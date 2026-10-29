"""Section 38: bounded, server-validated tenant configuration.

Display choices are never authorization to process PHI, activate payments or
use unapproved providers. Public-site attestations are not legal approval.
"""
from __future__ import annotations
from fastapi import HTTPException

LOCALES={"fa","en","ar","ps","prs"}
SAFE_FLAGS={"show_operations_summary","show_help_tips","compact_dashboard"}
PUBLIC_SITE_FLAGS={"show_public_link","search_indexing_enabled","legal_content_reviewed"}

def validate_setting(key:str,value:object)->object:
    if key=="feature_flags":
        if not isinstance(value,dict) or not set(value).issubset(SAFE_FLAGS):
            raise HTTPException(422,"Unknown or privileged feature flag")
        if any(type(enabled) is not bool for enabled in value.values()):
            raise HTTPException(422,"Feature flags must be boolean")
        return value
    if key=="enabled_languages":
        if not isinstance(value,list) or not value or len(value)>len(LOCALES):
            raise HTTPException(422,"Invalid language list")
        if any(not isinstance(x,str) or x not in LOCALES for x in value) or len(value)!=len(set(value)):
            raise HTTPException(422,"Unknown or duplicate locale")
        return value
    if key=="locale":
        if not isinstance(value,str) or value not in LOCALES:
            raise HTTPException(422,"Invalid default locale")
        return value
    if key=="public_portal":
        if not isinstance(value,dict) or not set(value).issubset(PUBLIC_SITE_FLAGS):
            raise HTTPException(422,"Unknown public site preference")
        # Preserve the pre-existing API contract: malformed string attestations
        # are accepted but normalized to False, never treated as truthy consent.
        clean={}
        for name,flag in value.items():
            if type(flag) is bool:
                clean[name]=flag
            elif name in {"search_indexing_enabled","legal_content_reviewed"} and isinstance(flag,str):
                clean[name]=False
            else:
                raise HTTPException(422,"Invalid public site preference")
        return clean
    if not isinstance(value,dict):
        raise HTTPException(422,"Setting value must be an object")
    return value
