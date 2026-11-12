"""Hazard calculation service for Lower Maze Network (G_M) corridors.

Computes point damage rates D(q), average corridor danger D_bar(e),
potential damage P(e), and reactive edge weights w(e).
"""

from typing import Dict, List, Tuple, Optional, Any, Union
import math
from app.domain.soldier import DefenseUnit, SoldierType
from app.domain.edge import MazeEdge
from app.core.maze_graph import MazeGraph
from app.services.scenario_service import ScenarioService


class CorridorHazard(tuple):
    """3-tuple (avg_danger, danger_potential, reactive_weight) with rich dictionary access."""

    def __new__(
        cls,
        avg_danger: float,
        danger_potential: float,
        reactive_weight: float,
        details: Optional[Dict[str, Any]] = None,
    ):
        instance = super().__new__(
            cls, (float(avg_danger), float(danger_potential), float(reactive_weight))
        )
        instance.avg_danger = float(avg_danger)
        instance.danger_potential = float(danger_potential)
        instance.reactive_weight = float(reactive_weight)
        instance.details = details or {}
        return instance

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, str):
            if item in self.details:
                return self.details[item]
            if hasattr(self, item):
                return getattr(self, item)
            raise KeyError(item)
        return super().__getitem__(item)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.details:
            return self.details[key]
        if hasattr(self, key):
            return getattr(self, key)
        return default

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.details)


def get_covering_defenses(
    point: Tuple[float, float],
    active_defenses: List[DefenseUnit],
) -> List[DefenseUnit]:
    """Returns all defense units whose effective range covers point q=(x, y)."""
    covering: List[DefenseUnit] = []
    qx, qy = point
    for unit in active_defenses:
        dist = math.hypot(unit.x - qx, unit.y - qy)
        if dist <= unit.effective_range + 1e-9:
            covering.append(unit)
    return covering


def calculate_point_damage(
    point: Tuple[float, float],
    active_defenses: List[DefenseUnit],
) -> float:
    """Calculates instantaneous damage rate D(q) = sum(d_s * f_s) at point q.
    
    Single-count artillery rule:
        Regardless of how many gunners reach q, gunner contribution is counted
        at most ONCE:
        D(q) = 10.0 * N_inf + 25.0 * N_snip + 20.0 * min(1, N_gun).
    """
    n_inf = 0
    n_snip = 0
    n_gun = 0

    qx, qy = point
    for unit in active_defenses:
        dist = math.hypot(unit.x - qx, unit.y - qy)
        if dist <= unit.effective_range + 1e-9:
            if unit.is_infantry:
                n_inf += 1
            elif unit.is_sniper:
                n_snip += 1
            elif unit.is_gunner:
                n_gun += 1

    artillery_contribution = 20.0 if n_gun > 0 else 0.0
    damage_rate = 10.0 * n_inf + 25.0 * n_snip + artillery_contribution
    return float(damage_rate)


def calculate_corridor_hazard(
    corridor: MazeEdge,
    active_defenses: List[DefenseUnit],
    alpha: float = 1.0,
    maze_graph: Optional[MazeGraph] = None,
) -> CorridorHazard:
    """Calculates corridor hazard metrics for corridor e=(u, v).
    
    Evaluates 3 key points: (q_ini, q_mid, q_end).
    Computes:
        D_bar(e) = (D(q_ini) + D(q_mid) + D(q_end)) / 3.0
        P(e) = D_bar(e) * t(e)
        w(e) = t(e) + alpha * P(e)
    Updates corridor.update_danger(D_bar, alpha) in place.
    
    Returns:
        CorridorHazard (avg_danger, danger_potential, reactive_weight).
    """
    if maze_graph is None:
        scenario_srv = ScenarioService.get_instance()
        maze_graph = scenario_srv.maze_graph

    points = maze_graph.get_corridor_points(corridor.u, corridor.v)
    if points is not None:
        q_ini, q_mid, q_end = points
    else:
        # Fallback if nodes lack coordinates
        q_ini = (0.0, 0.0)
        q_mid = (0.0, 0.0)
        q_end = (0.0, 0.0)

    d_ini = calculate_point_damage(q_ini, active_defenses)
    d_mid = calculate_point_damage(q_mid, active_defenses)
    d_end = calculate_point_damage(q_end, active_defenses)

    d_bar = (d_ini + d_mid + d_end) / 3.0
    t_e = corridor.base_time
    p_e = d_bar * t_e
    w_e = t_e + float(alpha) * p_e

    # Update corridor in-place
    corridor.update_danger(d_bar, float(alpha))

    # Synchronize graph adjacency weight
    if maze_graph.has_edge(corridor.u, corridor.v):
        maze_graph.adj[corridor.u][corridor.v]["reactive_weight"] = corridor.reactive_weight
        if not maze_graph.directed and corridor.v in maze_graph.adj and corridor.u in maze_graph.adj[corridor.v]:
            maze_graph.adj[corridor.v][corridor.u]["reactive_weight"] = corridor.reactive_weight

    # Collect covering soldiers for telemetry
    covering_ini = get_covering_defenses(q_ini, active_defenses)
    covering_mid = get_covering_defenses(q_mid, active_defenses)
    covering_end = get_covering_defenses(q_end, active_defenses)

    all_covering: Dict[str, DefenseUnit] = {}
    for u in covering_ini + covering_mid + covering_end:
        all_covering[u.id] = u

    has_artillery = any(u.is_gunner for u in all_covering.values())

    details = {
        "u": corridor.u,
        "v": corridor.v,
        "length": corridor.length,
        "speed": corridor.speed,
        "base_time": round(t_e, 2),
        "q_ini": {"x": q_ini[0], "y": q_ini[1], "damage_rate": round(d_ini, 2)},
        "q_mid": {"x": q_mid[0], "y": q_mid[1], "damage_rate": round(d_mid, 2)},
        "q_end": {"x": q_end[0], "y": q_end[1], "damage_rate": round(d_end, 2)},
        "avg_danger": round(d_bar, 2),
        "danger_potential": round(p_e, 2),
        "reactive_weight": round(w_e, 2),
        "has_artillery": has_artillery,
        "covering_soldiers": sorted(list(all_covering.keys())),
    }

    return CorridorHazard(
        avg_danger=d_bar,
        danger_potential=p_e,
        reactive_weight=w_e,
        details=details,
    )


class HazardService:
    """Service for managing defense deployments and corridor hazard calculations."""

    _instance: Optional["HazardService"] = None

    def __init__(self, scenario_service: Optional[ScenarioService] = None):
        self._scenario_service = scenario_service
        self.custom_active_defenses: Optional[List[DefenseUnit]] = None

    @property
    def scenario_service(self) -> ScenarioService:
        if self._scenario_service is not None:
            return self._scenario_service
        return ScenarioService.get_instance()

    @classmethod
    def get_instance(cls) -> "HazardService":
        if cls._instance is None:
            cls._instance = HazardService()
        return cls._instance

    def set_custom_defenses(self, defenses: Optional[List[DefenseUnit]]) -> None:
        """Sets custom defenses to override scenario defenses (useful for testing and sandbox)."""
        self.custom_active_defenses = defenses

    def deploy_soldier_to_tower(
        self,
        tower_id: str,
        soldier_type: Union[SoldierType, str] = SoldierType.INFANTRY,
        soldier_id: Optional[str] = None,
    ) -> DefenseUnit:
        """Deploys a soldier to an elevated tower in the scenario."""
        elevated_node = self.scenario_service.elevated_graph.get_elevated_node(tower_id)
        if not elevated_node:
            raise ValueError(f"Tower '{tower_id}' not found in Elevated Network.")

        elevated_node.is_active_tower = True
        s_id = soldier_id or f"soldier_{tower_id}_{len(elevated_node.stationed_soldiers) + 1}"
        if s_id not in elevated_node.stationed_soldiers:
            elevated_node.stationed_soldiers.append(s_id)

        # Store in simulation state
        from app.domain.soldier import Soldier
        s_obj = Soldier(
            soldier_type=SoldierType(soldier_type) if isinstance(soldier_type, SoldierType) else SoldierType.INFANTRY,
            soldier_id=s_id,
            location_node_id=tower_id,
        )
        self.scenario_service.simulation_state.soldiers[s_id] = s_obj

        unit = DefenseUnit(
            soldier_type=soldier_type,
            x=elevated_node.x,
            y=elevated_node.y,
            z=elevated_node.z,
            unit_id=s_id,
            tower_id=tower_id,
            beta=self.scenario_service.simulation_state.beta_elevation,
        )
        return unit

    def get_active_defenses(self) -> List[DefenseUnit]:
        """Extracts active defense units deployed in the elevated network."""
        if self.custom_active_defenses is not None:
            return list(self.custom_active_defenses)

        active_units: List[DefenseUnit] = []
        beta = self.scenario_service.simulation_state.beta_elevation

        for node_id, node in self.scenario_service.elevated_graph.elevated_nodes.items():
            if not node.is_active_tower:
                continue

            for s_id in node.stationed_soldiers:
                soldier = self.scenario_service.simulation_state.soldiers.get(s_id)
                if soldier:
                    unit = DefenseUnit(
                        soldier_type=soldier.soldier_type,
                        x=node.x,
                        y=node.y,
                        z=node.z,
                        unit_id=s_id,
                        tower_id=node.id,
                        beta=beta,
                    )
                    active_units.append(unit)
                else:
                    # Deduce from soldier ID or default to Infantry
                    s_type = SoldierType.INFANTRY
                    sid_lower = s_id.lower()
                    if "snip" in sid_lower or "franc" in sid_lower:
                        s_type = SoldierType.SNIPER
                    elif "gun" in sid_lower or "art" in sid_lower:
                        s_type = SoldierType.GUNNER
                    unit = DefenseUnit(
                        soldier_type=s_type,
                        x=node.x,
                        y=node.y,
                        z=node.z,
                        unit_id=s_id,
                        tower_id=node.id,
                        beta=beta,
                    )
                    active_units.append(unit)

        return active_units

    def evaluate_all_corridors(
        self,
        alpha: Optional[float] = None,
        active_defenses: Optional[List[DefenseUnit]] = None,
    ) -> Dict[str, Any]:
        """Evaluates hazard rates and reactive weights for all corridors in G_M."""
        if alpha is None:
            alpha = self.scenario_service.simulation_state.alpha_danger
        alpha = max(0.0, float(alpha))

        if active_defenses is None:
            active_defenses = self.get_active_defenses()

        maze_graph = self.scenario_service.maze_graph
        corridor_hazards: Dict[str, Dict[str, Any]] = {}
        max_avg_danger = 0.0

        for edge_key, corridor in maze_graph.maze_edges.items():
            hazard_res = calculate_corridor_hazard(
                corridor=corridor,
                active_defenses=active_defenses,
                alpha=alpha,
                maze_graph=maze_graph,
            )
            key_str = f"{corridor.u}-{corridor.v}"
            corridor_hazards[key_str] = hazard_res.to_dict()
            if hazard_res.avg_danger > max_avg_danger:
                max_avg_danger = hazard_res.avg_danger

        return {
            "alpha_danger": alpha,
            "max_avg_danger": round(max_avg_danger, 2),
            "corridor_hazards": corridor_hazards,
            "active_defenses_count": len(active_defenses),
        }
