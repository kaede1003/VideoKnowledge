import os
import pathlib
import struct
import sys
import unittest
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from server.asr_core import AudioBuffer, AudioWindow, WhisperEngine, decode_audio_packet


def packet(start=10.0, end=10.5, duration=0.5, amp=5000):
    audio = np.full(int(16000 * duration), amp, dtype='<i2').tobytes()
    return b'VKN2' + struct.pack('<dd', start, end) + audio


class TestPacketProtocol(unittest.TestCase):
    def test_valid_packet(self):
        value=decode_audio_packet(packet(12,12.5))
        self.assertEqual(value.start, 12)
        self.assertAlmostEqual(value.duration, .5)

    def test_reject_invalid_magic_size_and_time(self):
        baseline=packet()
        for bad in (b'BAD!' + baseline[4:], baseline[:-1], baseline[:20],
                    b'VKN2' + struct.pack('<dd', 5, 1) + baseline[20:],
                    b'VKN2' + struct.pack('<dd', float('nan'), 1) + baseline[20:]):
            with self.subTest(bad=bad[:24]):
                with self.assertRaises(ValueError):decode_audio_packet(bad)

    def test_reject_large_or_implausible_packets(self):
        with self.assertRaises(ValueError):decode_audio_packet(packet(0,30,duration=.5))
        with self.assertRaises(ValueError):decode_audio_packet(packet(0,3,duration=3))


class TestAudioBuffer(unittest.TestCase):
    def test_buffer_one_full_chunk(self):
        b=AudioBuffer(seconds=6)
        outputs=[]
        for i in range(12):
            outputs.extend(b.feed(decode_audio_packet(packet(i*.5,(i+1)*.5))))
        self.assertEqual(len(outputs),1)
        self.assertAlmostEqual(outputs[0].start,0)
        self.assertAlmostEqual(outputs[0].end,6)
        self.assertEqual(len(outputs[0].data),6*16000*2)
        self.assertFalse(b.flush())

    def test_seek_flushes_instead_of_merging(self):
        b=AudioBuffer(seconds=6)
        b.feed(decode_audio_packet(packet(0,.5)))
        b.feed(decode_audio_packet(packet(.5,1)))
        outputs=b.feed(decode_audio_packet(packet(301,301.5)))
        self.assertEqual(len(outputs),1)
        self.assertAlmostEqual(outputs[0].start,0)
        self.assertAlmostEqual(outputs[0].end,1)
        remaining=b.flush()
        self.assertEqual(len(remaining),0) # half-second below min_tail

    def test_short_silence_drops(self):
        b=AudioBuffer(seconds=6)
        b.feed(decode_audio_packet(packet(4,4.5)))
        self.assertFalse(b.flush())


class FakeWhisperModel:
    def __init__(self,*args,**kwargs):pass
    def transcribe(self,pcm,**kwargs):
        return iter([SimpleNamespace(text='人工样本语音', start=0.2, end=2.2, no_speech_prob=.1)]), None


class TestWhisperAdapter(unittest.TestCase):
    def test_timestamp_mapping_and_model_loader(self):
        engine=WhisperEngine(loader=FakeWhisperModel)
        window=AudioWindow(np.full(16000*2,2000,dtype='<i2').tobytes(),80,84)
        result=engine.transcribe(window)
        self.assertTrue(engine.loaded)
        self.assertEqual(result[0]['text'],'人工样本语音')
        self.assertAlmostEqual(result[0]['time'],80.4)
        self.assertAlmostEqual(result[0]['end'],84)

    def test_skip_silence_without_loading_model(self):
        engine=WhisperEngine(loader=FakeWhisperModel)
        result=engine.transcribe(AudioWindow(b'\0'*32000,0,1))
        self.assertEqual(result,[])
        self.assertFalse(engine.loaded)


if __name__=='__main__':unittest.main()
