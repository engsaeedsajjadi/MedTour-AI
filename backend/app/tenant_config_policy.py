"""Section 38: fail-closed tenant configuration rules.

The tenant settings UI may not grant access to medical/AI/payment providers,
production safety flags, security bypasses, or privileged runtime configuration.
"""
from __future__ import annotations
from fastapi import HTTPException

LOCALES={"fa","en","ar","ps","prs"}
# Display-only flags: never consumed to authorize an API, PHI or external action.
SAFE_FLAGS={"show_operations_summary","show_help_tips","compact_dashboard"}

def validate_setting(key:str,value:object)->object:
    if key=="feature_flags":
        if not isinstance(value,dict):
            raise HTTPException(422,"Feature flags must be an object")
        if not set(value).issubset(SAFE_FLAGS):
            raise HTTPException(422,"Unknown or privileged feature flag")
        if any(type(enabled) is not bool for enabled in value.values()):
            raise HTTPException(422,"Feature flags must be boolean")
        if not isinstance(value,dict):
        raise HTTPException(422,'Setting value must be an object')
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
        # This setting is informational only. It cannot override access controls.
        allowed={"show_public_link","search_indexing_enabled","legal_content_reviewed"}
        if not isinstance(value,dict) or not set(value).issubset(allowed) or any(type(v) is not bool for v in value.values()):
            raise HTTPException(422,"Only reviewed public-site display/indexing preferences are configurable")
        return value
    return value
