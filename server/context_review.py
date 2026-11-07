"""Validate model-proposed homophone edits. Never treat self-rated certainty as proof.
No LLM call here; only local structural/phonetic checks, no raw-cue mutation.
"""
from __future__ import annotations
from collections import Counter
import importlib.util
import json
import re
from fastapi import Request, HTTPException

ORIGIN = re.compile(r'^chrome-extension://[a-p]{32}$')
HANS = re.compile(r'^[\u3400-\u9fff]{1,10}$')
PROTECTED = re.compile(r'[0-9A-Za-z零〇一二三四五六七八九十百千万億亿兩两点點年月日号號%％]|不|没|沒|无|無|未|非|别|別|否|禁止|可能|也许|也許|或许|或許|大概|必须|必須|一定|如果|除非|只有|仅|僅')
NAME_CONTEXT = re.compile(r'(?:我叫|叫做|名叫|姓名|名字|先生|女士|老师|老師|教授|博士|医师|醫師|医生|醫生|品牌|型号|型號|地名|人名)')


def availability():
    yes = importlib.util.find_spec('pypinyin') is not None
    return {'available': yes, 'message': '同音校验组件可用；不代表内容正确' if yes else
            '未安装拼音校验组件，候选只提示不自动采用；运行 INSTALL_CONTEXT_REVIEW.bat 后重启服务'}


def phonetic_equal(before, after):
    from pypinyin import lazy_pinyin, Style
    return lazy_pinyin(before, style=Style.NORMAL) == lazy_pinyin(after, style=Style.NORMAL)


def valid_evidence(source,before,evidence):
    if not 8<=len(evidence)<=300 or not before:return False
    if evidence in source['text'] and before in evidence and evidence!=before:return True
    left=str(source.get('contextBefore',''))[-500:]
    right=str(source.get('contextAfter',''))[:500]
    joined=left+' '+source['text']+' '+right
    if source['text'].count(before)!=1:return False
    target=len(left)+1+source['text'].index(before)
    start=joined.find(evidence)
    while start>=0:
        if start<=target and start+len(evidence)>=target+len(before):return True
        start=joined.find(evidence,start+1)
    return False


def validate(data, checker=None):
    """No paths, system commands, model requests, or deletion. Input is capped."""
    cues = data.get('items')
    edits = data.get('edits')
    if not isinstance(cues, list) or len(cues) > 60 or not isinstance(edits, list) or len(edits) > 12:
        raise ValueError('REVIEW_FORMAT: 检查材料格式或数量超限')
    sources = {}
    for item in cues:
        if not isinstance(item, dict):
            continue
        ident, text = item.get('id'), item.get('text')
        if isinstance(ident, str) and len(ident) < 120 and isinstance(text, str) and len(text) <= 6000:
            sources[ident] = item
    if sum(len(x['text'])+len(str(x.get('contextBefore','')))+len(str(x.get('contextAfter',''))) for x in sources.values()) > 9000:
        raise ValueError('REVIEW_SIZE: 本批文字过长')
    can_check = checker is not None or availability()['available']
    checker = checker or phonetic_equal
    accepted, held, used = [], [], Counter()
    for item in edits:
        if not isinstance(item, dict):
            continue
        ident, before, after = str(item.get('id', '')), str(item.get('before', '')), str(item.get('after', ''))
        evidence, reason = str(item.get('evidence', ''))[:300], str(item.get('reason', ''))[:300]
        source = sources.get(ident)
        record = {'id': ident, 'before': before[:30], 'after': after[:30], 'evidence': evidence,
                  'reason': reason, 'status': 'needs_review', 'validation': ''}
        problem = ''
        try:
            confidence = float(item.get('confidence', 0))
        except (ValueError, TypeError):
            confidence = 0
        if not source:
            problem = '记录不属于本批'
        elif not HANS.fullmatch(before) or not HANS.fullmatch(after) or len(before) != len(after) or before == after:
            problem = '只允许等长中文短语替换，不允许扩写'
        elif source.get('manual') or source.get('uncertain'):
            problem = '人工稿或识别疑点只提示，不自动改写'
        elif source['text'].count(before) != 1:
            problem = '原短语不存在或出现多次，不能确定修改位置'
        elif not valid_evidence(source,before,evidence):
            problem = '没有包含本条目标词的连续上下文依据'
        elif not .92 <= confidence <= 1 or len(reason) < 8 or item.get('kind') != 'common_term':
            problem = '缺少充分的上下文理由，或属于姓名/数值等高风险项'
        elif PROTECTED.search(before.replace('未知','')) or PROTECTED.search(after.replace('未知','')):
            problem = '涉及数字、否定、范围或语气，保留原文'
        elif NAME_CONTEXT.search(evidence):
            problem = '可能涉及姓名、称谓或专名，保留原文'
        elif used[ident] >= 2:
            problem = '单句修改过多，保留后续候选供核对'
        elif not can_check:
            problem = '拼音校验组件未安装，未自动采用'
        else:
            try:
                if not checker(before, after):
                    problem = '拼音不一致，只能作为待核对候选'
            except Exception:
                problem = '拼音校验失败，未自动采用'
        if problem:
            record['validation'] = problem
            held.append(record)
        else:
            # Don't let two accepted edits consume overlapping source ranges.
            start = source['text'].index(before)
            overlap = any(x['id'] == ident and not (start+len(before) <= x['start'] or start >= x['end']) for x in accepted)
            if overlap:
                record['validation'] = '候选位置重叠，未自动采用';held.append(record);continue
            record.update(status='contextual', validation='通过结构与同音检查；尚未对照原音验证', start=start, end=start+len(before))
            accepted.append(record);used[ident] += 1
    return {'applied': accepted, 'held': held, 'phonetic_available': can_check,
            'warning': '只是上下文修订，不是原音核验；模型自评分不是准确率。'}


def attach_context_review_routes(app):
    @app.post('/text-review/validate')
    async def validate_route(request: Request):
        if not ORIGIN.fullmatch(request.headers.get('origin', '')):
            raise HTTPException(403, 'REVIEW_ORIGIN: 仅允许扩展请求')
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise HTTPException(415, 'REVIEW_JSON')
        raw = bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw) > 65536:
                raise HTTPException(413, 'REVIEW_SIZE')
        try:
            data = json.loads(raw)
            if not isinstance(data, dict): raise ValueError()
            return validate(data)
        except (ValueError, UnicodeError):
            raise HTTPException(400, 'REVIEW_FORMAT: 无效核对请求')
