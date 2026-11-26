"""Global simulation state and resource management."""

from typing import Dict, List, Any, Optional
from app.domain.soldier import Soldier
from app.domain.enemy import EnemyMachine
from app.domain.transport import TransportMission, TransportType


class SimulationState:
    """Encapsulates the global state of the defense scenario."""

    def __init__(
        self,
        initial_budget: float = 1200.0,
        helicopter_cost: float = 150.0,
        helicopter_speed: float = 15.0,
        max_helicopter_uses: int = 5,
        helicopter_fleet_size: int = 1,
        total_repair_personnel: int = 4,
        beta_elevation: float = 0.1,
        alpha_danger: float = 1.0,
        d0_normalization: float = 50.0,
        max_time_limit: float = 300.0,
    ):
        self.initial_budget = float(initial_budget)
        self.budget_available = float(initial_budget)
        self.budget_reserved = 0.0

        self.helicopter_cost = float(helicopter_cost)
        self.helicopter_speed = max(0.001, float(helicopter_speed))
        self.max_helicopter_uses = max(0, int(max_helicopter_uses))
        self.remaining_helicopter_uses = self.max_helicopter_uses
        self.helicopter_fleet_size = max(1, int(helicopter_fleet_size))
        self.total_repair_personnel = max(1, int(total_repair_personnel))
        self.available_repair_personnel = self.total_repair_personnel
        self.beta_elevation = float(beta_elevation)
        self.alpha_danger = float(alpha_danger)
        self.d0_normalization = float(d0_normalization)
        self.max_time_limit = float(max_time_limit)

        self.clock: float = 0.0
        self.is_running: bool = False
        self.is_paused: bool = True
        self.is_game_over: bool = False
        self.game_result: str = "En preparación"

        # Registries
        self.soldiers: Dict[str, Soldier] = {}
        self.enemies: List[EnemyMachine] = []
        self.active_missions: List[TransportMission] = []
        self.event_log: List[Dict[str, Any]] = []

    @property
    def total_budget(self) -> float:
        return self.budget_available + self.budget_reserved

    @property
    def active_air_missions_count(self) -> int:
        return sum(
            1
            for m in self.active_missions
            if m.transport_type == TransportType.HELICOPTER and not m.is_completed
        )

    @property
    def helicopters_available(self) -> int:
        if self.remaining_helicopter_uses <= 0:
            return 0
        return max(0, self.helicopter_fleet_size - self.active_air_missions_count)

    def can_afford(self, amount: float) -> bool:
        return self.budget_available >= amount

    def spend_budget(self, amount: float) -> bool:
        if self.can_afford(amount):
            self.budget_available -= amount
            return True
        return False

    def reserve_budget(self, amount: float) -> bool:
        if self.can_afford(amount):
            self.budget_available -= amount
            self.budget_reserved += amount
            return True
        return False

    def release_reserved_budget(self, amount: float) -> None:
        amount_to_release = min(self.budget_reserved, amount)
        self.budget_reserved -= amount_to_release
        self.budget_available += amount_to_release

    def commit_reserved_budget(self, amount: float) -> None:
        amount_to_commit = min(self.budget_reserved, amount)
        self.budget_reserved -= amount_to_commit

    def add_reward(self, amount: float) -> None:
        self.budget_available += float(amount)

    def add_event(self, event_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        self.event_log.append({
            "timestamp": round(self.clock, 2),
            "type": event_type,
            "message": message,
            "details": details or {},
        })

    def get_alive_enemies(self) -> List[EnemyMachine]:
        return [e for e in self.enemies if e.is_alive]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clock": round(self.clock, 2),
            "max_time_limit": self.max_time_limit,
            "helicopter_speed": self.helicopter_speed,
            "max_helicopter_uses": self.max_helicopter_uses,
            "remaining_helicopter_uses": self.remaining_helicopter_uses,
            "helicopter_fleet_size": self.helicopter_fleet_size,
            "helicopters_available": self.helicopters_available,
            "total_repair_personnel": self.total_repair_personnel,
            "available_repair_personnel": self.available_repair_personnel,
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "is_game_over": self.is_game_over,
            "game_result": self.game_result,
            "budget_available": round(self.budget_available, 2),
            "budget_reserved": round(self.budget_reserved, 2),
            "total_budget": round(self.total_budget, 2),
            "alive_enemies_count": len(self.get_alive_enemies()),
            "total_soldiers_count": len(self.soldiers),
            "active_missions_count": len(self.active_missions),
        }

