import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import numpy as np
from server.speaker import SpeakerAnnotator, unit, match_speakers, at_word, nonoverlap_regions
from server.stream_store import Job, StreamStore, normalize_options
from server.stream_protocol import Packet

SID='d'*32

def job():
    p=Packet(1,100,106,0,b'\x01\x00'*(16000*6))
    return Job(SID,[p],1,0,6,normalize_options({'diarize':True,'translate':False}),'')

def segment():
    words=[{'start':.1,'end':.8,'word':'这是'}, {'start':1.,'end':1.8,'word':'问题。'},
           {'start':3.1,'end':3.8,'word':'这是'}, {'start':4.,'end':4.8,'word':'回答。'}]
    return {'time':100.1,'end':104.8,'text':'这是问题。这是回答。','language':'zh','_words':words,'_audioStart':.1,'_audioEnd':4.8}

class Backend:
    def analyze(self,pcm):
        return [{'start':0,'end':2.5,'local':0},{'start':3,'end':5.5,'local':1}], {0:(np.array([1.,0.,0.]),2.5),1:(np.array([0.,1.,0.]),2.5)}

class SpeakerTests(unittest.TestCase):
    def test_opt_in_only(self):
        j=job();j.options['diarize']=False
        def forbidden():raise AssertionError('must not load a model')
        out=SpeakerAnnotator(forbidden).annotate(j,[segment()])
        self.assertNotIn('_words',out[0]);self.assertNotIn('speakerStatus',out[0]);self.assertEqual(out[0]['text'],segment()['text'])
    def test_split_without_losing_text(self):
        out=SpeakerAnnotator(Backend).annotate(job(),[segment()])
        self.assertEqual(len(out),2);self.assertEqual(''.join(x['text'] for x in out),segment()['text'])
        self.assertEqual(out[0]['speakerId'],SID+':spk1');self.assertEqual(out[1]['speakerId'],SID+':spk2')
        self.assertEqual(out[1]['time'],103.1);self.assertFalse(any('_words'in x for x in out))
    def test_local_ids_reordering_keeps_session_speakers(self):
        m,st=match_speakers({0:(np.array([1.,0.]),2),1:(np.array([0.,1.]),2)}, {})
        n,new=match_speakers({9:(np.array([0.,1.]),2),3:(np.array([1.,0.]),2)},st)
        self.assertEqual(m[0][0],n[3][0]);self.assertEqual(m[1][0],n[9][0]);self.assertEqual(len(new['profiles']),2)
    def test_one_to_one_ambiguous_not_merged(self):
        _,state=match_speakers({0:(np.array([1.,0.]),2)}, {})
        got,_=match_speakers({0:(np.array([1.,0.]),2),1:(unit([1.,.01]),2)},state)
        self.assertEqual(sum(x[0] is not None for x in got.values()),1)
    def test_short_unknown_not_registered(self):
        got,st=match_speakers({0:(np.array([1.,0.]),.9)}, {})
        self.assertIsNone(got[0][0]);self.assertEqual(st['profiles'],[])
    def test_cap_does_not_merge_overflow(self):
        _,st=match_speakers({0:(np.array([1.,0.,0.]),2),1:(np.array([0.,1.,0.]),2)}, {},2)
        got,st=match_speakers({2:(np.array([0.,0.,1.]),3)},st,2)
        self.assertIsNone(got[2][0]);self.assertEqual(len(st['profiles']),2)
    def test_overlap_and_boundary_remain_unknown(self):
        turns=[{'start':0,'end':2,'local':0},{'start':1,'end':3,'local':1}]
        self.assertIsNone(at_word(1.2,1.8,turns)[0]);self.assertEqual(nonoverlap_regions(turns[0],turns),[(0.,1.)])
    def test_no_words_no_whole_sentence_guess(self):
        s=segment();s['_words']=[]
        out=SpeakerAnnotator(Backend).annotate(job(),[s])
        self.assertEqual(out[0]['speakerStatus'],'uncertain');self.assertEqual(out[0]['text'],s['text'])
    def test_unavailable_does_not_drop_transcript(self):
        def unavailable():raise RuntimeError('missing optional dependency')
        out=SpeakerAnnotator(unavailable).annotate(job(),[segment()])
        self.assertEqual(out[0]['speakerStatus'],'unavailable');self.assertEqual(out[0]['text'],segment()['text'])
    def test_identity_is_recording_scoped(self):
        a=job();b=job();b.session='e'*32
        sa=SpeakerAnnotator(Backend).annotate(a,[segment()]);sb=SpeakerAnnotator(Backend).annotate(b,[segment()])
        self.assertNotEqual(sa[0]['speakerId'],sb[0]['speakerId'])
    def test_state_and_audio_watermark_commit_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'cache.db';store=StreamStore(path,min_free=0)
            store.open(SID,'yt:demo',job().options);j=job();store.receive(SID,j.packets[0])
            out=SpeakerAnnotator(Backend).annotate(j,[segment()]);store.commit(j,out);store.close()
            store=StreamStore(path,min_free=0);row=store.session(SID)
            self.assertEqual(row['processed'],1);self.assertEqual(len(json.loads(row['speaker_state'])['profiles']),2)
            event=store.events(SID)[0];self.assertEqual(event['speakerId'],SID+':spk1');store.close()
    def test_state_is_unchanged_before_commit(self):
        state={'profiles':[{'id':1,'vector':[1.,0.]}]}
        _,new=match_speakers({0:(unit([1.,.1]),3)},state)
        self.assertEqual(state['profiles'][0]['vector'],[1.,0.]);self.assertNotEqual(new,state)
    def test_legacy_database_gets_additive_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.db';store=StreamStore(path,min_free=0);store.open(SID,'test',{});store.close()
            con=sqlite3.connect(path);con.execute('ALTER TABLE sessions DROP COLUMN speaker_state');con.close()
            store=StreamStore(path,min_free=0);self.assertEqual(store.session(SID)['video_key'],'test');self.assertEqual(store.session(SID)['speaker_state'],'{}');store.close()
    def test_settings_strict_opt_in_and_bounded(self):
        self.assertFalse(normalize_options({'diarize':'yes'})['diarize']);self.assertEqual(normalize_options({'maxSpeakers':999})['maxSpeakers'],6)
    def test_bad_vector_rejected(self):
        self.assertIsNone(unit([0,0]));self.assertIsNone(unit([float('nan'),1]))

if __name__=='__main__':unittest.main()
