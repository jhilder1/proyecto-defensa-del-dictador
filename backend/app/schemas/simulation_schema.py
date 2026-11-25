"""Pydantic schemas for Etapa 3 simulation requests."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CalculateHazardsRequest(BaseModel):
    alpha_danger: Optional[float] = Field(default=None, description="Risk weighting factor alpha >= 0")


class ConvoyStepRequest(BaseModel):
    alpha_danger: Optional[float] = Field(default=None, description="Risk weighting factor alpha >= 0")


class ConvoyRunRequest(BaseModel):
    alpha_danger: Optional[float] = Field(default=None, description="Risk weighting factor alpha >= 0")
    max_steps: Optional[int] = Field(default=100, description="Maximum number of steps to simulate")


class ConvoyResetRequest(BaseModel):
    alpha_danger: Optional[float] = Field(default=None, description="Risk weighting factor alpha >= 0")


class SimulationTickRequest(BaseModel):
    dt: float = Field(default=1.0, gt=0.0, description="Logical clock step duration in seconds")
    alpha_danger: Optional[float] = Field(default=None, ge=0.0, description="Risk weighting factor alpha >= 0")
