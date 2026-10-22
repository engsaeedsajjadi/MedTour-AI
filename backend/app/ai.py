"""Opt-in, disabled-by-default OpenAI-compatible administrative intake adapter.

Must never infer medical diagnosis or send medical records to an unapproved provider.
"""
from __future__ import annotations
import json, os, ipaddress
from urllib.parse import urlsplit
import httpx
from fastapi import HTTPException

SYSTEM = (
    'You are a multilingual administrative patient intake assistant for a medical travel coordination service. '
    'You may ask one concise non-diagnostic intake question at a time, in the requested language. '
    'Do not diagnose, prescribe, recommend a treatment, promise a medical outcome, confirm pricing, '
    'determine fitness to travel, or provide emergency triage. '
    'If medical judgment or urgent symptoms are mentioned, explicitly require human review and local emergency care. '
    'Do not echo private patient details in your response. '
    'Respond ONLY with JSON with keys "message" (string), "requires_human" (boolean), "question_category" (string).'
)

def approved_provider_base_url() -> str | None:
    """Require a configured exact HTTPS host allowlist; never trust model input.

    Network egress allowlisting/DNS controls are still required in production.
    """
    raw = os.getenv('AI_BASE_URL', '').strip()
    allowed = {h.strip().lower() for h in os.getenv('AI_APPROVED_HOSTS', '').split(',') if h.strip()}
    if not raw or not allowed:
        return None
    try:
        parsed = urlsplit(raw)
        host = parsed.hostname
        if (parsed.scheme != 'https' or not host or host.lower() not in allowed
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.port not in (None, 443)
            or host.lower() == 'localhost' or not host.isascii()
            or host.endswith('.local') or host.endswith('.internal')):
            return None
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            return None
        return raw.rstrip('/')
    except (ValueError, TypeError):
        return None


def provider_available()->bool:
    return bool(
        os.getenv('AI_PROVIDER_APPROVED','').lower()=='true'
        and os.getenv('AI_API_KEY') and os.getenv('AI_MODEL')
        and approved_provider_base_url()
    )

def draft(message:str,language:str)->dict:
    if not provider_available():
        raise HTTPException(503,'AI provider is disabled until jurisdiction, contract and medical-data processing are approved')
    root=approved_provider_base_url()
    if root is None:
        raise HTTPException(503,'Approved AI endpoint host policy unavailable')
    try:
        with httpx.Client(timeout=25,follow_redirects=False) as http:
            resp=http.post(root+'/chat/completions',headers={
                'Authorization':'Bearer '+os.environ['AI_API_KEY'],
                'Content-Type':'application/json'
            },json={'model':os.environ['AI_MODEL'],'temperature':0.2,'messages':[
                {'role':'system','content':SYSTEM},
                {'role':'user','content':f'Language: {language}\nAdministrative intake message: {message}'},
            ]})
            resp.raise_for_status()
        raw=resp.json()['choices'][0]['message']['content']
        data=json.loads(raw)
        if not isinstance(data,dict) or not isinstance(data.get('message'),str) or not isinstance(data.get('requires_human'),bool):
            raise ValueError('Invalid AI response schema')
        return {'language':language,'message':data['message'][:2000],
                'human_review_required':True, # medical travel processing ALWAYS human reviewed
                'provider_declared_handoff':data['requires_human'],
                'question_category':str(data.get('question_category','general'))[:70],
                'disclaimer':'Administrative assistant only; not medical advice.'}
    except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError) as exc:
        raise HTTPException(502,'AI provider error; escalate to human operator') from exc

def translate(text:str,source_language:str,target_language:str)->str:
    """Explicitly approved provider only; drafts must be human-reviewed."""
    from .intake import LANGUAGES
    if source_language not in LANGUAGES or target_language not in LANGUAGES:
        raise HTTPException(422,'Unsupported language')
    if not provider_available():raise HTTPException(503,'Approved AI translation provider is unavailable')
    root=approved_provider_base_url()
    if root is None:raise HTTPException(503,'Approved AI endpoint host policy unavailable')
    try:
        with httpx.Client(timeout=20,follow_redirects=False) as client:
            resp=client.post(root+'/chat/completions',headers={'Authorization':'Bearer '+os.environ['AI_API_KEY']},json={
                'model':os.environ['AI_MODEL'],
                'messages':[{'role':'system','content':
                  f'Translate faithfully from {source_language} to {target_language}. Preserve uncertainty, proper names, numbers, and clinical terminology. '
                  'Do not add diagnoses, advice, facts or interpretations. Return translation only.'},
                  {'role':'user','content':text}], 'temperature':0,'max_tokens':1200})
        resp.raise_for_status()
        result=resp.json()['choices'][0]['message']['content']
        if not isinstance(result,str) or not result.strip() or len(result)>9000:raise ValueError('Invalid translation')
        return result.strip()
    except (httpx.HTTPError,KeyError,IndexError,ValueError,TypeError):
        raise HTTPException(502,'AI translation draft failed; use a human translator')
