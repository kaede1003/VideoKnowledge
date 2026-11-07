"""VKN5 ordered PCM transport. One sequence includes audio AND boundaries.

28 byte header: magic(4), sequence(uint32 LE), media start/end(float64 LE),
flags(uint32 LE). 0=audio, 1=boundary, 2=end. Audio is 16 kHz mono PCM16 LE.
The session id is negotiated in the JSON hello, not trusted from a URL.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import struct

RATE = 16000
HEADER = 28
AUDIO, BOUNDARY, FINISH = 0, 1, 2

@dataclass(frozen=True)
class Packet:
    seq: int
    start: float
    end: float
    flag: int
    pcm: bytes

    @property
    def duration(self):
        return len(self.pcm) / (RATE * 2)

    def encode(self):
        return struct.pack('<4sIddI', b'VKN5', self.seq, self.start, self.end, self.flag) + self.pcm


def decode(raw: bytes) -> Packet:
    if not isinstance(raw, bytes) or not HEADER <= len(raw) <= HEADER + RATE * 4:
        raise ValueError('音频包大小非法；每包最多2秒')
    magic, seq, start, end, flag = struct.unpack_from('<4sIddI', raw)
    if magic != b'VKN5':
        raise ValueError('需要同时升级扩展和本地服务到0.5版本')
    if not 1 <= seq <= 0xFFFFFFFF or flag not in (AUDIO, BOUNDARY, FINISH):
        raise ValueError('音频序号或控制类型非法')
    if not all(math.isfinite(v) and 0 <= v < 30 * 86400 for v in (start, end)) or start > end:
        raise ValueError('视频时间戳非法')
    pcm = raw[HEADER:]
    if len(pcm) % 2 or (flag == AUDIO and not pcm) or (flag != AUDIO and pcm):
        raise ValueError('音频包内容与类型不匹配')
    if flag == AUDIO and end - start > len(pcm) / (RATE * 2) * 4.5 + .75:
        raise ValueError('视频时间超出允许倍速')
    return Packet(seq, start, end, flag, pcm)
