"""Convoy service module unifying danger estimation and continuous corridor position helpers."""

from typing import Tuple
from app.core.maze_graph import MazeGraph
from app.services.hazard_service import (
    CorridorHazard,
    HazardService,
    calculate_corridor_hazard,
    calculate_point_damage,
    get_covering_defenses,
)


def interpolate_convoy_position(
    maze_graph: MazeGraph,
    u: str,
    v: str,
    progress: float,
    duration: float,
) -> Tuple[float, float]:
    """Computes interpolated 2D coordinates of the convoy along corridor (u, v)."""
    node_u = maze_graph.get_maze_node(u)
    node_v = maze_graph.get_maze_node(v)
    if not node_u:
        return (0.0, 0.0)
    if not node_v or duration <= 1e-9:
        return (node_u.x, node_u.y)

    ratio = min(1.0, max(0.0, progress / duration))
    x = node_u.x + (node_v.x - node_u.x) * ratio
    y = node_u.y + (node_v.y - node_u.y) * ratio
    return (x, y)


__all__ = [
    "CorridorHazard",
    "HazardService",
    "calculate_corridor_hazard",
    "calculate_point_damage",
    "get_covering_defenses",
    "interpolate_convoy_position",
]
