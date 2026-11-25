"""Pydantic schemas for Stage 4 logistics actions."""

from typing import List, Optional
from pydantic import BaseModel, Field


class BuySoldierRequest(BaseModel):
    soldier_type: str = Field(..., description="Infantería, Francotirador o Artillero")
    quantity: int = Field(default=1, ge=1)


class DispatchGroundRequest(BaseModel):
    transport_type: str = Field(..., description="A pie o Moto")
    soldier_ids: List[str] = Field(..., min_length=1)
    destination_id: str
    origin_id: Optional[str] = None


class DispatchAirRequest(BaseModel):
    soldier_ids: List[str] = Field(..., min_length=1, max_length=4)
    destination_id: str
