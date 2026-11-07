"""Audio packet, rolling window and ASR inference helpers.

The browser streams mono PCM16 at 16 kHz. Each binary packet starts with
'VKN2' + two little-endian float64 video-time coordinates (seconds),
followed by PCM16 samples. No audio is written to disk by this component.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
import struct
from typing import Callable

import numpy as np

RATE = 16000
MAGIC = b"VKN2"
HEADER_BYTES = 20
MAX_PACKET_BYTES = HEADER_BYTES + RATE * 2 * 2  # at most two seconds per message


@dataclass(frozen=True)
class AudioPacket:
    start: float
    end: float
    data: bytes

    @property
    def duration(self) -> float:
        return len(self.data) / (RATE * 2)


def decode_audio_packet(raw: bytes) -> AudioPacket:
    if not isinstance(raw, bytes) or len(raw) < HEADER_BYTES + 2 or len(raw) > MAX_PACKET_BYTES:
        raise ValueError("音频包大小不合法")
    if raw[:4] != MAGIC:
        raise ValueError("音频包版本不匹配")
    if (len(raw) - HEADER_BYTES) % 2:
        raise ValueError("PCM16数据长度必须为偶数")
    start, end = struct.unpack_from('<dd', raw, 4)
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end < 24*3600*30):
        raise ValueError("视频播放时间非法")
    duration = (len(raw) - HEADER_BYTES) / (RATE*2)
    if end - start > duration * 4.5 + 0.75:
        raise ValueError("视频时钟超出允许范围")
    return AudioPacket(start=start, end=end, data=raw[HEADER_BYTES:])


@dataclass
class AudioWindow:
    data: bytes
    start: float
    end: float


class AudioBuffer:
    """Bounded in-memory audio buffer, segmented at ~6 seconds.

    A discontinuity flushes the buffer instead of assigning speech to the
    wrong seek position. No synthetic audio/transcript is inserted.
    """

    def __init__(self, seconds: float = 6.0, min_tail: float = 0.8):
        if seconds < 1:
            raise ValueError("segment duration too small")
        self.threshold = int(seconds * RATE * 2)
        self.minimum = int(min_tail * RATE * 2)
        self.buffer = bytearray()
        self.start = None
        self.end = None

    def feed(self, packet: AudioPacket) -> list[AudioWindow]:
        results = []
        if self.end is not None and abs(packet.start - self.end) > 2.0:
            results.extend(self.flush())
        if self.start is None:
            self.start = packet.start
        self.end = packet.end
        self.buffer.extend(packet.data)
        if len(self.buffer) >= self.threshold:
            results.extend(self.flush())
        return results

    def flush(self) -> list[AudioWindow]:
        if len(self.buffer) < self.minimum or self.start is None or self.end is None:
            self.clear()
            return []
        window = AudioWindow(bytes(self.buffer), self.start, self.end)
        self.clear()
        return [window]

    def clear(self) -> None:
        self.buffer.clear()
        self.start = None
        self.end = None


class WhisperEngine:
    """Load the selected faster-whisper model lazily on the first window."""

    def __init__(self, loader: Callable | None = None):
        self.model_name = os.getenv('VKN_ASR_MODEL', 'base').strip() or 'base'
        self.device = os.getenv('VKN_ASR_DEVICE', 'cpu').strip() or 'cpu'
        self.compute_type = os.getenv('VKN_ASR_COMPUTE', 'int8').strip() or 'int8'
        self.language = os.getenv('VKN_ASR_LANGUAGE', 'auto').strip() or 'auto'
        self._model = None
        self._loader = loader
        self.loaded = False

    def _ensure(self):
        if self._model is None:
            if self._loader is None:
                from faster_whisper import WhisperModel
                self._loader = WhisperModel
            print(f'[VKN] 载入本地语音模型 {self.model_name}（首次需下载模型文件）...',flush=True)
            self._model = self._loader(self.model_name, device=self.device, compute_type=self.compute_type)
            print('[VKN] 语音模型已就绪',flush=True)
            self.loaded = True
        return self._model

    def transcribe(self, window: AudioWindow) -> list[dict]:
        arr = np.frombuffer(window.data, dtype='<i2').astype(np.float32) / 32768.0
        if not arr.size or float(np.sqrt(np.mean(arr*arr))) < 0.003:
            return []
        model = self._ensure()
        requested_language = None if self.language == 'auto' else self.language
        segments, _info = model.transcribe(
            arr, beam_size=1, best_of=1, language=requested_language,
            condition_on_previous_text=False, vad_filter=False,
            no_speech_threshold=0.55, compression_ratio_threshold=2.5,
            word_timestamps=False,
        )
        duration_audio = arr.size / RATE
        video_duration = max(window.end-window.start, 0.001)
        out = []
        for segment in segments:
            text = ' '.join(str(segment.text).split())
            if not text or len(text) > 1200:
                continue
            if float(getattr(segment, 'no_speech_prob', 0)) > 0.78:
                continue
            start_offset = max(0, min(duration_audio, float(segment.start)))
            end_offset = max(start_offset, min(duration_audio, float(segment.end)))
            t = max(0.0, window.start + video_duration * start_offset / duration_audio)
            out.append({'time': round(t, 2), 'end': round(window.start + video_duration * end_offset / duration_audio, 2), 'text': text})
        return out
