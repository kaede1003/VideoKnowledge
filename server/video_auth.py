"""Per-attempt YouTube session data. Never read a browser database or write cookies.

Caller must obtain explicit consent. Values are transported via loopback JSON and
child stdin, used by a domain-scoped cookie jar, then references are released.
This is not secure memory erasure and cannot override platform access controls.
"""
from __future__ import annotations
import http.cookiejar
import json
import math
import re
import time
from urllib.parse import urlparse

DOMAINS = {'youtube.com', '.youtube.com', 'www.youtube.com', '.www.youtube.com', 'm.youtube.com', '.m.youtube.com'}
AUTH_NAMES = {'SAPISID', '__Secure-1PAPISID', '__Secure-3PAPISID', 'SID', 'LOGIN_INFO'}
MAX_COOKIE_BYTES = 64 * 1024

def youtube_url(url):
    u=urlparse(str(url))
    return u.scheme=='https' and u.hostname in {'youtube.com','www.youtube.com','m.youtube.com','youtu.be'} and not u.username and not u.password

def clean_cookies(raw, url, consent=False, now=None):
    if consent is not True:
        raise ValueError('VIDEO_AUTH_CONSENT: 必须单独同意本次使用YouTube登录状态')
    if not youtube_url(url):
        raise ValueError('VIDEO_AUTH_SCOPE: 登录状态仅用于YouTube视频')
    if not isinstance(raw,list) or not 1<=len(raw)<=128:
        raise ValueError('VIDEO_AUTH_EMPTY: 没有可用的YouTube登录状态，请在同一Edge配置中登录')
    # Bound before copying. Error messages deliberately omit names and values.
    if len(json.dumps(raw,ensure_ascii=False).encode('utf-8'))>MAX_COOKIE_BYTES:
        raise ValueError('VIDEO_AUTH_SIZE: 登录数据超过本次传输上限')
    now=time.time() if now is None else now
    out=[];seen=set()
    for c in raw:
        if not isinstance(c,dict) or c.get('partitionKey'):
            raise ValueError('VIDEO_AUTH_SCOPE: 不接受其他分区的登录状态')
        domain=c.get('domain');name=c.get('name');value=c.get('value');path=c.get('path','/')
        if domain not in DOMAINS or not isinstance(name,str) or not re.fullmatch(r'[!#$%&\'*+.^_`|~0-9A-Za-z-]{1,256}',name):
            raise ValueError('VIDEO_AUTH_SCOPE: 登录数据的站点范围无效')
        if not isinstance(value,str) or len(value)>8192 or any(ord(x)<32 or ord(x)>126 for x in value) or ';' in value:
            raise ValueError('VIDEO_AUTH_FORMAT: 登录数据格式无效')
        if not isinstance(path,str) or not path.startswith('/') or len(path)>1024 or any(ord(x)<32 for x in path):
            raise ValueError('VIDEO_AUTH_FORMAT: 登录数据路径无效')
        exp=c.get('expirationDate')
        if exp is not None:
            if not isinstance(exp,(int,float)) or isinstance(exp,bool) or not math.isfinite(exp):
                raise ValueError('VIDEO_AUTH_FORMAT: 登录数据期限无效')
            if exp<=now:continue
            exp=int(exp)
        key=(domain,path,name)
        if key in seen:continue
        seen.add(key)
        out.append({'domain':domain,'name':name,'value':value,'path':path,'secure':c.get('secure') is True,
                    'httpOnly':c.get('httpOnly') is True,'hostOnly':c.get('hostOnly',not domain.startswith('.')) is True,
                    'expirationDate':exp})
    if not out or not any(c['name'] in AUTH_NAMES for c in out):
        raise ValueError('VIDEO_AUTH_EMPTY: 未找到YouTube登录会话；普通访客Cookie不代表已登录')
    return out

def install_cookiejar(jar,cookies):
    for c in cookies:
        domain=c['domain'];specified=not c['hostOnly']
        jar.set_cookie(http.cookiejar.Cookie(version=0,name=c['name'],value=c['value'],port=None,port_specified=False,
            domain=domain,domain_specified=specified,domain_initial_dot=domain.startswith('.'),path=c['path'],path_specified=True,
            secure=c['secure'],expires=c['expirationDate'],discard=c['expirationDate'] is None,
            comment=None,comment_url=None,rest={'HttpOnly':None} if c['httpOnly'] else {},rfc2109=False))
