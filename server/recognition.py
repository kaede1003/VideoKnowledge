"""Overlapped, incremental Whisper transcription (not a token-streaming ASR model)."""
from __future__ import annotations
import os
import numpy as np
from .asr_core import WhisperEngine
from .stream_protocol import RATE
from .stream_store import Job

class StreamingWhisperEngine(WhisperEngine):
    def __init__(self, loader=None):
        super().__init__(loader)
        self.model_name = os.getenv('VKN_ASR_MODEL','small').strip() or 'small'

    def transcribe_job(self, job: Job):
        if not job.packets:
            return []
        pcm = np.frombuffer(job.pcm, dtype='<i2').astype(np.float32) / 32768.0
        # Do not discard a quiet voice merely because its RMS is below 0.003.
        if not pcm.size or not np.any(pcm):
            return []
        opts=job.options
        language=opts.get('language','auto')
        if language=='auto':
            language=os.getenv('VKN_ASR_LANGUAGE','auto')
        prompt=[]
        if opts.get('hotwords'):prompt.append('Terms: '+opts['hotwords'])
        # Previous machine transcripts are not acoustic evidence. Refeeding an
        # error as an initial prompt may perpetuate it. Only explicit user terms
        # are allowed here; neighbouring AUDIO remains in the overlap window.
        segments, info = self._ensure().transcribe(
            pcm, task='transcribe', language=None if language=='auto' else language,
            beam_size=max(1,min(8,int(os.getenv('VKN_ASR_BEAM','5')))),
            best_of=1, temperature=0.0, condition_on_previous_text=False,
            initial_prompt='\n'.join(prompt) or None, hotwords=opts.get('hotwords') or None,
            word_timestamps=True,
            vad_filter=os.getenv('VKN_ASR_VAD','1')!='0',
            vad_parameters={'threshold':0.35,'min_silence_duration_ms':600,'speech_pad_ms':400},
            no_speech_threshold=.6, compression_ratio_threshold=2.4,
        )
        detected=getattr(info,'language',None) or (language if language!='auto' else 'unknown')
        probability=float(getattr(info,'language_probability',0.0))
        result=[]
        def metric(obj, name, default):
            try:
                value=float(getattr(obj,name,default))
                return value if np.isfinite(value) else default
            except (TypeError,ValueError):return default

        for seg in segments:
            selected=[]
            words=getattr(seg,'words',None) or []
            for word in words:
                a,b=float(word.start),float(word.end)
                # Each word belongs to exactly one fresh interval. Overlap supplies
                # acoustic context; future/right words are held for the next commit.
                midpoint=(a+b)/2
                if job.owner_start-1e-6 <= midpoint < job.owner_end-1e-6:
                    selected.append(word)
            if selected:
                text=''.join(w.word for w in selected).strip()
                start=float(selected[0].start);end=float(selected[-1].end)
                confidence=sum(float(getattr(w,'probability',0)) for w in selected)/len(selected)
            elif words:
                continue
            else:
                # Defensive fallback for adapters lacking word timestamps. Real
                # faster-whisper supplies words; flag a fallback for inspection.
                start,end=float(seg.start),float(seg.end)
                if not job.owner_start-1e-6 <= (start+end)/2 < job.owner_end-1e-6:
                    continue
                text=str(seg.text).strip();confidence=0.0
            if not text:
                continue
            avg_logprob=metric(seg,'avg_logprob',0.0)
            no_speech=metric(seg,'no_speech_prob',0.0)
            compression=metric(seg,'compression_ratio',0.0)
            flags=[]
            if confidence<.55:flags.append('word_score_low')
            if probability<.65 or detected=='unknown':flags.append('language_uncertain')
            if avg_logprob<-.9:flags.append('segment_score_low')
            if no_speech>.45:flags.append('possible_nonspeech')
            if compression>2.4:flags.append('possible_repetition')
            if not words:flags.append('word_timestamps_missing')
            labels={'word_score_low':'识别模型的字词分数较低','language_uncertain':'语种不确定，建议指定原视频语言',
                    'segment_score_low':'该段模型解码分数较低','possible_nonspeech':'可能包含静音或非语音误识别',
                    'possible_repetition':'可能有重复生成','word_timestamps_missing':'缺少词级时间戳'}
            # Scores/thresholds are diagnostic heuristics, NOT calibrated accuracy.
            result.append({'time':round(job.media_time(start),3),'end':round(job.media_time(end),3),
                           '_audioStart':start,'_audioEnd':end,
                           '_words':[{'start':float(w.start),'end':float(w.end),'word':str(w.word)} for w in selected],
                           'text':text,'language':detected,'languageProbability':round(probability,3),
                           'confidence':round(confidence,3),
                           'needsReview':bool(flags), 'qualityFlags':flags,
                           'asrModel':self.model_name, 'qualityVersion':'0.7.1',
                           'asrAvgLogprob':round(avg_logprob,4),'asrNoSpeechProb':round(no_speech,4),
                           'asrCompressionRatio':round(compression,4), 'verificationStatus':'machine_unverified',
                           'reviewReason':'；'.join(labels[f] for f in flags)})
        return result
