"""Section 33: conservative, documented API contract and correlation identifiers."""
from __future__ import annotations
import secrets
from fastapi import APIRouter,Request
from pydantic import BaseModel,ConfigDict

router=APIRouter(prefix="/api/v1/meta",tags=["api contract"])

class APIContract(BaseModel):
    model_config=ConfigDict(extra="forbid")
    api_major:int
    schema_url:str
    stability:str
    idempotency_coverage:str
    production_ready:bool
    patient_data_authorized:bool

@router.get("/contract",response_model=APIContract)
def contract():
    return APIContract(
        api_major=1,schema_url="/openapi.json",stability="alpha",
        idempotency_coverage="endpoint_specific_not_global",
        production_ready=False,patient_data_authorized=False)

async def correlation_middleware(request:Request,call_next):
    # Caller-controlled correlation IDs can be malicious, sensitive or spoofed.
    # Generate independent IDs, and never copy supplied headers into logs.
    request_id=secrets.token_hex(16)
    request.state.request_id=request_id
    response=await call_next(request)
    response.headers["X-Request-ID"]=request_id
    response.headers["X-API-Major-Version"]="1"
    return response
