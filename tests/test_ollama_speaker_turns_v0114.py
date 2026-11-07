"""Ollama no-word-timestamp diarization: synthetic speech and fake speaker vectors.

Tests avoid installing/loading sherpa, downloading models or claiming diarization
accuracy. They check identity *claims*, audio ownership and durable retry safety.
"""
from __future__ import annotations
import json
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np
from server.stream_protocol import Packet, RATE, AUDIO
from server.stream_store import Job, StreamStore, normalize_options
from server.speaker import SpeakerAnnotator, acoustic_regions, slice_audio_job
from server.qwen_protocol import ASRBackendError

SID='a'*32

def audio(seconds=6):
    # Non-silent unique samples make ownership and subchunk order observable.
    samples=(np.arange(int(RATE*seconds),dtype=np.int32)%30000+100).astype('<i2')
    return samples.tobytes()

def job(pcm=None):
    pcm=pcm if pcm is not None else audio()
    return Job(SID,[Packet(1,100,100+len(pcm)/(RATE*2),AUDIO,pcm)],1,0,len(pcm)/(RATE*2),
               normalize_options({'diarize':True,'translate':False,'maxSpeakers':6}),'')

class FakeASR:
    backend_name='ollama-qwen3-asr'
    def __init__(self,fail_call=0):self.calls=[];self.fail_call=fail_call
    def transcribe_job(self,part):
        self.calls.append((part.pcm,part.media_time(0),part.media_time(part.owner_end)))
        if self.fail_call and len(self.calls)==self.fail_call:
            raise ASRBackendError('ASR_OLLAMA_SERVER_ERROR','fake failure')
        return [{'time':round(part.media_time(0),3),'end':round(part.media_time(part.owner_end),3),
                '_audioStart':0,'_audioEnd':part.owner_end,'_words':[],
                'text':f'发言{len(self.calls)}','language':'zh','asrTiming':'audio_window',
                'needsReview':True,'qualityFlags':['word_timestamps_missing'],
                'reviewReason':'没有可靠词级时间戳，按音频窗口记录；不强行分配说话人'}]

class SpeakerBackend:
    def __init__(self,turns,vectors):self.turns=turns;self.vectors=vectors;self.calls=0
    def analyze(self,pcm):self.calls+=1;return self.turns,self.vectors

V0=np.array([1.,0.,0.],dtype=np.float32)
V1=np.array([0.,1.,0.],dtype=np.float32)

class Tests(unittest.TestCase):
    def test_one_dominant_voice_keeps_single_model_request_but_names_speaker(self):
        backend=SpeakerBackend([{'start':.15,'end':5.8,'local':0}],{0:(V0,5.65)})
        j=job();model=FakeASR()
        result=SpeakerAnnotator(lambda:backend).transcribe_and_annotate(j,model)
        self.assertEqual(len(model.calls),1)
        self.assertEqual(result[0]['speakerId'],SID+':spk1')
        self.assertEqual(result[0]['speakerStatus'],'estimated')
        self.assertEqual(result[0]['speakerTiming'],'acoustic_turn')
        self.assertFalse('_words' in result[0])
        self.assertIn('word_timestamps_missing',result[0]['qualityFlags'])
        self.assertEqual(len(j.speaker_state['profiles']),1)

    def test_two_voice_turns_have_two_distinct_transcriptions_and_no_fake_words(self):
        b=SpeakerBackend([{'start':0.,'end':3.,'local':0},{'start':3.,'end':6.,'local':1}],
                         {0:(V0,3.),1:(V1,3.)})
        j=job();e=FakeASR();r=SpeakerAnnotator(lambda:b).transcribe_and_annotate(j,e)
        self.assertEqual(len(e.calls),2)
        self.assertEqual(b''.join(x[0] for x in e.calls),j.pcm)
        self.assertEqual([(x['time'],x['end']) for x in r],[(100.,103.),(103.,106.)])
        self.assertEqual([x['text'] for x in r],['发言1','发言2'])
        self.assertEqual([x['speakerId'] for x in r],[SID+':spk1',SID+':spk2'])
        self.assertTrue(all(x['speakerStatus']=='estimated' for x in r))
        self.assertFalse(any('_words' in x for x in r))

    def test_cross_window_speaker_profile_survives_changed_local_ids(self):
        j=job();left=SpeakerBackend([{'start':0.,'end':3.,'local':0},
                                   {'start':3.,'end':6.,'local':1}],{0:(V0,3.),1:(V1,3.)})
        first=SpeakerAnnotator(lambda:left).transcribe_and_annotate(j,FakeASR())
        swapped=SpeakerBackend([{'start':0.,'end':3.,'local':9},
                                {'start':3.,'end':6.,'local':3}],{9:(V1,3.),3:(V0,3.)})
        another=job();another.speaker_state=j.speaker_state
        second=SpeakerAnnotator(lambda:swapped).transcribe_and_annotate(another,FakeASR())
        self.assertEqual([r['speakerId'] for r in second],
                         [first[1]['speakerId'],first[0]['speakerId']])
        self.assertEqual(len(another.speaker_state['profiles']),2)

    def test_audio_overlap_not_duplicated_and_not_attributed(self):
        # The overlapped second is recognized ONCE with no single-speaker claim.
        b=SpeakerBackend([{'start':0.,'end':3.5,'local':0},
                          {'start':2.5,'end':6.,'local':1}],
                         {0:(V0,2.5),1:(V1,2.5)})
        j=job();e=FakeASR();r=SpeakerAnnotator(lambda:b).transcribe_and_annotate(j,e)
        self.assertEqual(b''.join(x[0] for x in e.calls),j.pcm)
        self.assertEqual([x['speakerStatus'] for x in r],['estimated','overlap','estimated'])
        self.assertEqual(r[1]['speakerId'],'')
        self.assertEqual(r[1]['end']-r[1]['time'],1.)

    def test_unknown_audio_region_is_transcribed_not_deleted(self):
        b=SpeakerBackend([{'start':0.,'end':2.,'local':0},
                          {'start':3.,'end':6.,'local':1}],{0:(V0,2.),1:(V1,3.)})
        j=job();e=FakeASR();r=SpeakerAnnotator(lambda:b).transcribe_and_annotate(j,e)
        self.assertEqual(b''.join(x[0] for x in e.calls),j.pcm)
        self.assertEqual([x['speakerStatus'] for x in r],['estimated','uncertain','estimated'])
        self.assertEqual(r[1]['time'],102.);self.assertEqual(r[1]['end'],103.)

    def test_empty_speech_piece_reverts_to_full_audio_without_discarding_content(self):
        class EmptySecond(FakeASR):
            def transcribe_job(self, part):
                out=super().transcribe_job(part)
                return [] if len(self.calls)==2 else out
        b=SpeakerBackend([{'start':0.,'end':3.,'local':0},
                          {'start':3.,'end':6.,'local':1}],{0:(V0,3.),1:(V1,3.)})
        e=EmptySecond();j=job()
        rows=SpeakerAnnotator(lambda:b).transcribe_and_annotate(j,e)
        self.assertEqual(len(e.calls),3)   # two parts, then one complete window
        self.assertEqual(e.calls[-1][0],j.pcm)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['speakerStatus'],'uncertain')
        self.assertEqual(j.speaker_state,{})

    def test_quick_voice_changes_fall_back_without_guessing(self):
        turns=[{'start':0.,'end':2.9,'local':0},
               {'start':2.9,'end':3.05,'local':1},
               {'start':3.05,'end':6,'local':0}]
        b=SpeakerBackend(turns,{0:(V0,5.85),1:(V1,.15)})
        j=job();e=FakeASR();r=SpeakerAnnotator(lambda:b).transcribe_and_annotate(j,e)
        self.assertEqual(len(e.calls),1)
        self.assertEqual(r[0]['speakerStatus'],'uncertain')
        self.assertEqual(r[0].get('speakerId',''),'')

    def test_small_coverage_is_uncertain_not_misidentified(self):
        b=SpeakerBackend([{'start':0.,'end':2.,'local':0}],{0:(V0,2.)})
        r=SpeakerAnnotator(lambda:b).transcribe_and_annotate(job(),FakeASR())
        self.assertEqual(r[0]['speakerStatus'],'uncertain')
        self.assertEqual(r[0]['speakerId'],'')

    def test_unavailable_speaker_model_still_transcribes_all_audio(self):
        def missing():raise RuntimeError('models not installed')
        j=job();e=FakeASR();r=SpeakerAnnotator(missing).transcribe_and_annotate(j,e)
        self.assertEqual(len(e.calls),1)
        self.assertEqual(r[0]['speakerStatus'],'unavailable')
        self.assertEqual(j.speaker_state,{})

    def test_later_piece_failure_does_not_commit_cursors_or_voice_profiles(self):
        b=SpeakerBackend([{'start':0.,'end':3.,'local':0},{'start':3.,'end':6.,'local':1}],
                         {0:(V0,3.),1:(V1,3.)})
        j=job();e=FakeASR(fail_call=2)
        with tempfile.TemporaryDirectory() as td:
            store=StreamStore(Path(td)/'raw.sqlite3',min_free=0)
            try:
                store.open(SID,'demo',j.options);store.receive(SID,j.packets[0])
                with self.assertRaises(ASRBackendError):
                    SpeakerAnnotator(lambda:b).transcribe_and_annotate(j,e)
                self.assertEqual(j.speaker_state,{})
                self.assertEqual(store.session(SID)['processed'],0)
                self.assertEqual(store.session(SID)['speaker_state'],'{}')
                self.assertEqual(store._packets(SID)[0].pcm,j.pcm)
                self.assertEqual(store.events(SID),[])
            finally:store.close()

    def test_atomic_storage_of_split_speaker_records_and_watermark(self):
        b=SpeakerBackend([{'start':0.,'end':3.,'local':0},{'start':3.,'end':6.,'local':1}],
                         {0:(V0,3.),1:(V1,3.)})
        j=job();r=SpeakerAnnotator(lambda:b).transcribe_and_annotate(j,FakeASR())
        with tempfile.TemporaryDirectory() as td:
            store=StreamStore(Path(td)/'raw.sqlite3',min_free=0)
            try:
                store.open(SID,'demo',j.options);store.receive(SID,j.packets[0]);store.commit(j,r)
                self.assertEqual(store.session(SID)['processed'],1)
                self.assertEqual(len(json.loads(store.session(SID)['speaker_state'])['profiles']),2)
                rows=[x for x in store.events(SID) if x['type']=='segment']
                self.assertEqual([x['speakerId'] for x in rows],[SID+':spk1',SID+':spk2'])
            finally:store.close()

    def test_overlap_context_only_owns_new_audio_and_media_time(self):
        first=Packet(1,100,102,AUDIO,audio(2))
        second=Packet(2,104,107,AUDIO,audio(3))
        j=Job(SID,[first,second],2,2.,5.,normalize_options({'diarize':True,'translate':False}), '')
        b=SpeakerBackend([{'start':0.,'end':2.9,'local':0},
                          {'start':2.9,'end':5.,'local':1}],{0:(V0,2.9),1:(V1,2.1)})
        e=FakeASR();out=SpeakerAnnotator(lambda:b).transcribe_and_annotate(j,e)
        self.assertEqual(b''.join(x[0] for x in e.calls),second.pcm)
        self.assertEqual([(x['time'],x['end']) for x in out],[(104.,104.9),(104.9,107.)])

    def test_legacy_whisper_keeps_timestamp_based_annotator(self):
        class Legacy(FakeASR):backend_name='faster-whisper'
        b=SpeakerBackend([{'start':0,'end':6.,'local':0}],{0:(V0,6.)})
        j=job();e=Legacy()
        r=SpeakerAnnotator(lambda:b).transcribe_and_annotate(j,e)
        self.assertEqual(len(e.calls),1)
        self.assertEqual(r[0]['speakerStatus'],'uncertain')  # fake Legacy has no word timestamps

    def test_partition_and_partial_packet_clock(self):
        a=Packet(1,10.,12.,AUDIO,audio(2))
        b=Packet(2,12.,18.,AUDIO,audio(2))  # accelerated playback media clock
        j=Job(SID,[a,b],2,0.,4.,normalize_options({'diarize':True}),'')
        child=slice_audio_job(j,1.5,2.5)
        self.assertEqual(child.pcm,j.pcm[int(1.5*RATE)*2:int(2.5*RATE)*2])
        self.assertAlmostEqual(child.media_time(0),11.5)
        self.assertAlmostEqual(child.media_time(child.owner_end),13.5)
        segs=acoustic_regions([{'start':0,'end':3,'local':0},{'start':2,'end':4,'local':1}],0,4)
        self.assertEqual(segs,[(0,2,0,'speech'),(2,3,None,'overlap'),(3,4,1,'speech')])

if __name__=='__main__':unittest.main()
