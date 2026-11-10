"""Domain models for graph nodes in the defense simulation."""

from enum import Enum
from typing import List, Optional, Any, Dict


class ElevatedNodeType(str, Enum):
    BASE = "Base"
    CANDIDATO = "Candidato"
    TRANSITO = "Tránsito"
    HELIPUERTO = "Helipuerto"


class ElevatedNode:
    """Node in the Elevated Network (G_E)."""

    def __init__(
        self,
        node_id: str,
        x: float,
        y: float,
        z: float = 0.0,
        node_type: ElevatedNodeType = ElevatedNodeType.TRANSITO,
        is_active_tower: bool = False,
        surveillance_radius: float = 20.0,
    ):
        self.id = str(node_id)
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.node_type = ElevatedNodeType(node_type)
        self.is_active_tower = is_active_tower or (self.node_type == ElevatedNodeType.BASE)
        self.surveillance_radius = float(surveillance_radius)
        self.max_capacity = 3
        # List of soldier IDs currently stationed here
        self.stationed_soldiers: List[str] = []
        # Number of soldiers currently in transit/reserved for this tower
        self.reserved_slots = 0

    @property
    def total_committed_soldiers(self) -> int:
        return len(self.stationed_soldiers) + self.reserved_slots

    @property
    def available_slots(self) -> int:
        return max(0, self.max_capacity - self.total_committed_soldiers)

    def can_receive_soldier(self) -> bool:
        return self.available_slots > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "type": self.node_type.value,
            "is_active_tower": self.is_active_tower,
            "surveillance_radius": self.surveillance_radius,
            "stationed_soldiers": list(self.stationed_soldiers),
            "reserved_slots": self.reserved_slots,
            "available_slots": self.available_slots,
        }


class MazeNode:
    """Node in the Lower Maze Network (G_M)."""

    def __init__(
        self,
        node_id: str,
        x: float,
        y: float,
        is_entry: bool = False,
        is_exit: bool = False,
    ):
        self.id = str(node_id)
        self.x = float(x)
        self.y = float(y)
        self.is_entry = bool(is_entry)
        self.is_exit = bool(is_exit)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "is_entry": self.is_entry,
            "is_exit": self.is_exit,
        }

