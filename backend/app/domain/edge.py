"""Domain models for edges and dynamic bridges in the defense simulation."""

from typing import Dict, Any, Optional, Tuple


class ElevatedEdge:
    """Undirected edge in the Elevated Network (G_E), possibly a dynamic bridge."""

    def __init__(
        self,
        u: str,
        v: str,
        foot_time: float,
        moto_time: float,
        is_bridge: bool = False,
        max_resistance: int = 3,
        reconstruction_duration: float = 30.0,
    ):
        self.u = str(u)
        self.v = str(v)
        self.foot_time = float(foot_time)
        self.moto_time = float(moto_time)
        self.is_bridge = bool(is_bridge)
        self.max_resistance = int(max_resistance) if is_bridge else 999999
        self.current_resistance = self.max_resistance
        self.is_destroyed = False
        self.reconstruction_duration = float(reconstruction_duration)
        self.reconstruction_timer = 0.0

    @property
    def edge_key(self) -> Tuple[str, str]:
        """Canonical ordered key for undirected edge."""
        return (min(self.u, self.v), max(self.u, self.v))

    def on_motorcycle_cross_complete(self) -> bool:
        """Called when a motorcycle finishes crossing the bridge.
        
        Decrements current resistance by 1.
        If resistance hits 0, the bridge collapses and starts rebuilding.
        Returns True if the bridge just collapsed.
        """
        if not self.is_bridge or self.is_destroyed:
            return False

        self.current_resistance = max(0, self.current_resistance - 1)
        if self.current_resistance == 0:
            self.is_destroyed = True
            self.reconstruction_timer = self.reconstruction_duration
            return True
        return False

    def update_reconstruction(self, delta_time: float) -> bool:
        """Advances reconstruction timer.
        
        Returns True if the bridge just finished rebuilding.
        """
        if not self.is_destroyed:
            return False

        self.reconstruction_timer -= delta_time
        if self.reconstruction_timer <= 0.0:
            self.is_destroyed = False
            self.current_resistance = self.max_resistance
            self.reconstruction_timer = 0.0
            return True
        return False

    def is_passable(self) -> bool:
        """A normal edge is always passable. A bridge is impassable if destroyed."""
        return not (self.is_bridge and self.is_destroyed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "u": self.u,
            "v": self.v,
            "foot_time": self.foot_time,
            "moto_time": self.moto_time,
            "is_bridge": self.is_bridge,
            "max_resistance": self.max_resistance,
            "current_resistance": self.current_resistance,
            "is_destroyed": self.is_destroyed,
            "reconstruction_duration": self.reconstruction_duration,
            "reconstruction_timer": max(0.0, round(self.reconstruction_timer, 2)),
        }


class MazeEdge:
    """Corridor edge in the Lower Maze Network (G_M)."""

    def __init__(
        self,
        u: str,
        v: str,
        length: float,
        speed: float,
    ):
        self.u = str(u)
        self.v = str(v)
        self.length = float(length)
        self.speed = max(0.001, float(speed))
        self.base_time = self.length / self.speed
        self.avg_danger = 0.0
        self.danger_potential = 0.0
        self.reactive_weight = self.base_time

    @property
    def edge_key(self) -> Tuple[str, str]:
        return (min(self.u, self.v), max(self.u, self.v))

    def update_danger(self, avg_danger: float, alpha: float) -> None:
        """Updates reactive weight based on average danger and alpha parameter.
        
        D_bar(e) = avg_danger
        P(e) = D_bar(e) * t(e)
        w(e) = t(e) + alpha * P(e)
        """
        self.avg_danger = float(avg_danger)
        self.danger_potential = self.avg_danger * self.base_time
        self.reactive_weight = self.base_time + float(alpha) * self.danger_potential

    def to_dict(self) -> Dict[str, Any]:
        return {
            "u": self.u,
            "v": self.v,
            "length": self.length,
            "speed": self.speed,
            "base_time": round(self.base_time, 2),
            "avg_danger": round(self.avg_danger, 2),
            "danger_potential": round(self.danger_potential, 2),
            "reactive_weight": round(self.reactive_weight, 2),
        }

