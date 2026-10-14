"""Opt-in, disabled-by-default OpenAI-compatible administrative intake adapter.

Must never infer medical diagnosis or send medical records to an unapproved provider.
"""
from __future__ import annotations
import json, os
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

def provider_available()->bool:
    return all([
        os.getenv('AI_PROVIDER_APPROVED','').lower()=='true',
        os.getenv('AI_API_KEY'),os.getenv('AI_BASE_URL'),os.getenv('AI_MODEL'),
    ])

def draft(message:str,language:str)->dict:
    if not provider_available():
        raise HTTPException(503,'AI provider is disabled until jurisdiction, contract and medical-data processing are approved')
    root=os.environ['AI_BASE_URL'].rstrip('/')
    # Approved URL must be controlled by operator, never supplied by chat messages.
    if not root.startswith('https://'):
        raise HTTPException(503,'Approved AI endpoint must use HTTPS')
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
    root=os.environ['AI_BASE_URL'].rstrip('/')
    if not root.startswith('https://'):raise HTTPException(503,'AI endpoint must use HTTPS')
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
