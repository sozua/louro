from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.auth import verify_api_key
from src.config import Language
from src.db.queries import get_org_language, set_org_language

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orgs", tags=["orgs"], dependencies=[Depends(verify_api_key)])


# ── Schemas ──────────────────────────────────────────────────────


class OrgLanguageOut(BaseModel):
    org: str
    language: str


class OrgLanguageIn(BaseModel):
    language: Language


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/{org}/language", response_model=OrgLanguageOut)
async def get_language(org: str):
    language = await get_org_language(org)
    return OrgLanguageOut(org=org, language=language)


@router.put("/{org}/language", response_model=OrgLanguageOut)
async def put_language(org: str, body: OrgLanguageIn):
    record = await set_org_language(org, body.language)
    return OrgLanguageOut(org=org, language=record.language)
