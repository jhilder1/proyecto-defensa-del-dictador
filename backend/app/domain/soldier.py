"""Domain models for defense soldiers (Infantería, Francotirador, Artillero)."""

from enum import Enum
from typing import Dict, Any, Optional
import uuid


class SoldierType(str, Enum):
    INFANTRY = "Infantería"
    SNIPER = "Francotirador"
    GUNNER = "Artillero"


SOLDIER_CONFIG = {
    SoldierType.INFANTRY: {
        "cost": 100,
        "damage": 10.0,
        "base_range": 5.0,
        "fire_rate": 1.0,  # attacks per second
        "is_area": False,
    },
    SoldierType.SNIPER: {
        "cost": 300,
        "damage": 50.0,
        "base_range": 20.0,
        "fire_rate": 0.5,  # 1 attack every 2.0s
        "is_area": False,
    },
    SoldierType.GUNNER: {
        "cost": 500,
        "damage": 100.0,
        "base_range": 15.0,
        "fire_rate": 0.2,  # 1 attack every 5.0s
        "is_area": True,
    },
}


class Soldier:
    """Represents a defensive soldier unit."""

    def __init__(
        self,
        soldier_type: SoldierType,
        soldier_id: Optional[str] = None,
        location_node_id: Optional[str] = "Base",
    ):
        self.id = soldier_id or f"soldier_{uuid.uuid4().hex[:6]}"
        self.soldier_type = SoldierType(soldier_type)
        cfg = SOLDIER_CONFIG[self.soldier_type]
        self.cost = cfg["cost"]
        self.damage = cfg["damage"]
        self.base_range = cfg["base_range"]
        self.fire_rate = cfg["fire_rate"]
        self.is_area = cfg["is_area"]
        self.location_node_id = location_node_id
        self.cooldown = 0.0  # seconds until next attack

    def get_effective_range(self, z_height: float, beta: float = 0.1) -> float:
        """Calculates effective range: R_ef = R_base * (1 + beta * z)."""
        return self.base_range * (1.0 + beta * max(0.0, z_height))

    def update_cooldown(self, dt: float) -> None:
        """Reduces cooldown timer by delta time."""
        if self.cooldown > 0:
            self.cooldown = max(0.0, self.cooldown - dt)

    def can_attack(self) -> bool:
        """Returns True if the unit is off cooldown."""
        return self.cooldown <= 1e-6

    def trigger_attack(self) -> None:
        """Resets attack cooldown based on fire rate."""
        self.cooldown = 1.0 / self.fire_rate

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.soldier_type.value,
            "cost": self.cost,
            "damage": self.damage,
            "base_range": self.base_range,
            "fire_rate": self.fire_rate,
            "is_area": self.is_area,
            "location_node_id": self.location_node_id,
            "cooldown": round(self.cooldown, 2),
        }

