"""Domain models for logistics transports (A pie, Moto, Helicóptero)."""

from enum import Enum
from typing import List, Dict, Any, Optional
import uuid


class TransportType(str, Enum):
    FOOT = "A pie"
    MOTORCYCLE = "Moto"
    HELICOPTER = "Helicóptero"


TRANSPORT_CONFIG = {
    TransportType.FOOT: {
        "max_capacity": 1,
        "fixed_cost": 0,
    },
    TransportType.MOTORCYCLE: {
        "max_capacity": 2,
        "fixed_cost": 0,
    },
    TransportType.HELICOPTER: {
        "max_capacity": 4,
        "fixed_cost": 150,  # Fixed operational flight cost
        "speed": 15.0,      # Direct 2D Euclidean units per second
    },
}


class TransportMission:
    """Represents an ongoing transport of soldiers to destination tower(s)."""

    def __init__(
        self,
        transport_type: TransportType,
        soldier_ids: List[str],
        origin_id: str,
        destination_id: str,
        path: Optional[List[str]] = None,
        mission_id: Optional[str] = None,
    ):
        self.id = mission_id or f"mission_{uuid.uuid4().hex[:6]}"
        self.transport_type = TransportType(transport_type)
        self.soldier_ids = list(soldier_ids)
        self.origin_id = str(origin_id)
        self.destination_id = str(destination_id)
        self.path = list(path) if path else [self.origin_id, self.destination_id]
        self.current_step_index = 0
        self.edge_progress = 0.0  # seconds spent on current edge
        self.is_completed = False
        self.is_blocked = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.transport_type.value,
            "soldier_ids": list(self.soldier_ids),
            "origin_id": self.origin_id,
            "destination_id": self.destination_id,
            "path": list(self.path),
            "current_step_index": self.current_step_index,
            "edge_progress": round(self.edge_progress, 2),
            "is_completed": self.is_completed,
            "is_blocked": self.is_blocked,
        }

