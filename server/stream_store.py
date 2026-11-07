"""Durable audio inbox and result outbox. No queue-full drop policy.

Only acknowledged data may be removed from the browser. Acknowledgements follow
SQLite commits. ASR results and the processed watermark are committed together.
PCM older than the overlap context is deleted only after successful ASR.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time
from .stream_protocol import Packet, AUDIO, BOUNDARY, FINISH, RATE

SESSION_RE = re.compile(r'^[a-f0-9]{32}$')

@dataclass
class Job:
    session: str
    packets: list[Packet]
    commit_seq: int
    owner_start: float
    owner_end: float
    options: dict
    context: str
    final: bool = False
    reset: bool = False
    speaker_state: dict = field(default_factory=dict)

    @property
    def pcm(self):
        return b''.join(p.pcm for p in self.packets)

    def media_time(self, audio_time: float) -> float:
        offset = 0.0
        for p in self.packets:
            if audio_time <= offset + p.duration + 1e-6:
                f = max(0.0, min(1.0, (audio_time - offset) / max(p.duration, 1e-6)))
                return p.start + (p.end - p.start) * f
            offset += p.duration
        return self.packets[-1].end if self.packets else 0.0


def normalize_options(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    lang = str(raw.get('language', 'auto')).strip().lower()
    if lang not in ('auto','zh','en','ja','ko','fr','de','es','ru','it','pt','ar','hi'):
        lang = 'auto'
    model = str(raw.get('textModel', 'qwen2.5:3b')).strip()
    if not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,100}', model) or 'cloud' in model.lower():
        model = 'qwen2.5:3b'
    return {'language':lang, 'translate':raw.get('translate', True) is not False,
            'correct':raw.get('correct', False) is True,
            'chunkSeconds':int(raw.get('chunkSeconds',12)) if str(raw.get('chunkSeconds',12)) in ('6','12','18') else 12,
            'textModel':model, 'hotwords':str(raw.get('hotwords',''))[:600],
            'title':str(raw.get('title',''))[:240], 'diarize':raw.get('diarize') is True,
            'maxSpeakers':int(raw['maxSpeakers']) if str(raw.get('maxSpeakers','')) in ('2','3','4','5','6','7','8') else 6}


class StreamStore:
    def __init__(self, path: Path | str, max_bytes=256*1024*1024, min_free=128*1024*1024):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.max_bytes, self.min_free = max_bytes, min_free
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY, video_key TEXT NOT NULL, options TEXT NOT NULL,
          received INTEGER NOT NULL DEFAULT 0, processed INTEGER NOT NULL DEFAULT 0,
          finished INTEGER NOT NULL DEFAULT 0, closed INTEGER NOT NULL DEFAULT 0,
          updated REAL NOT NULL, error TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
          retry_at REAL NOT NULL DEFAULT 0, boundary INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS packets (
          session TEXT NOT NULL, seq INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL,
          flag INTEGER NOT NULL, pcm BLOB, digest TEXT NOT NULL,
          PRIMARY KEY(session,seq));
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS event_session ON events(session,id);
        CREATE TABLE IF NOT EXISTS segments (
          id TEXT PRIMARY KEY, session TEXT NOT NULL, payload TEXT NOT NULL,
          text_state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
          retry_at REAL NOT NULL DEFAULT 0, created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS segment_session ON segments(session,created);
        ''')
        # Additive migration: old recordings/queues remain readable.
        if 'speaker_state' not in {r[1] for r in self.db.execute('PRAGMA table_info(sessions)')}:
            self.db.execute("ALTER TABLE sessions ADD COLUMN speaker_state TEXT NOT NULL DEFAULT '{}'")
        self.db.commit()

    def close(self):
        self.db.close()

    def session(self, sid):
        row = self.db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
        return dict(row) if row else None

    def open(self, sid, video_key, options):
        if not SESSION_RE.fullmatch(sid) or not isinstance(video_key,str) or not 0 < len(video_key) < 400:
            raise ValueError('会话标识非法')
        old = self.session(sid)
        if old:
            if old['video_key'] != video_key:
                raise ValueError('同一会话不能切换视频')
            return old
        with self.db:
            self.db.execute('INSERT INTO sessions(id,video_key,options,updated) VALUES(?,?,?,?)',
                            (sid, video_key, json.dumps(normalize_options(options), ensure_ascii=False), time.time()))
        return self.session(sid)

    def receive(self, sid, p: Packet):
        s = self.session(sid)
        if not s:
            raise ValueError('会话不存在')
        digest = hashlib.sha256(p.encode()).hexdigest()
        if p.seq <= s['received']:
            old = self.db.execute('SELECT digest FROM packets WHERE session=? AND seq=?',(sid,p.seq)).fetchone()
            if not old or old['digest'] != digest:
                raise ValueError('相同音频序号的内容不一致；停止重试以保护记录')
            return s['received']
        if s['closed']:
            raise ValueError('已结束会话不能继续写入，请开始新会话')
        if p.seq != s['received'] + 1:
            raise ValueError('音频序号不连续，请从最后确认序号重新发送')
        used = self.db.execute('SELECT COALESCE(SUM(LENGTH(pcm)),0) FROM packets').fetchone()[0]
        if p.pcm and (used + len(p.pcm) > self.max_bytes or shutil.disk_usage(self.path.parent).free < self.min_free):
            raise BufferError('本地音频缓存接近容量或磁盘不足；暂停视频，未确认音频仍在浏览器缓存')
        with self.db:
            self.db.execute('INSERT INTO packets VALUES(?,?,?,?,?,?,?)',
                            (sid,p.seq,p.start,p.end,p.flag,p.pcm,digest))
            self.db.execute('UPDATE sessions SET received=?, closed=?, updated=? WHERE id=?',
                            (p.seq, int(p.flag == FINISH), time.time(), sid))
        return p.seq

    def _packets(self, sid, after=0, limit=120):
        rows = self.db.execute('SELECT * FROM packets WHERE session=? AND seq>? ORDER BY seq LIMIT ?',
                               (sid, after, limit)).fetchall()
        return [Packet(r['seq'],r['start'],r['end'],r['flag'],bytes(r['pcm'] or b'')) for r in rows]

    def next_job(self, sid, hop=None, overlap=None):
        s = self.session(sid)
        if not s or s['finished'] or s['retry_at'] > time.time():
            return None
        options = normalize_options(json.loads(s['options']))
        # 12s default is a latency/linguistic-context tradeoff, not a guarantee.
        hop=float(options['chunkSeconds']) if hop is None else float(hop)
        overlap=(1.2 if hop<=6 else 2.4) if overlap is None else float(overlap)
        future = self._packets(sid, s['processed'], limit=180)
        if not future:
            return None
        if future[0].flag != AUDIO:
            return Job(sid,[],future[0].seq,0,0,options,'',final=future[0].flag==FINISH,reset=True)
        group=[]; ended=False; duration=0.0
        for p in future:
            if p.flag != AUDIO:
                ended=True; break
            # An undeclared time jump is treated as a boundary rather than joined.
            if group and abs(p.start-group[-1].end) > .8:
                ended=True; break
            group.append(p); duration+=p.duration
            if duration >= hop+overlap-1e-5:
                break
        if not group or (duration < hop+overlap-1e-5 and not ended):
            return None
        own=[]; own_duration=0.0
        for p in group:
            if own_duration >= hop-1e-5:
                break
            own.append(p); own_duration+=p.duration
        if ended and duration <= hop+overlap+1e-5:
            own=group; own_duration=duration
        left=[]; ld=0.0
        rows=self.db.execute('SELECT * FROM packets WHERE session=? AND seq<=? AND seq>? ORDER BY seq DESC LIMIT 20',
                             (sid,s['processed'],s['boundary'])).fetchall()
        for r in rows:
            if r['flag'] != AUDIO or not r['pcm']:
                break
            p=Packet(r['seq'],r['start'],r['end'],r['flag'],bytes(r['pcm']))
            if (not left and abs(p.end-group[0].start)>.8) or (left and abs(p.end-left[-1].start)>.8):
                break
            left.append(p); ld+=p.duration
            if ld >= overlap-1e-5:
                break
        left.reverse()
        previous=self.db.execute('SELECT payload FROM segments WHERE session=? ORDER BY created DESC LIMIT 3',(sid,)).fetchall()
        context=' '.join(json.loads(r[0]).get('original','') for r in reversed(previous))[-500:]
        if not left:
            context=''
        return Job(sid,left+group,own[-1].seq,ld,ld+own_duration,options,context,
                   speaker_state=json.loads(s.get('speaker_state') or '{}'))

    def _event(self, sid, payload):
        self.db.execute('INSERT INTO events(session,payload) VALUES(?,?)',
                        (sid,json.dumps(payload,ensure_ascii=False)))

    def commit(self, job: Job, segments: list[dict]):
        """Results + watermark: either both survive a crash, or neither does."""
        with self.db:
            if job.packets:
                self.db.execute('UPDATE sessions SET speaker_state=? WHERE id=?',
                                (json.dumps(job.speaker_state),job.session))
            for i, item in enumerate(segments):
                seg_id=f'{job.session}:{job.commit_seq}:{i}'
                item={**item,'contextEpoch':self.session(job.session)['boundary'],
                      'verificationStatus':item.get('verificationStatus','machine_unverified'),
                      'id':seg_id,'revision':1,'source':'local-asr',
                      'original':item['text'],'corrected':'','translation':'','translationStatus':'off',
                      'correctionStatus':'off','textStatus':'done'}
                foreign = item.get('language') not in ('zh','yue')
                needs=(foreign and job.options['translate']) or job.options['correct']
                if foreign and job.options['translate']:
                    item['translationStatus']='pending'
                if job.options['correct']:
                    item['correctionStatus']='pending'
                item['textStatus']='pending' if needs else 'done'
                self.db.execute('INSERT INTO segments(id,session,payload,text_state,created) VALUES(?,?,?,?,?)',
                                (seg_id,job.session,json.dumps(item,ensure_ascii=False),'pending' if needs else 'done',time.time()))
                self._event(job.session,{'type':'segment',**item})
            self.db.execute('UPDATE sessions SET processed=?,finished=?,boundary=CASE WHEN ? THEN ? ELSE boundary END,error=\'\',attempts=0,retry_at=0,updated=? WHERE id=?',
                            (job.commit_seq,int(job.final),job.reset,job.commit_seq,time.time(),job.session))
            # Keep >2s of left context for the next overlapped inference window.
            keep=0.0; cutoff=job.commit_seq
            for p in reversed(job.packets):
                if p.seq > job.commit_seq: continue
                cutoff=p.seq; keep+=p.duration
                if keep>=2.4:break
            if job.reset:cutoff=job.commit_seq+1
            self.db.execute('UPDATE packets SET pcm=NULL WHERE session=? AND seq<?',(job.session,cutoff))
            if job.final:
                self._event(job.session,{'type':'done','message':'录音已停止；所有已缓存音频已转写。中文翻译/纠错如仍排队会继续补齐。'})

    def fail(self, sid, message):
        s=self.session(sid); tries=s['attempts']+1
        with self.db:
            self.db.execute('UPDATE sessions SET attempts=?,retry_at=?,error=? WHERE id=?',
                            (tries,time.time()+min(60,2**min(tries,6)),str(message)[:300],sid))
            self._event(sid,{'type':'warning','message':'识别失败，音频保留并自动重试：'+str(message)[:240]})

    def pending_sessions(self):
        return [r[0] for r in self.db.execute('SELECT id FROM sessions WHERE finished=0 AND received>processed ORDER BY updated')]

    def events(self, sid, after=0, limit=128):
        return [{'eventId':r['id'],**json.loads(r['payload'])} for r in self.db.execute(
            'SELECT id,payload FROM events WHERE session=? AND id>? ORDER BY id LIMIT ?', (sid,after,limit))]

    def stats(self, sid):
        s=self.session(sid)
        pending=self.db.execute('SELECT COALESCE(SUM(LENGTH(pcm)),0) FROM packets WHERE session=? AND seq>?',(sid,s['processed'])).fetchone()[0]
        text_pending=self.db.execute("SELECT COUNT(*) FROM segments WHERE session=? AND text_state='pending'",(sid,)).fetchone()[0]
        text_failed=self.db.execute("SELECT COUNT(*) FROM segments WHERE session=? AND text_state='failed'",(sid,)).fetchone()[0]
        return {'received':s['received'],'processed':s['processed'],'pendingSeconds':round(pending/(RATE*2),1),
                'textPending':text_pending,'textFailed':text_failed,'finished':bool(s['finished']),'error':s['error']}

    def next_text(self):
        r=self.db.execute("SELECT * FROM segments WHERE text_state='pending' AND retry_at<=? ORDER BY created LIMIT 1",(time.time(),)).fetchone()
        if not r:return None
        return {**dict(r),'item':json.loads(r['payload']),'options':normalize_options(json.loads(self.session(r['session'])['options']))}

    def text_context(self, row):
        """Only nearby raw ASR, never an old translation or generated summary.

        Lookahead is opportunistic: it does not hold up live text indefinitely.
        Stop at time jumps, recording boundaries, or an uncertain source.
        """
        current=row['item']; epoch=current.get('contextEpoch',0)
        before=self.db.execute('SELECT payload FROM segments WHERE session=? AND created<? ORDER BY created DESC LIMIT 3',
            (row['session'],row['created'])).fetchall()
        after=self.db.execute('SELECT payload FROM segments WHERE session=? AND created>? ORDER BY created LIMIT 2',
            (row['session'],row['created'])).fetchall()
        def collect(rows, backwards):
            texts=[]; edge=float(current.get('time',0) if backwards else current.get('end',current.get('time',0)))
            for r in rows:
                c=json.loads(r[0]); a=float(c.get('time',0)); b=float(c.get('end',a))
                gap=edge-b if backwards else a-edge
                if c.get('contextEpoch',0)!=epoch or gap<-.5 or gap>3 or c.get('needsReview'):break
                texts.append(c.get('original',''))
                edge=a if backwards else b
            if backwards:texts.reverse()
            return ' '.join(texts)[:600]
        return {'previous':collect(before,True),'following':collect(after,False)}

    def finish_text(self, row, item, failure=None):
        tries=row['attempts']+(1 if failure else 0)
        status=('failed' if tries>=3 else 'pending') if failure else 'done'
        item={**item,'textStatus':status,'revision':row['item'].get('revision',1)+1}
        with self.db:
            self.db.execute('UPDATE segments SET payload=?,text_state=?,attempts=?,retry_at=? WHERE id=?',
                            (json.dumps(item,ensure_ascii=False),status,tries,time.time()+min(120,15*tries) if failure else 0,row['id']))
            self._event(row['session'],{'type':'segment',**item})

    def retry(self, sid):
        with self.db:
            self.db.execute('UPDATE sessions SET retry_at=0,attempts=0,error=\'\' WHERE id=?',(sid,))
            self.db.execute("UPDATE segments SET text_state='pending',attempts=0,retry_at=0 WHERE session=? AND text_state='failed'",(sid,))

    def clean(self, days=7):
        """Only completed sessions with no pending/failed text are auto-expired."""
        rows=self.db.execute("SELECT id FROM sessions WHERE finished=1 AND updated<? AND id NOT IN (SELECT session FROM segments WHERE text_state!='done')",(time.time()-days*86400,)).fetchall()
        with self.db:
            for r in rows:
                for table in ('packets','segments','events'):
                    self.db.execute(f'DELETE FROM {table} WHERE session=?',(r[0],))
                self.db.execute('DELETE FROM sessions WHERE id=?',(r[0],))
        return len(rows)
