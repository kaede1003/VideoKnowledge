"""Optional, local block-wise speaker diarization; never infer personal identity.

V0.8 requests automatic grouping on new sessions unless the user disables it.
Models still require explicit installation. Labels are
session-scoped and provisional. Missing models degrade to unattributed text,
not fake alternating speakers. This is NOT native token-streaming diarization.
"""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import numpy as np

RATE = 16000
MODEL_FILES = ('segmentation.onnx', 'embedding.onnx')

def model_dir():
    return Path(os.getenv('VKN_SPEAKER_MODEL_DIR') or
                str(Path(__file__).resolve().parents[1] / 'models' / 'speakers'))

def availability():
    path = model_dir()
    installed = importlib.util.find_spec('sherpa_onnx') is not None
    files = all((path / name).is_file() for name in MODEL_FILES)
    return {'available': installed and files, 'installed': installed, 'models': files,
            'mode': 'LOCAL_CPU', 'message': ('组件与模型文件齐备，尚不代表实际推理已验证' if installed and files else
              '未安装可选说话人组件/模型；运行 INSTALL_SPEAKER_MODEL.bat，重启服务')}

def unit(vector):
    a = np.asarray(vector, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(a))
    if not a.size or not np.all(np.isfinite(a)) or n < 1e-8:
        return None
    return a / n

def nonoverlap_regions(turn, turns):
    """Exclude all detected concurrent speakers from embedding audio."""
    spans = [(float(turn['start']), float(turn['end']))]
    for other in turns:
        if other['local'] == turn['local']:
            continue
        a, b = float(other['start']), float(other['end'])
        out = []
        for left, right in spans:
            if b <= left or a >= right:
                out.append((left, right)); continue
            if left < a: out.append((left, min(a, right)))
            if b < right: out.append((max(b, left), right))
        spans = out
    return [(a, b) for a, b in spans if b - a > .03]

class SherpaBackend:
    """Uses public sherpa-onnx Python APIs; imported lazily (no torch required)."""
    def __init__(self):
        if not availability()['available']:
            raise RuntimeError(availability()['message'])
        import sherpa_onnx as so
        path = model_dir()
        cfg = so.OfflineSpeakerDiarizationConfig(
            segmentation=so.OfflineSpeakerSegmentationModelConfig(
                pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(path / MODEL_FILES[0])),
                num_threads=2, provider='cpu'),
            embedding=so.SpeakerEmbeddingExtractorConfig(model=str(path / MODEL_FILES[1]), num_threads=2, provider='cpu'),
            clustering=so.FastClusteringConfig(num_clusters=-1, threshold=.5),
            min_duration_on=.2, min_duration_off=.3)
        if not cfg.validate(): raise RuntimeError('说话人模型配置无效，请重新安装可选模型')
        self.pipeline = so.OfflineSpeakerDiarization(cfg)
        self.extractor = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(
            model=str(path / MODEL_FILES[1]), num_threads=2, provider='cpu'))

    def analyze(self, pcm):
        length = len(pcm) / RATE
        # The segmentation model is trained on fixed windows. A short tail gets
        # silence padding, but padding never enters text or embedding samples.
        audio = np.pad(pcm, (0, max(0, 10 * RATE - len(pcm)))).astype(np.float32)
        turns = [{'start': max(0., float(r.start)), 'end': min(length, float(r.end)), 'local': int(r.speaker)}
                 for r in self.pipeline.process(audio).sort_by_start_time() if float(r.start) < length]
        turns = [r for r in turns if r['end'] > r['start']]
        grouped = defaultdict(list)
        for turn in turns:
            for a, b in nonoverlap_regions(turn, turns):
                grouped[turn['local']].append(pcm[int(a * RATE):int(b * RATE)])
        vectors = {}
        for local, slices in grouped.items():
            samples = np.concatenate(slices) if slices else np.array([], dtype=np.float32)
            seconds = len(samples) / RATE
            if seconds < .8: continue
            # Bounded representative audio; this isn't a cross-video voice database.
            samples = np.ascontiguousarray(samples[:8 * RATE], dtype=np.float32)
            stream = self.extractor.create_stream()
            stream.accept_waveform(sample_rate=RATE, waveform=samples)
            stream.input_finished()
            if self.extractor.is_ready(stream):
                vector = unit(self.extractor.compute(stream))
                if vector is not None: vectors[local] = (vector, seconds)
        return turns, vectors

def match_speakers(vectors, saved, max_speakers=6):
    """Session-only cosine matching with an uncertainty band and one-to-one match.

    Similarities are heuristic scores, NOT calibrated identity probabilities.
    Persisted centroids are committed together with the ASR watermark.
    """
    state = deepcopy(saved or {})
    bank = state.setdefault('profiles', [])
    assigned, used = {}, set()
    candidates, best_by_local = [], {}
    for local, (vec, duration) in vectors.items():
        scores = []
        for idx, profile in enumerate(bank):
            old = unit(profile.get('vector', []))
            if old is not None and old.shape == vec.shape:
                scores.append((float(np.dot(vec, old)), idx))
        scores.sort(reverse=True)
        best_by_local[local] = scores
        if scores:
            best, idx = scores[0]
            margin = best - scores[1][0] if len(scores) > 1 else 1.
            if best >= .55 and margin >= .08:
                candidates.append((best, local, idx))
    for score, local, idx in sorted(candidates, reverse=True):
        if idx in used: continue
        assigned[local] = (bank[idx]['id'], score); used.add(idx)
        vec, _ = vectors[local]
        # Conservative updating prevents a single uncertain turn drifting a voice.
        if score >= .65:
            old = unit(bank[idx]['vector'])
            new = unit(.9 * old + .1 * vec)
            bank[idx]['vector'] = new.tolist()
    for local, (vec, duration) in vectors.items():
        if local in assigned: continue
        scores = best_by_local.get(local, [])
        best = scores[0][0] if scores else -1.
        if duration >= 1.5 and best < .40 and len(bank) < max_speakers:
            ident = 1 + max([p['id'] for p in bank] or [0])
            bank.append({'id': ident, 'vector': vec.tolist()})
            assigned[local] = (ident, None)
        else:
            assigned[local] = (None, best if scores else None)
    return assigned, state

def at_word(start, end, turns):
    """Do not force words at overlap/turn boundaries into a single speaker."""
    width = max(.03, end - start)
    candidates = set()
    coverage = defaultdict(float)
    midpoint = (start + end) / 2
    for turn in turns:
        a, b = turn['start'], turn['end']
        overlap = max(0., min(end, b) - max(start, a))
        if overlap >= width * .20 or a <= midpoint < b:
            candidates.add(turn['local']); coverage[turn['local']] += overlap
    if len(candidates) > 1:
        return None, 'uncertain', '换人边界或可能交叠发言，需回听确认'
    if not candidates:
        return None, 'uncertain', '声音不足，无法可靠归属'
    who = next(iter(candidates))
    if coverage[who] < width * .5 and end > start:
        return None, 'uncertain', '说话人时间覆盖不足'
    return who, 'estimated', ''

class SpeakerAnnotator:
    def __init__(self, factory=SherpaBackend):
        self.factory = factory
        self.backend = None

    @staticmethod
    def strip_private(cue):
        return {k: v for k, v in cue.items() if k not in ('_words', '_audioStart', '_audioEnd')}

    def annotate(self, job, segments):
        if not job.options.get('diarize', False):
            return [self.strip_private(s) for s in segments]
        if not segments: return []
        before = deepcopy(job.speaker_state)
        try:
            if self.backend is None: self.backend = self.factory()
            pcm = np.frombuffer(job.pcm, dtype='<i2').astype(np.float32) / 32768.
            turns, vectors = self.backend.analyze(pcm)
            mapping, new_state = match_speakers(vectors, before, job.options.get('maxSpeakers', 6))
            result = []
            for original in segments:
                words = original.get('_words') or []
                if not words:
                    # No word timestamps: never put a whole mixed sentence under
                    # whichever person spoke the longest.
                    result.append({**self.strip_private(original), 'speakerStatus': 'uncertain',
                                   'speakerReason': '缺少词级时间戳，未强行归属'}); continue
                groups = []
                for word in words:
                    local, status, reason = at_word(word['start'], word['end'], turns)
                    ident, score = mapping.get(local, (None, None))
                    if ident is None and status == 'estimated':
                        status, reason = 'uncertain', '语音过短、声音相近或达到人数上限，待确认'
                    key = (ident, status, reason)
                    if not groups or groups[-1][0] != key:
                        groups.append((key, [], score))
                    groups[-1][1].append(word)
                for (ident, status, reason), selected, score in groups:
                    text = ''.join(w['word'] for w in selected).strip()
                    if not text: continue
                    cue = self.strip_private(original)
                    cue.update(text=text, time=round(job.media_time(selected[0]['start']), 3),
                               end=round(job.media_time(selected[-1]['end']), 3),
                               speakerId=f'{job.session}:spk{ident}' if ident else '',
                               speakerStatus=status, speakerReason=reason)
                    if score is not None: cue['speakerSimilarity'] = round(float(score), 3)
                    result.append(cue)
            job.speaker_state = new_state
            return result
        except Exception as exc:
            # This optional step cannot swallow the ASR transcript or cause an
            # endless ASR retry loop when a model component is not installed.
            job.speaker_state = before
            reason = '说话人区分不可用，原文保留：' + str(exc)[:160]
            return [{**self.strip_private(s), 'speakerStatus': 'unavailable', 'speakerReason': reason} for s in segments]
