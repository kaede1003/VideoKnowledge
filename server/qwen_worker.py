"""Isolated Qwen native Transformers worker. Private stdio, no HTTP listener.

Weights must already exist locally. No runtime downloads/remote Python. Only
installation explicitly fetches official repositories. This is windowed inference,
not vLLM/native token streaming. Stdout is reserved for the JSON protocol.
"""
from __future__ import annotations
import argparse
import base64
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
import time

from .qwen_protocol import (ASRBackendError, RATE, MAX_LINE, ALIGNED, decode_request,
                            language_code, lexical_map, align_words, select_owned)


class NativeQwenRuntime:
    def __init__(self, model_dir, aligner_dir, device='cuda:0'):
        # Never silently offload to CPU or download missing models during recording.
        os.environ['HF_HUB_OFFLINE']='1'
        os.environ['TRANSFORMERS_OFFLINE']='1'
        os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
        os.environ['TOKENIZERS_PARALLELISM']='false'
        import torch
        import numpy as np
        from transformers import AutoProcessor, AutoModelForMultimodalLM, AutoModelForTokenClassification
        self.torch,self.np=torch,np
        self.device=device
        if device.startswith('cuda'):
            if not torch.cuda.is_available():
                raise ASRBackendError('ASR_CUDA_UNAVAILABLE', 'Qwen profile requires a working CUDA PyTorch/driver')
            # A kernel check catches wheels that cannot execute on the installed GPU.
            check=torch.ones((8,8),device=device)
            _=check@check; torch.cuda.synchronize(); del check
            dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        else:
            dtype=torch.float32
        for directory in (model_dir,aligner_dir):
            if not Path(directory).is_dir():
                raise ASRBackendError('ASR_MODEL_MISSING', 'Run INSTALL_ALL.bat -Profile asr -AsrProfile qwen17')
        load={'local_files_only':True,'trust_remote_code':False}
        self.processor=AutoProcessor.from_pretrained(str(model_dir),**load)
        self.model=AutoModelForMultimodalLM.from_pretrained(str(model_dir),dtype=dtype,
            use_safetensors=True,attn_implementation='sdpa',**load).to(device).eval()
        self.aligner_processor=AutoProcessor.from_pretrained(str(aligner_dir),**load)
        self.aligner=AutoModelForTokenClassification.from_pretrained(str(aligner_dir),dtype=dtype,
            use_safetensors=True,attn_implementation='sdpa',**load).to(device).eval()
        self.dtype=dtype

    def transcribe(self, audio, language, hotwords, max_tokens=1024):
        kwargs={'audio':audio,'processor_kwargs':{'audio_kwargs':{'sampling_rate':RATE}}}
        if language: kwargs['language']=language
        if hotwords: kwargs['prompt']='Vocabulary: '+hotwords
        inputs=self.processor.apply_transcription_request(**kwargs).to(self.device,self.dtype)
        with self.torch.inference_mode():
            output=self.model.generate(**inputs,max_new_tokens=max_tokens,do_sample=False)
        ids=output[:,inputs['input_ids'].shape[1]:]
        eos=self.model.generation_config.eos_token_id
        eos=eos if isinstance(eos,list) else [eos]
        if ids.shape[-1]>=max_tokens and int(ids[0,-1]) not in eos:
            raise ASRBackendError('ASR_OUTPUT_TRUNCATED','audio retained; output token limit reached')
        parsed=self.processor.decode(ids,return_format='parsed')[0]
        if not isinstance(parsed,dict) or not isinstance(parsed.get('transcription'),str):
            raise ASRBackendError('ASR_DECODE_INVALID')
        return parsed['transcription'],parsed.get('language') or language or 'unknown'

    def align(self,audio,text,language):
        inputs,word_lists=self.aligner_processor.prepare_forced_aligner_inputs(
            audio=audio,transcript=text,language=language,processor_kwargs={'audio_kwargs':{'sampling_rate':RATE}})
        inputs=inputs.to(self.device,self.dtype)
        with self.torch.inference_mode():
            outputs=self.aligner(**inputs)
        return self.aligner_processor.decode_forced_alignment(
            logits=outputs.logits,input_ids=inputs['input_ids'],word_lists=word_lists,
            timestamp_token_id=self.aligner.config.timestamp_token_id)[0]

    def warmup(self):
        # Executes actual inference and alignment kernels. Synthetic input is NOT
        # a language accuracy test and its generated content is never saved.
        audio=self.np.zeros(RATE,dtype=self.np.float32)
        inputs=self.processor.apply_transcription_request(audio=audio).to(self.device,self.dtype)
        with self.torch.inference_mode():
            self.model.generate(**inputs,max_new_tokens=4,do_sample=False)
        self.align(audio,'test','English')
        return {'device':self.device,'dtype':str(self.dtype),
                'cuda':str(self.torch.version.cuda),'model_loaded':True,
                'synthetic_kernel_check':True,'accuracy_tested':False}


def recognize(runtime, data):
    pcm,a,b,language,hotwords=decode_request(data)
    np=runtime.np
    audio=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768.
    if not np.any(audio):
        return {'segments':[],'audio_seconds':len(audio)/RATE,'alignment':'silence'}
    start=time.monotonic()
    text,detected=runtime.transcribe(audio,language,hotwords)
    words=[]; precise=False; alignment_reason='unsupported_language'
    if text.strip() and language_code(detected) in ALIGNED:
        try:
            timestamps=runtime.align(audio,text,detected)
            words=align_words(text,timestamps,len(audio)/RATE)
            owned=select_owned(words,a,b)
            # Non-empty raw output entirely assigned outside the owner interval
            # is uncertain. Re-read the owned sound, never fabricate a timed word.
            if not owned: raise ASRBackendError('ASR_OWNER_ALIGNMENT_EMPTY')
            text=''.join(w['word'] for w in owned)
            words=owned; precise=True; alignment_reason='aligned_words'
        except Exception as exc:
            words=[]; alignment_reason=getattr(exc,'code',type(exc).__name__)
    if not precise:
        # Avoid emitting overlapped words twice when alignment is unavailable.
        # A supported but broken aligner is not replaced with uniform fake timing.
        core=audio[int(round(a*RATE)):int(round(b*RATE))]
        if a>1e-6 or b<len(audio)/RATE-1e-6:
            text,detected=runtime.transcribe(core,language,hotwords)
        flags=['word_timestamps_missing'] if text.strip() else []
        left,right=a,b
    else:
        flags=[]; left,right=words[0]['start'],words[-1]['end']
    # Flag repetition without filtering/removing original text.
    import re
    if re.search(r'(.{3,60}?)\1{4,}',text,re.S):
        flags.append('asr_repetition_suspected')
    segments=[{'text':text,'language':detected,'start':left,'end':right,
              'words':words,'flags':flags}] if text.strip() else []
    seconds=time.monotonic()-start
    return {'segments':segments,'audio_seconds':len(audio)/RATE,
            'recognition_seconds':round(seconds,3),'alignment':alignment_reason,
            'rtf':round(seconds/max(b-a,.001),3)}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-dir',required=True)
    p.add_argument('--aligner-dir',required=True)
    p.add_argument('--device',default='cuda:0')
    p.add_argument('--smoke',action='store_true')
    args=p.parse_args(argv)
    out=sys.stdout
    def send(value):
        out.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');out.flush()
    started=time.monotonic()
    try:
        with redirect_stdout(sys.stderr):
            runtime=NativeQwenRuntime(args.model_dir,args.aligner_dir,args.device)
            info=runtime.warmup() if args.smoke else {'device':runtime.device,'dtype':str(runtime.dtype)}
        send({'type':'ready','protocol':1,'load_seconds':round(time.monotonic()-started,3),**info})
        if args.smoke: return 0
    except Exception as exc:
        # No raw audio, transcripts or prompts in error output.
        send({'type':'fatal','code':getattr(exc,'code',type(exc).__name__)})
        return 1
    while True:
        line=sys.stdin.buffer.readline(MAX_LINE+1)
        if not line: break
        if len(line)>MAX_LINE or not line.endswith(b'\n'):
            send({'type':'fatal','code':'ASR_IPC_TOO_LARGE'}); return 1
        request_id=None
        try:
            data=json.loads(line)
            if not isinstance(data,dict): raise ASRBackendError('ASR_BAD_REQUEST')
            request_id=data.get('id')
            if data.get('op')=='close': break
            with redirect_stdout(sys.stderr): result=recognize(runtime,data)
            send({'id':request_id,'ok':True,**result})
        except Exception as exc:
            send({'id':request_id,'ok':False,'code':getattr(exc,'code',type(exc).__name__)})
    return 0

if __name__=='__main__':
    for s in (sys.stdout,sys.stderr):
        if hasattr(s,'reconfigure'): s.reconfigure(encoding='utf-8',errors='replace')
    raise SystemExit(main())
