"""Domain models for logistics transports (A pie, Moto, Helicóptero)."""

from enum import Enum
from typing import List, Dict, Any, Optional, Tuple, Union
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


def parse_transport_type(raw: Union[TransportType, str]) -> TransportType:
    """Parses Spanish/English transport type strings into TransportType."""
    if isinstance(raw, TransportType):
        return raw

    text = str(raw).strip().lower()
    if text in {"a pie", "pie", "foot", "walk"}:
        return TransportType.FOOT
    if text in {"moto", "motorcycle", "motocicleta"}:
        return TransportType.MOTORCYCLE
    if text in {"helicóptero", "helicoptero", "helicopter", "air", "heli"}:
        return TransportType.HELICOPTER
    raise ValueError(f"Tipo de transporte desconocido: '{raw}'")


class AirLeg:
    """Represents a single Euclidean flight segment in a helicopter circuit."""

    def __init__(
        self,
        from_node_id: str,
        to_node_id: str,
        from_pos: Tuple[float, float],
        to_pos: Tuple[float, float],
        distance: float,
        duration: float,
        dropoff_soldiers: Optional[List[str]] = None,
        is_return_to_base: bool = False,
    ):
        self.from_node_id = str(from_node_id)
        self.to_node_id = str(to_node_id)
        self.from_pos = (float(from_pos[0]), float(from_pos[1]))
        self.to_pos = (float(to_pos[0]), float(to_pos[1]))
        self.distance = float(distance)
        self.duration = float(duration)
        self.dropoff_soldiers = list(dropoff_soldiers or [])
        self.is_return_to_base = bool(is_return_to_base)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "from_pos": list(self.from_pos),
            "to_pos": list(self.to_pos),
            "distance": round(self.distance, 2),
            "duration": round(self.duration, 2),
            "dropoff_soldiers": list(self.dropoff_soldiers),
            "is_return_to_base": self.is_return_to_base,
        }


class TransportMission:
    """Represents an ongoing transport of soldiers to destination tower(s)."""

    def __init__(
        self,
        transport_type: Union[TransportType, str],
        soldier_ids: List[str],
        origin_id: str,
        destination_id: str,
        path: Optional[List[str]] = None,
        mission_id: Optional[str] = None,
        legs: Optional[List[AirLeg]] = None,
        reserved_cost: float = 0.0,
        current_x: float = 0.0,
        current_y: float = 0.0,
    ):
        self.id = mission_id or f"mission_{uuid.uuid4().hex[:6]}"
        self.transport_type = parse_transport_type(transport_type)
        self.soldier_ids = list(soldier_ids)
        self.origin_id = str(origin_id)
        self.destination_id = str(destination_id)
        self.path = list(path) if path else [self.origin_id, self.destination_id]
        self.current_step_index = 0
        self.edge_progress = 0.0  # seconds spent on current edge
        self.started_current_edge = False
        self.is_completed = False
        self.is_blocked = False

        # Spatial tracking and aerial circuit metadata
        self.legs: List[AirLeg] = list(legs or [])
        self.current_leg_index = 0
        self.leg_progress = 0.0
        self.reserved_cost = float(reserved_cost)
        self.current_x = float(current_x)
        self.current_y = float(current_y)

        self.total_flight_distance = sum(leg.distance for leg in self.legs)
        self.total_flight_duration = sum(leg.duration for leg in self.legs)
        self.returned_to_base_soldiers: List[str] = [
            s_id
            for leg in self.legs
            if leg.is_return_to_base
            for s_id in leg.dropoff_soldiers
        ]
        self.delivered_map: Dict[str, List[str]] = {}

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
            "started_current_edge": self.started_current_edge,
            "is_completed": self.is_completed,
            "is_blocked": self.is_blocked,
            "current_x": round(self.current_x, 2),
            "current_y": round(self.current_y, 2),
            "reserved_cost": round(self.reserved_cost, 2),
            "legs": [leg.to_dict() for leg in self.legs],
            "current_leg_index": self.current_leg_index,
            "leg_progress": round(self.leg_progress, 2),
            "total_flight_distance": round(self.total_flight_distance, 2),
            "total_flight_duration": round(self.total_flight_duration, 2),
            "returned_to_base_soldiers": list(self.returned_to_base_soldiers),
            "delivered_map": {k: list(v) for k, v in self.delivered_map.items()},
        }
