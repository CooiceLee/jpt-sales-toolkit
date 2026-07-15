"""Strict request models shared by authorization endpoint groups."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemberCreate(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    role: Literal["leader", "sales", "tech"]
    region: Optional[str] = Field(default=None, max_length=120)


class MemberUpdate(StrictModel):
    username: Optional[str] = Field(default=None, min_length=1, max_length=80)
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    role: Optional[Literal["leader", "sales", "tech"]] = None
    region: Optional[str] = Field(default=None, max_length=120)


class IssuerInitialize(StrictModel):
    passphrase: str = Field(min_length=12, max_length=1024)


class FirstRunSetup(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=1024)
    issuer_passphrase: str = Field(min_length=12, max_length=1024)
    region: Optional[str] = Field(default=None, max_length=120)


class LeaderRecovery(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=1024)
    issuer_passphrase: str = Field(min_length=12, max_length=1024)
