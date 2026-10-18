"""Conservative password-guess throttling: Redis in production, bounded memory in test/dev."""
from __future__ import annotations
import os,time,threading,hashlib
from fastapi import HTTPException

_lock=threading.Lock()
_hits:dict[str,tuple[int,float]]={}

def throttle(raw_identity:str,limit:int=10,window:int=600):
    key='medtour:login:'+hashlib.sha256(raw_identity.encode()).hexdigest()
    env=os.getenv('APP_ENV','development')
    uri=os.getenv('REDIS_URL')
    if env=='production' and not uri:
        raise HTTPException(503,'Rate limiting unavailable')
    # Unit tests must use their isolated in-memory counter even when Docker
    # passes REDIS_URL from .env. Never share production/development Redis
    # login counters with the test suite.
    if uri and env!='test':
        try:
            import redis
            r=redis.Redis.from_url(uri,socket_connect_timeout=1,socket_timeout=2)
            count=r.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",1,key,window)
            if count>limit:raise HTTPException(429,'Too many login attempts')
            return
        except HTTPException:raise
        except Exception as exc:
            raise HTTPException(503,'Rate limiting unavailable') from exc
    # Only for development and unit tests; not distributed and not for production.
    now=time.monotonic()
    with _lock:
        if len(_hits)>4000:
            for k,(_,expiry) in list(_hits.items()):
                if expiry<=now:_hits.pop(k,None)
        count,expiry=_hits.get(key,(0,now+window))
        if expiry<=now:count,expiry=0,now+window
        count+=1;_hits[key]=(count,expiry)
    if count>limit:raise HTTPException(429,'Too many login attempts')
