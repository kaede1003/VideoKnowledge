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
from importlib.metadata import PackageNotFoundError, version as distribution_version
import logging
import re
import multiprocessing
import os
from pathlib import Path
import threading
from contextlib import suppress
import numpy as np

RATE = 16000
MODEL_FILES = ('segmentation.onnx', 'embedding.onnx')
MIN_DIARIZATION_SECONDS = 0.8
MIN_AUDIO_PEAK = 0.003
MIN_AUDIO_RMS = 0.0008
# sherpa-onnx 1.13.1 added bounds checks that prevent out-of-range access in
# speaker diarization. 1.12.34 and earlier are deliberately blocked here.
MIN_SAFE_SHERPA_VERSION = (1, 13, 1)
PINNED_SHERPA_VERSION = '1.13.8'
LOG = logging.getLogger('vkn.speaker')


def _version_tuple(value):
    """Parse the numeric major.minor.patch prefix without another dependency."""
    match = re.match(r'^\s*(\d+)\.(\d+)\.(\d+)', str(value or ''))
    return tuple(int(part) for part in match.groups()) if match else None


def _installed_sherpa_version():
    for distribution in ('sherpa-onnx', 'sherpa_onnx'):
        try:
            return distribution_version(distribution)
        except (PackageNotFoundError, ValueError, OSError):
            continue
    return ''

def model_dir():
    return Path(os.getenv('VKN_SPEAKER_MODEL_DIR') or
                str(Path(__file__).resolve().parents[1] / 'models' / 'speakers'))

def availability():
    path = model_dir()
    try:
        installed = importlib.util.find_spec('sherpa_onnx') is not None
    except (ImportError, ValueError):
        installed = False
    version = _installed_sherpa_version() if installed else ''
    parsed = _version_tuple(version)
    version_safe = bool(parsed and parsed >= MIN_SAFE_SHERPA_VERSION)
    files = all((path / name).is_file() for name in MODEL_FILES)
    available = installed and version_safe and files
    if not installed:
        message = '未安装可选说话人组件；运行 INSTALL_SPEAKER_MODEL.bat 安装。'
    elif not version:
        message = ('无法确认 sherpa-onnx 运行库版本；为避免旧原生库访问冲突，'
                   '请停止服务后运行 INSTALL_SPEAKER_MODEL.bat 更新到 ' + PINNED_SHERPA_VERSION)
    elif not version_safe:
        message = (f'当前 sherpa-onnx {version} 低于安全最低版本 1.13.1；'
                   '该旧版本缺少说话人分离边界检查。请停止服务后运行 '
                   'INSTALL_SPEAKER_MODEL.bat 更新到 ' + PINNED_SHERPA_VERSION)
    elif not files:
        message = '说话人模型文件不完整；运行 INSTALL_SPEAKER_MODEL.bat 补齐模型。'
    else:
        message = (f'sherpa-onnx {version} 与模型文件齐备；原生推理在独立子进程运行，'
                   '真实音频准确率仍需现场验收。')
    return {'available': available, 'installed': installed, 'version': version or 'unknown',
            'minimum_safe_version': '1.13.1', 'pinned_version': PINNED_SHERPA_VERSION,
            'version_safe': version_safe, 'models': files,
            'mode': 'LOCAL_CPU', 'execution': 'isolated_child_process',
            'failure_policy': 'disable_until_service_restart', 'message': message}

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
        runtime = availability()
        if not runtime['available']:
            raise RuntimeError(runtime['message'])
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
        """Run native diarization only on finite, non-trivial mono float audio.

        sherpa-onnx may legitimately return an empty result when no speech is
        detected. Treat that as an ordinary uncertain outcome and never call the
        embedding extractor with an empty sample list.
        """
        audio = _prepare_diarization_audio(pcm)
        if audio is None:
            return [], {}
        length = len(audio) / RATE
        # The segmentation model is trained on fixed windows. A short tail gets
        # silence padding, but padding never enters text or embedding samples.
        padded = np.pad(audio, (0, max(0, 10 * RATE - len(audio)))).astype(np.float32)
        diarization = self.pipeline.process(padded)
        if diarization is None:
            return [], {}
        ordered = diarization.sort_by_start_time() if hasattr(diarization, 'sort_by_start_time') else diarization
        if ordered is None:
            return [], {}
        try:
            raw_turns = list(ordered)
        except TypeError:
            return [], {}
        turns = []
        for row in raw_turns:
            try:
                start, end, local = float(row.start), float(row.end), int(row.speaker)
            except (AttributeError, TypeError, ValueError, OverflowError):
                continue
            if not (np.isfinite(start) and np.isfinite(end) and start < length and end > start):
                continue
            turns.append({'start': max(0., start), 'end': min(length, end), 'local': local})
        if not turns:
            return [], {}
        grouped = defaultdict(list)
        for turn in turns:
            for a, b in nonoverlap_regions(turn, turns):
                piece = audio[max(0, int(a * RATE)):min(len(audio), int(b * RATE))]
                if piece.size:
                    grouped[turn['local']].append(piece)
        vectors = {}
        for local, slices in grouped.items():
            samples = np.concatenate(slices) if slices else np.array([], dtype=np.float32)
            seconds = len(samples) / RATE
            if seconds < MIN_DIARIZATION_SECONDS or not samples.size:
                continue
            # Bounded representative audio; this isn't a cross-video voice database.
            samples = np.ascontiguousarray(samples[:8 * RATE], dtype=np.float32)
            if not samples.size or not np.all(np.isfinite(samples)):
                continue
            stream = self.extractor.create_stream()
            stream.accept_waveform(sample_rate=RATE, waveform=samples)
            stream.input_finished()
            if self.extractor.is_ready(stream):
                vector = unit(self.extractor.compute(stream))
                if vector is not None:
                    vectors[local] = (vector, seconds)
        return turns, vectors


def _prepare_diarization_audio(pcm):
    """Return contiguous float32 audio, or None for empty/quiet/short windows."""
    try:
        audio = np.asarray(pcm, dtype=np.float32).reshape(-1)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('invalid speaker audio buffer') from exc
    if audio.size < int(MIN_DIARIZATION_SECONDS * RATE):
        return None
    if not np.all(np.isfinite(audio)):
        raise ValueError('speaker audio contains non-finite samples')
    peak = float(np.max(np.abs(audio)))
    if peak < MIN_AUDIO_PEAK:
        return None
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    if rms < MIN_AUDIO_RMS:
        return None
    return np.ascontiguousarray(audio, dtype=np.float32)


class SpeakerBackendError(RuntimeError):
    """A failure contained inside the isolated native speaker worker."""



def _sherpa_worker_main(connection):
    """Child-process entry point: native ONNX faults cannot kill the ASR server."""
    backend = None
    try:
        backend = SherpaBackend()
        connection.send({'type': 'ready'})
    except BaseException as exc:
        with suppress(Exception):
            connection.send({'type': 'startup_error', 'error': type(exc).__name__})
        with suppress(Exception):
            connection.close()
        return
    try:
        while True:
            request = connection.recv()
            if request is None:
                return
            if not isinstance(request, dict) or request.get('type') != 'analyze':
                connection.send({'type': 'error', 'error': 'INVALID_REQUEST'})
                continue
            try:
                turns, vectors = backend.analyze(request.get('pcm'))
                serial_vectors = {
                    int(local): (np.asarray(vector, dtype=np.float32).tolist(), float(duration))
                    for local, (vector, duration) in vectors.items()
                }
                connection.send({'type': 'ok', 'turns': turns, 'vectors': serial_vectors})
            except BaseException as exc:
                # Do not leak paths, audio or model internals through IPC.
                with suppress(Exception):
                    connection.send({'type': 'error', 'error': type(exc).__name__})
    except (EOFError, OSError):
        pass
    finally:
        with suppress(Exception):
            connection.close()


def _exit_code_detail(code):
    return '' if code is None else ':0x' + format(int(code) & 0xffffffff, '08X')


def _bounded_timeout(value, default):
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError):
        seconds = float(default)
    if not np.isfinite(seconds):
        seconds = float(default)
    return max(5.0, min(600.0, seconds))


class IsolatedSherpaBackend:
    """Persistent sherpa worker isolated in a spawned process.

    A native access violation (0xC0000005 on Windows) terminates only this
    child. The parent detects EOF/exit, marks diarization unavailable for the
    remainder of this service run, and lets the caller transcribe the original
    full audio without speaker guesses.
    """
    def __init__(self, *, worker_target=_sherpa_worker_main, startup_timeout=None,
                 analyze_timeout=None):
        self._ctx = multiprocessing.get_context('spawn')
        self._worker_target = worker_target
        self._startup_timeout = _bounded_timeout(
            startup_timeout if startup_timeout is not None else
            os.getenv('VKN_SPEAKER_START_TIMEOUT_SECONDS', '90'), 90)
        self._analyze_timeout = _bounded_timeout(
            analyze_timeout if analyze_timeout is not None else
            os.getenv('VKN_SPEAKER_TIMEOUT_SECONDS', '90'), 90)
        self._lock = threading.Lock()
        self._process = None
        self._connection = None
        self._failure = ''
        self._closed = False

    @property
    def failure(self):
        return self._failure

    def snapshot(self):
        if self._closed:
            phase = 'closed'
        elif self._failure:
            phase = 'disabled_after_failure'
        elif self._process is not None and self._process.is_alive():
            phase = 'ready'
        elif self._process is not None:
            phase = 'worker_exited'
        else:
            phase = 'not_started'
        return {'mode': 'isolated_process', 'phase': phase,
                'error': self._failure[:120]}

    def _terminate_worker(self):
        connection, process = self._connection, self._process
        self._connection = None
        self._process = None
        if connection is not None:
            with suppress(Exception):
                connection.close()
        if process is not None:
            with suppress(Exception):
                if process.is_alive():
                    process.terminate()
                process.join(timeout=2)
                if process.is_alive() and hasattr(process, 'kill'):
                    process.kill()
                    process.join(timeout=2)
            with suppress(Exception):
                process.close()

    def _fail(self, reason):
        if not self._failure:
            self._failure = str(reason)[:120]
            LOG.warning('Sherpa speaker worker disabled for this service run: %s', self._failure)
        self._terminate_worker()
        raise SpeakerBackendError(self._failure)

    def _start(self):
        parent, child = self._ctx.Pipe(duplex=True)
        process = self._ctx.Process(target=self._worker_target, args=(child,),
                                    name='vkn-sherpa-speaker', daemon=True)
        try:
            process.start()
        except Exception as exc:
            with suppress(Exception):
                parent.close()
            with suppress(Exception):
                child.close()
            self._fail('SHERPA_WORKER_START_FAILED:' + type(exc).__name__)
        with suppress(Exception):
            child.close()
        self._connection, self._process = parent, process
        if not parent.poll(self._startup_timeout):
            self._fail('SHERPA_WORKER_START_TIMEOUT')
        try:
            reply = parent.recv()
        except (EOFError, OSError):
            with suppress(Exception):
                process.join(timeout=0.2)
            code = process.exitcode
            self._fail('SHERPA_WORKER_EXITED_DURING_START' + _exit_code_detail(code))
        if not isinstance(reply, dict) or reply.get('type') != 'ready':
            error = reply.get('error', 'UNKNOWN') if isinstance(reply, dict) else 'BAD_HANDSHAKE'
            self._fail('SHERPA_WORKER_INIT_FAILED:' + str(error)[:48])

    def start(self):
        """Start the isolated worker and verify native model initialization only."""
        with self._lock:
            if self._closed:
                raise SpeakerBackendError('SHERPA_WORKER_CLOSED')
            if self._failure:
                raise SpeakerBackendError(self._failure)
            if self._process is None:
                self._start()
            elif not self._process.is_alive():
                self._fail('SHERPA_WORKER_EXITED_BEFORE_ANALYZE' +
                           _exit_code_detail(self._process.exitcode))
            return self.snapshot()

    def analyze(self, pcm):
        audio = _prepare_diarization_audio(pcm)
        if audio is None:
            return [], {}
        with self._lock:
            if self._closed:
                raise SpeakerBackendError('SHERPA_WORKER_CLOSED')
            if self._failure:
                raise SpeakerBackendError(self._failure)
            if self._process is None:
                self._start()
            connection, process = self._connection, self._process
            try:
                connection.send({'type': 'analyze', 'pcm': audio})
                if not connection.poll(self._analyze_timeout):
                    self._fail('SHERPA_ANALYZE_TIMEOUT')
                reply = connection.recv()
            except (EOFError, OSError, BrokenPipeError):
                if process is not None:
                    with suppress(Exception):
                        process.join(timeout=0.2)
                code = process.exitcode if process is not None else None
                self._fail('SHERPA_WORKER_EXITED' + _exit_code_detail(code))
            if not isinstance(reply, dict) or reply.get('type') != 'ok':
                error = reply.get('error', 'BAD_RESPONSE') if isinstance(reply, dict) else 'BAD_RESPONSE'
                self._fail('SHERPA_NATIVE_ANALYSIS_FAILED:' + str(error)[:48])
            vectors = {
                int(local): (np.asarray(value[0], dtype=np.float32), float(value[1]))
                for local, value in reply.get('vectors', {}).items()
            }
            return reply.get('turns') or [], vectors

    def close(self):
        self._closed = True
        # Terminate rather than waiting for a potentially stuck native call.
        # This child owns only the optional speaker model, never ASR/audio storage.
        self._terminate_worker()

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

def acoustic_regions(turns, start, end):
    """Partition owned audio by *acoustic* speaker changes, never ASR tokens.

    Every sample within [start, end] belongs to exactly one region. An overlap
    is one uncertain region, not two copies of the same speech. A missing
    diarization turn is an unassigned region rather than dropped audio.
    """
    if not (0 <= start < end):
        raise ValueError('invalid owned audio interval')
    clipped = []
    edges = [start, end]
    for turn in turns:
        a = max(start, float(turn['start']))
        b = min(end, float(turn['end']))
        if a >= b: continue
        clipped.append((a, b, int(turn['local'])))
        edges.extend((a, b))
    edges = sorted(set(round(v, 6) for v in edges))
    spans = []
    for a, b in zip(edges, edges[1:]):
        if b <= a: continue
        mid = (a + b) / 2
        active = {who for x, y, who in clipped if x <= mid < y}
        who = next(iter(active)) if len(active) == 1 else None
        mode = 'speech' if len(active) == 1 else ('overlap' if active else 'unknown')
        if spans and spans[-1][2:] == (who, mode):
            spans[-1] = (spans[-1][0], b, who, mode)
        else:
            spans.append((a, b, who, mode))
    return spans


def slice_audio_job(job, start, end):
    """Construct a transient owned-audio job retaining each packet's media clock.

    This is never persisted independently, and cannot change the durable packet
    sequence or ASR commit watermark. Subcalls only see their assigned PCM.
    """
    from .stream_protocol import AUDIO, Packet
    from .stream_store import Job
    if not 0 <= start < end <= len(job.pcm) / RATE + 1e-6:
        raise ValueError('invalid ASR speaker slice')
    left = round(start * RATE)
    right = round(end * RATE)
    pieces = []
    offset = 0
    for packet in job.packets:
        frames = len(packet.pcm) // 2
        a, b = max(left, offset), min(right, offset + frames)
        if a < b:
            f0, f1 = (a - offset) / frames, (b - offset) / frames
            t0 = packet.start + (packet.end - packet.start) * f0
            t1 = packet.start + (packet.end - packet.start) * f1
            pcm = packet.pcm[2 * (a - offset):2 * (b - offset)]
            pieces.append(Packet(packet.seq, t0, t1, AUDIO, pcm))
        offset += frames
    length = sum(p.duration for p in pieces)
    if not pieces or length <= 0 or sum(len(p.pcm) for p in pieces) != 2 * (right - left):
        raise ValueError('speaker slice did not preserve all PCM samples')
    return Job(job.session, pieces, job.commit_seq, 0, length, job.options,
               '', final=False, reset=False, speaker_state=deepcopy(job.speaker_state))


class SpeakerAnnotator:
    def __init__(self, factory=IsolatedSherpaBackend):
        self.factory = factory
        self.backend = None

    def snapshot(self):
        if self.backend is None:
            return {'mode': 'isolated_process', 'phase': 'not_started', 'error': ''}
        snapshot = getattr(self.backend, 'snapshot', None)
        return snapshot() if callable(snapshot) else {'mode': 'in_process_test_backend', 'phase': 'active', 'error': ''}

    def close(self):
        backend = self.backend
        close = getattr(backend, 'close', None)
        if callable(close):
            with suppress(Exception):
                close()

    @staticmethod
    def strip_private(cue):
        return {k: v for k, v in cue.items() if k not in ('_words', '_audioStart', '_audioEnd')}

    def transcribe_and_annotate(self, job, engine):
        """Ollama: diarize the AUDIO first, then transcribe distinct voices.

        A text-only transcript has no evidence to distribute its words across
        multiple speakers. For a single dominant voice, reuse the full-window
        ASR result; for multiple acoustic turns, run independent ASR on bounded
        chunks. All partial results stay in memory until StreamStore.commit,
        so a later model failure cannot advance the durable audio watermark.
        """
        if not job.packets or not job.options.get('diarize', False):
            return self.annotate(job, engine.transcribe_job(job))
        if getattr(engine, 'backend_name', '') != 'ollama-qwen3-asr':
            return self.annotate(job, engine.transcribe_job(job))

        def plain(status, reason):
            return [{**self.strip_private(row), 'speakerStatus': status,
                     'speakerReason': reason}
                    for row in engine.transcribe_job(job)]

        # Audio analysis is optional. If its files/runtime are unavailable,
        # retain one complete ASR result instead of failing the recognition.
        try:
            if self.backend is None and self.factory is IsolatedSherpaBackend:
                state = availability()
                if not state['available']:
                    return plain('unavailable', state['message'])
            if self.backend is None: self.backend = self.factory()
            pcm = np.frombuffer(job.pcm, dtype='<i2').astype(np.float32) / 32768.
            turns, vectors = self.backend.analyze(pcm)
            mapping, new_state = match_speakers(
                vectors, job.speaker_state, job.options.get('maxSpeakers', 6))
            regions = acoustic_regions(turns, job.owner_start, job.owner_end)
        except Exception as exc:
            return plain('unavailable', '声学说话人分析失败，原文保留：' + str(exc)[:120])

        known = {local for a, b, local, _ in regions if local is not None}
        if not known:
            return plain('uncertain', '没有可靠的声学发言区间，未猜测说话人')

        def label(row, local, mode):
            ident, similarity = mapping.get(local, (None, None))
            if mode == 'overlap':
                status, reason = 'overlap', '多人声音交叠，无法单独归属'
            elif mode == 'unknown':
                status, reason = 'uncertain', '此段未检测到可靠的声音归属'
            elif ident is None:
                status, reason = 'uncertain', '声纹较短或相似度不足，未强行归属'
            else:
                status, reason = 'estimated', '按音频声学分段估计；没有词级时间戳'
            cue = {**self.strip_private(row),
                   'speakerId': f'{job.session}:spk{ident}' if status == 'estimated' else '',
                   'speakerStatus': status, 'speakerReason': reason,
                   'speakerTiming': 'acoustic_turn'}
            if status == 'estimated' and similarity is not None:
                cue['speakerSimilarity'] = round(float(similarity), 3)
            if 'word_timestamps_missing' in cue.get('qualityFlags', []):
                cue['reviewReason'] = str(cue.get('reviewReason', '')).replace(
                    '不强行分配说话人', '归属由音频声学分段估计，非词级对齐')
            return cue

        # Exactly one detected speaker: the WHOLE owner window can be labelled
        # only if it is substantially covered by that one voice. Otherwise the
        # unassigned portion may contain another speaker's speech.
        if len(known) == 1 and not any(m == 'overlap' for _, _, _, m in regions):
            local = next(iter(known))
            coverage = sum(b-a for a, b, who, _ in regions if who == local)
            dominant = (coverage >= .90 * (job.owner_end - job.owner_start) and
                        not any(b-a > .6 for a,b,who,_ in regions if who is None))
            rows = engine.transcribe_job(job)
            result = [label(row, local, 'speech') if dominant else
                      label(row, None, 'unknown') for row in rows]
            job.speaker_state = new_state
            return result

        # Multiple different voices require independently transcribed AUDIO;
        # labelling one mixed Ollama transcript with a single voice is invalid.
        # Very rapid alternation is held for review rather than issuing dozens
        # of tiny (often hallucinated) ASR requests.
        if len(regions) > 8 or any(b-a < .25 and mode != 'unknown'
                                    for a,b,_,mode in regions):
            return plain('uncertain', '说话人切换过快或片段过短，未强行归属')

        all_rows = []
        for a, b, local, mode in regions:
            subjob = slice_audio_job(job, a, b)
            rows = engine.transcribe_job(subjob)  # Errors MUST propagate.
            if not rows:
                # A short ASR fragment may be missed even when the complete
                # utterance is audible. Do not silently discard this region:
                # fall back to the full original audio without speaker guesses.
                piece = np.frombuffer(subjob.pcm, dtype='<i2')
                if piece.size and float(np.max(np.abs(piece.astype(np.int32)))) >= 100:
                    return plain('uncertain',
                                 '按人声切分后有片段未识别，已退回完整音频转写；待回听')
            for row in rows:
                all_rows.append(label(row, local, mode))
        # Commit caller persists both these rows and the session voice profiles
        # atomically. Never update the speaker state on partial inference.
        job.speaker_state = new_state
        return all_rows

    def annotate(self, job, segments):
        if not job.options.get('diarize', False):
            return [self.strip_private(s) for s in segments]
        if not segments: return []
        before = deepcopy(job.speaker_state)
        try:
            if self.backend is None and self.factory is IsolatedSherpaBackend:
                state = availability()
                if not state['available']:
                    reason = '说话人区分不可用，原文保留：' + state['message']
                    return [{**self.strip_private(row), 'speakerStatus': 'unavailable',
                             'speakerReason': reason} for row in segments]
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
