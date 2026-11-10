"""Pydantic schemas for scenario and planning requests/responses."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ScenarioNodeSchema(BaseModel):
    id: str
    x: float
    y: float
    z: Optional[float] = 0.0
    type: Optional[str] = "Tránsito"
    surveillance_radius: Optional[float] = 20.0
    is_entry: Optional[bool] = False
    is_exit: Optional[bool] = False


class ScenarioEdgeSchema(BaseModel):
    u: str
    v: str
    foot_time: Optional[float] = 10.0
    moto_time: Optional[float] = 4.0
    is_bridge: Optional[bool] = False
    max_resistance: Optional[int] = 3
    reconstruction_duration: Optional[float] = 30.0
    length: Optional[float] = None
    speed: Optional[float] = 1.0


class ScenarioConfigSchema(BaseModel):
    initial_budget: float = 1200.0
    beta_elevation: float = 0.1
    alpha_danger: float = 1.0
    d0_normalization: float = 50.0
    helicopter_cost: float = 150.0
    max_time_limit: float = 300.0


class EnemySchema(BaseModel):
    type: str
    hp: Optional[float] = None
    reward: Optional[int] = None


class ScenarioDataSchema(BaseModel):
    scenario_name: Optional[str] = "Escenario de Defensa"
    config: Optional[ScenarioConfigSchema] = Field(default_factory=ScenarioConfigSchema)
    elevated_network: Dict[str, Any]
    maze_network: Dict[str, Any]
    convoy: Optional[List[EnemySchema]] = Field(default_factory=list)


class SelectTowersRequest(BaseModel):
    k_towers: int = 3
    d0_normalization: Optional[float] = None

