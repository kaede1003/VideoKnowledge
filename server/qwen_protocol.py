"""Model-independent validation and timing ownership for the optional Qwen engine.

No invented confidence scores, evenly spaced pseudo-word timestamps, or global
text deduplication. Alignment validates spelling coverage, not ASR correctness.
"""
from __future__ import annotations
import base64
import math
import unicodedata

RATE = 16000
MAX_AUDIO_SECONDS = 40
MAX_LINE = 2 * 1024 * 1024
LANGUAGES = {
    'Chinese':'zh', 'English':'en', 'Cantonese':'yue', 'Spanish':'es', 'Portuguese':'pt',
    'Arabic':'ar', 'German':'de', 'French':'fr', 'Indonesian':'id', 'Italian':'it',
    'Korean':'ko', 'Russian':'ru', 'Thai':'th', 'Vietnamese':'vi', 'Japanese':'ja',
    'Turkish':'tr', 'Hindi':'hi', 'Malay':'ms', 'Dutch':'nl', 'Swedish':'sv',
    'Danish':'da', 'Finnish':'fi', 'Polish':'pl', 'Czech':'cs', 'Filipino':'fil',
    'Persian':'fa', 'Greek':'el', 'Hungarian':'hu', 'Macedonian':'mk', 'Romanian':'ro',
}
ALIGNED = {'zh','en','yue','fr','de','it','ja','ko','pt','ru','es'}


class ASRBackendError(RuntimeError):
    def __init__(self, code, detail=''):
        self.code = str(code)
        super().__init__(self.code + (': ' + detail if detail else ''))


def language_code(value):
    key = str(value or '').strip()
    if key.lower() in LANGUAGES.values():
        return key.lower()
    return next((v for k,v in LANGUAGES.items() if k.lower() == key.lower()), 'unknown')


def language_name(value):
    code = language_code(value)
    if code == 'unknown':
        if value in (None, '', 'auto', 'unknown'):
            return None
        raise ASRBackendError('ASR_LANGUAGE_UNSUPPORTED')
    return next(k for k,v in LANGUAGES.items() if v == code)


def decode_request(data):
    if not isinstance(data, dict) or data.get('op') != 'transcribe':
        raise ASRBackendError('ASR_BAD_REQUEST')
    try:
        pcm = base64.b64decode(data['pcm16'], validate=True)
        a,b = float(data['owner_start']), float(data['owner_end'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ASRBackendError('ASR_BAD_AUDIO') from exc
    duration = len(pcm)/(RATE*2)
    if len(pcm)%2 or not 0 < duration <= MAX_AUDIO_SECONDS:
        raise ASRBackendError('ASR_BAD_AUDIO')
    if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b <= duration+1e-6):
        raise ASRBackendError('ASR_BAD_OWNERSHIP')
    language = language_name(data.get('language', 'auto'))
    return pcm, a, min(b,duration), language, str(data.get('hotwords', ''))[:600]


def lexical_map(text):
    # Ignore punctuation/space ONLY for alignment coverage. Return raw offsets
    # so the ASR's original spelling, punctuation and spacing are retained.
    out=[]; indexes=[]
    for i,c in enumerate(text):
        if unicodedata.category(c)[0] in {'P','Z','C'} or c.isspace():
            continue
        for char in c.casefold():
            out.append(char); indexes.append(i)
    return ''.join(out), indexes


def align_words(text, timestamps, duration):
    """Return real aligner timing plus exact substrings; reject missing characters."""
    if not text.strip():
        return []
    if not isinstance(timestamps, list) or not timestamps or len(timestamps)>12000:
        raise ASRBackendError('ASR_ALIGNMENT_INVALID')
    target, positions=lexical_map(text)
    pieces=[]; timing=[]; last=-1.
    for row in timestamps:
        if not isinstance(row,dict):
            raise ASRBackendError('ASR_ALIGNMENT_INVALID')
        word=str(row.get('text',''))
        token,_=lexical_map(word)
        try:
            a,b=float(row['start_time']),float(row['end_time'])
        except (TypeError,ValueError,KeyError) as exc:
            raise ASRBackendError('ASR_ALIGNMENT_INVALID') from exc
        if not token or not(math.isfinite(a) and math.isfinite(b) and
                              0 <= a <= b <= duration+.08 and a >= last-1e-6):
            raise ASRBackendError('ASR_ALIGNMENT_INVALID')
        last=a; pieces.append(token); timing.append((a,min(b,duration)))
    if ''.join(pieces)!=target:
        raise ASRBackendError('ASR_ALIGNMENT_TEXT_MISMATCH')
    result=[]; offset=0
    for i,(token,(a,b)) in enumerate(zip(pieces,timing)):
        start = 0 if i==0 else positions[offset]
        offset+=len(token)
        end = len(text) if i==len(pieces)-1 else positions[offset]
        result.append({'start':a,'end':b,'word':text[start:end]})
    if ''.join(w['word'] for w in result)!=text:
        raise ASRBackendError('ASR_ALIGNMENT_TEXT_MISMATCH')
    return result


def select_owned(words, start, end):
    return [w for w in words if start-1e-6 <= (w['start']+w['end'])/2 < end-1e-6]


def build_segments(job, reply, model, device):
    if not isinstance(reply, dict) or not isinstance(reply.get('segments'), list):
        raise ASRBackendError('ASR_WORKER_BAD_RESPONSE')
    result=[]
    for row in reply['segments']:
        try:
            text=str(row['text']); a=float(row['start']); b=float(row['end'])
        except (TypeError, ValueError, KeyError) as exc:
            raise ASRBackendError('ASR_WORKER_BAD_RESPONSE') from exc
        if not text.strip(): continue
        if len(text)>20000 or not(math.isfinite(a) and math.isfinite(b) and 0<=a<=b<=len(job.pcm)/(RATE*2)+.1):
            raise ASRBackendError('ASR_WORKER_BAD_RESPONSE')
        words=row.get('words') or []
        flags=list(row.get('flags') or [])
        known_language=language_code(row.get('language'))
        if known_language=='unknown': flags.append('language_uncertain')
        result.append({'time':round(job.media_time(a),3),'end':round(job.media_time(b),3),
            '_audioStart':a,'_audioEnd':b,'_words':words,
            'text':text.strip(),'language':known_language,
            # Qwen's API does not expose Whisper-style calibrated scores.
            'confidence':None,'languageProbability':None,'asrAvgLogprob':None,
            'asrNoSpeechProb':None,'asrCompressionRatio':None,
            'asrEngine':'qwen3-native','asrModel':model,'asrDevice':device,
            'asrTiming':'aligned_words' if words else 'audio_window',
            'asrScoreStatus':'unavailable','qualityVersion':'0.11.0',
            'verificationStatus':'machine_unverified','qualityFlags':flags,
            'needsReview':bool(flags),
            'reviewReason':'；'.join({'word_timestamps_missing':'没有可靠词级时间戳，按音频窗口记录；不强行分配说话人',
                'language_uncertain':'语种未能明确识别','asr_repetition_suspected':'识别文字存在连续重复，需原音复核'}.get(f,f) for f in flags)})
    return result
