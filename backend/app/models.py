"""Data shapes for a rescue ticket.

Ticket fields are always stored in English so any responder can read them.
The caller's own words are kept in `transcript` for checking.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# Ordered from safest to most dangerous. Index is used for comparisons.
WATER_LEVELS = ["none", "ankle", "knee", "waist", "chest", "neck", "roof"]
VULNERABLE_TYPES = ["elderly", "child", "infant", "pregnant", "disabled", "sick", "unspecified"]
NEED_TYPES = ["rescue", "food", "water", "medicine", "info"]


class Status(str, Enum):
    NEW = "new"
    ASSIGNED = "assigned"
    RESCUED = "rescued"
    CLOSED = "closed"
    NEEDS_CALLBACK = "needs_callback"


class CallState(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DROPPED = "dropped"
    HANDED_OFF = "handed_off"   # AI could not get answers; a human officer takes over


class LocConfidence(str, Enum):
    EXACT = "exact"      # door no / building + street + locality
    STREET = "street"    # street or building + locality
    AREA = "area"        # locality only
    UNKNOWN = "unknown"  # nothing usable


class Location(BaseModel):
    locality: Optional[str] = None
    street: Optional[str] = None
    door_no: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[str] = None
    landmark: Optional[str] = None
    # Names as the caller said them, in their script (for the read-back)
    street_native: Optional[str] = None
    building_native: Optional[str] = None
    landmark_native: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    confidence: LocConfidence = LocConfidence.UNKNOWN
    confirmed: bool = False


class Danger(BaseModel):
    water_level: Optional[str] = None
    water_rising: Optional[bool] = None
    injured: Optional[bool] = None
    medical_emergency: Optional[bool] = None
    structure_unsafe: Optional[bool] = None
    trapped: Optional[bool] = None


class Turn(BaseModel):
    role: str  # "caller" or "agent"
    text: str
    lang: Optional[str] = None
    ts: float = Field(default_factory=time.time)


class Ticket(BaseModel):
    id: str
    caller_number: str
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    status: Status = Status.NEW
    call_state: CallState = CallState.IN_PROGRESS
    followup_reasons: list[str] = Field(default_factory=list)

    language: Optional[str] = None
    needs_interpreter: bool = False

    priority: str = "P1"
    priority_reasons: list[str] = Field(default_factory=list)
    escalate_to_human: bool = False

    location: Location = Field(default_factory=Location)
    people_count: Optional[int] = None
    vulnerable: list[str] = Field(default_factory=list)
    medical_need: Optional[str] = None
    danger: Danger = Field(default_factory=Danger)
    needs: list[str] = Field(default_factory=list)

    transcript: list[Turn] = Field(default_factory=list)


class Extraction(BaseModel):
    """What the LLM found in ONE caller utterance. Anything not said stays None/empty."""

    locality: Optional[str] = None
    street: Optional[str] = None
    door_no: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[str] = None
    landmark: Optional[str] = None
    street_native: Optional[str] = None
    building_native: Optional[str] = None
    landmark_native: Optional[str] = None

    people_count: Optional[int] = None
    vulnerable: list[str] = Field(default_factory=list)
    medical_need: Optional[str] = None

    water_level: Optional[str] = None
    water_rising: Optional[bool] = None
    injured: Optional[bool] = None
    medical_emergency: Optional[bool] = None
    structure_unsafe: Optional[bool] = None
    trapped: Optional[bool] = None

    needs: list[str] = Field(default_factory=list)

    confirmation: Optional[str] = None  # "yes" / "no" — answer to a read-back
    correction: bool = False            # caller is correcting earlier details
    asks_for_human: bool = False
    unclear: bool = False               # nothing usable in this utterance
    dont_know: bool = False             # caller says they don't know the thing we asked (a real answer)

    # Empathy signals (same LLM call, no extra request)
    ack: Optional[str] = None             # <= 6-word acknowledgement in the caller's language
    caller_question: Optional[str] = None  # when_help | stay_or_move | electricity | animal | other
    panic: Optional[str] = None            # low | high

    tokens_used: int = 0                # LLM tokens spent on this extraction (0 = quick parse / fake)