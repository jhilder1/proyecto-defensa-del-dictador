"""Domain models for convoy enemy machines (Tanque, Camión, Robot)."""

from enum import Enum
from typing import Dict, Any, Optional
import uuid


class EnemyType(str, Enum):
    TANK = "Tanque"
    TRUCK = "Camión"
    ROBOT = "Robot"


ENEMY_CONFIG = {
    EnemyType.TANK: {
        "hp": 200.0,
        "reward": 150,
    },
    EnemyType.TRUCK: {
        "hp": 100.0,
        "reward": 100,
    },
    EnemyType.ROBOT: {
        "hp": 50.0,
        "reward": 50,
    },
}


class EnemyMachine:
    """Individual machine in the enemy convoy."""

    def __init__(
        self,
        enemy_type: EnemyType,
        enemy_id: Optional[str] = None,
        custom_hp: Optional[float] = None,
        custom_reward: Optional[int] = None,
    ):
        self.id = enemy_id or f"enemy_{uuid.uuid4().hex[:6]}"
        self.enemy_type = EnemyType(enemy_type)
        cfg = ENEMY_CONFIG[self.enemy_type]
        self.max_hp = float(custom_hp if custom_hp is not None else cfg["hp"])
        self.current_hp = self.max_hp
        self.reward = int(custom_reward if custom_reward is not None else cfg["reward"])
        self.is_alive = True

    def take_damage(self, amount: float) -> float:
        """Applies damage and returns actual damage taken.
        
        If HP reaches 0, unit is destroyed.
        """
        if not self.is_alive:
            return 0.0

        actual_damage = min(self.current_hp, amount)
        self.current_hp -= actual_damage
        if self.current_hp <= 0.0:
            self.current_hp = 0.0
            self.is_alive = False
        return actual_damage

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.enemy_type.value,
            "max_hp": self.max_hp,
            "current_hp": round(self.current_hp, 2),
            "reward": self.reward,
            "is_alive": self.is_alive,
        }

