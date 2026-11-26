"""Service for loading, parsing, validating and managing scenario data."""

from typing import Dict, Any, Optional, List, Set
import json
import math
import os
from app.core.algorithms import dijkstra_reactive
from app.core.elevated_graph import ElevatedGraph
from app.core.maze_graph import MazeGraph
from app.domain.node import ElevatedNodeType
from app.domain.enemy import EnemyMachine, EnemyType
from app.domain.simulation_state import SimulationState


def _parse_enemy_type(raw_type: str) -> EnemyType:
    text = str(raw_type).strip().lower()
    if "tanque" in text or "tank" in text:
        return EnemyType.TANK
    if "camión" in text or "camion" in text or "truck" in text:
        return EnemyType.TRUCK
    if "robot" in text:
        return EnemyType.ROBOT
    raise ValueError(f"Tipo de máquina enemiga desconocido: '{raw_type}'")


class ScenarioService:
    """Manages active scenario graphs, units and parameters."""

    _instance: Optional["ScenarioService"] = None

    def __init__(self):
        self.scenario_name: str = "Sin escenario cargado"
        self.elevated_graph: ElevatedGraph = ElevatedGraph()
        self.maze_graph: MazeGraph = MazeGraph()
        self.simulation_state: SimulationState = SimulationState()
        self.mst_result: Optional[Dict[str, Any]] = None
        self.tower_selection_result: Optional[Dict[str, Any]] = None
        self.initial_maze_route: Optional[Dict[str, Any]] = None

    @classmethod
    def get_instance(cls) -> "ScenarioService":
        if cls._instance is None:
            cls._instance = ScenarioService()
        return cls._instance

    def load_from_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parses a scenario dictionary, validates PDF invariants, and constructs domain entities."""
        scenario_name = data.get("scenario_name", "Escenario Personalizado")

        # Config
        cfg = data.get("config", {})
        initial_budget = float(cfg.get("initial_budget", 1200.0))
        if initial_budget < 0 or not math.isfinite(initial_budget):
            raise ValueError("El presupuesto inicial debe ser finito y no negativo.")

        beta_elevation = float(cfg.get("beta_elevation", 0.1))
        alpha_danger = float(cfg.get("alpha_danger", 1.0))
        if beta_elevation < 0 or alpha_danger < 0:
            raise ValueError("Los coeficientes beta y alpha deben ser mayores o iguales a 0.")

        d0_normalization = float(cfg.get("d0_normalization", 50.0))
        if d0_normalization <= 0:
            raise ValueError("El parámetro de normalización D0 debe ser positivo.")

        helicopter_cost = float(cfg.get("helicopter_cost", 150.0))
        helicopter_speed = float(cfg.get("helicopter_speed", 15.0))
        max_helicopter_uses = int(cfg.get("max_helicopter_uses", 5))
        helicopter_fleet_size = int(cfg.get("helicopter_fleet_size", 1))
        total_repair_personnel = int(cfg.get("total_repair_personnel", 4))
        max_time_limit = float(cfg.get("max_time_limit", 300.0))

        sim_state = SimulationState(
            initial_budget=initial_budget,
            helicopter_cost=helicopter_cost,
            helicopter_speed=helicopter_speed,
            max_helicopter_uses=max_helicopter_uses,
            helicopter_fleet_size=helicopter_fleet_size,
            total_repair_personnel=total_repair_personnel,
            beta_elevation=beta_elevation,
            alpha_danger=alpha_danger,
            d0_normalization=d0_normalization,
            max_time_limit=max_time_limit,
        )

        # Build & Validate Elevated Graph (G_E)
        elev_data = data.get("elevated_network", {})
        elevated_graph = ElevatedGraph()
        seen_elev_ids: Set[str] = set()

        for node_info in elev_data.get("nodes", []):
            nid = str(node_info["id"])
            if nid in seen_elev_ids:
                raise ValueError(f"Identificador duplicado en G_E: '{nid}'.")
            seen_elev_ids.add(nid)

            x = float(node_info["x"])
            y = float(node_info["y"])
            z = float(node_info.get("z", 0.0))
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                raise ValueError(f"Coordenadas no finitas en nodo G_E '{nid}'.")
            if x < 0 or y < 0 or z < 0:
                raise ValueError(f"Las coordenadas y altura de G_E deben ser no negativas (nodo '{nid}').")

            raw_type = node_info.get("type", "Tránsito")
            matched_type = ElevatedNodeType.TRANSITO
            for t in ElevatedNodeType:
                if t.value.lower() == str(raw_type).lower():
                    matched_type = t
                    break

            elevated_graph.add_elevated_node(
                node_id=nid,
                x=x,
                y=y,
                z=z,
                node_type=matched_type,
                surveillance_radius=float(node_info.get("surveillance_radius", 20.0)),
            )

        base_nodes = [
            n for n in elevated_graph.elevated_nodes.values()
            if n.node_type == ElevatedNodeType.BASE
        ]
        if len(base_nodes) != 1:
            raise ValueError(
                f"El grafo elevado G_E debe tener exactamente una Base (encontradas: {len(base_nodes)})."
            )

        for edge_info in elev_data.get("edges", []):
            u = str(edge_info["u"])
            v = str(edge_info["v"])
            if not elevated_graph.has_node(u) or not elevated_graph.has_node(v):
                raise ValueError(f"Arista G_E ({u}-{v}) referencia nodos inexistentes.")
            if u == v:
                raise ValueError(f"No se permiten auto-lazos en G_E ({u}-{v}).")

            raw_foot = edge_info["foot_time"] if "foot_time" in edge_info else 10.0
            raw_moto = edge_info["moto_time"] if "moto_time" in edge_info else 4.0
            foot_time = float(raw_foot) if raw_foot is not None else None
            moto_time = float(raw_moto) if raw_moto is not None else None

            if foot_time is None and moto_time is None:
                raise ValueError(f"La arista G_E ({u}-{v}) debe permitir al menos un medio (pie o moto).")
            if foot_time is not None and (foot_time <= 0 or not math.isfinite(foot_time)):
                raise ValueError(f"El tiempo a pie en ({u}-{v}) debe ser positivo.")
            if moto_time is not None and (moto_time <= 0 or not math.isfinite(moto_time)):
                raise ValueError(f"El tiempo en moto en ({u}-{v}) debe ser positivo.")

            is_bridge = bool(edge_info.get("is_bridge", False))
            max_res = int(edge_info.get("max_resistance", 3))
            recon_dur = float(edge_info.get("reconstruction_duration", 30.0))
            repair_pers = int(edge_info.get("repair_personnel", 2))
            if is_bridge:
                if max_res < 1:
                    raise ValueError(f"La resistencia del puente ({u}-{v}) debe ser >= 1.")
                if recon_dur <= 0:
                    raise ValueError(f"El tiempo de reconstrucción del puente ({u}-{v}) debe ser > 0.")
                if repair_pers < 1:
                    raise ValueError(f"El personal de reparación del puente ({u}-{v}) debe ser >= 1.")

            elevated_graph.add_elevated_edge(
                u=u,
                v=v,
                foot_time=foot_time,
                moto_time=moto_time,
                is_bridge=is_bridge,
                max_resistance=max_res,
                reconstruction_duration=recon_dur,
                repair_personnel=repair_pers,
            )

        # Build & Validate Maze Graph (G_M)
        maze_data = data.get("maze_network", {})
        maze_graph = MazeGraph()
        seen_maze_ids: Set[str] = set()

        for node_info in maze_data.get("nodes", []):
            nid = str(node_info["id"])
            if nid in seen_maze_ids:
                raise ValueError(f"Identificador duplicado en G_M: '{nid}'.")
            seen_maze_ids.add(nid)

            x = float(node_info["x"])
            y = float(node_info["y"])
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError(f"Coordenadas no finitas en nodo G_M '{nid}'.")

            maze_graph.add_maze_node(
                node_id=nid,
                x=x,
                y=y,
                is_entry=bool(node_info.get("is_entry", False)),
                is_exit=bool(node_info.get("is_exit", False)),
            )

        entries = maze_graph.get_entry_nodes()
        exits = maze_graph.get_exit_nodes()
        if not entries or not exits:
            raise ValueError("El grafo del laberinto G_M debe definir nodos de Entrada y Salida.")
        if entries[0].id == exits[0].id:
            raise ValueError("Los nodos de Entrada y Salida en G_M deben ser diferentes.")

        for corr_info in maze_data.get("corridors", []):
            u = str(corr_info["u"])
            v = str(corr_info["v"])
            if not maze_graph.has_node(u) or not maze_graph.has_node(v):
                raise ValueError(f"Corredor G_M ({u}-{v}) referencia nodos inexistentes.")
            if u == v:
                raise ValueError(f"No se permiten auto-lazos en G_M ({u}-{v}).")

            length = corr_info.get("length")
            if length is not None:
                length = float(length)
                if length <= 0 or not math.isfinite(length):
                    raise ValueError(f"La longitud del corredor ({u}-{v}) debe ser positiva.")

            speed = float(corr_info.get("speed", 1.0))
            if speed <= 0 or not math.isfinite(speed):
                raise ValueError(f"La velocidad del corredor ({u}-{v}) debe ser positiva.")

            maze_graph.add_corridor(u=u, v=v, length=length, speed=speed)

        initial_route = dijkstra_reactive(maze_graph, entries[0].id, exits[0].id)
        if initial_route is None:
            raise ValueError(
                f"El laberinto G_M no tiene camino inicial válido entre '{entries[0].id}' y '{exits[0].id}'."
            )

        # Build Enemies (supports both list of detailed dicts and PDF count mapping)
        raw_convoy = data.get("convoy", [])
        if isinstance(raw_convoy, dict):
            for type_name, count in raw_convoy.items():
                e_type = _parse_enemy_type(type_name)
                for _ in range(int(count)):
                    sim_state.enemies.append(EnemyMachine(enemy_type=e_type))
        elif isinstance(raw_convoy, list):
            for enemy_info in raw_convoy:
                e_type = _parse_enemy_type(enemy_info.get("type", "Tanque"))
                hp = enemy_info.get("hp")
                reward = enemy_info.get("reward")
                sim_state.enemies.append(
                    EnemyMachine(
                        enemy_type=e_type,
                        custom_hp=float(hp) if hp is not None else None,
                        custom_reward=int(reward) if reward is not None else None,
                    )
                )

        # Commit validated scenario atomically
        self.scenario_name = scenario_name
        self.simulation_state = sim_state
        self.elevated_graph = elevated_graph
        self.maze_graph = maze_graph
        self.mst_result = None
        self.tower_selection_result = None
        self.initial_maze_route = {
            "path": initial_route[1],
            "cost": round(initial_route[0], 2),
        }

        return self.get_summary()

    def load_from_file(self, filepath: str) -> Dict[str, Any]:
        """Loads and parses a JSON file from disk."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Scenario file not found at {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.load_from_dict(data)

    def get_summary(self) -> Dict[str, Any]:
        """Returns full scenario structure ready for visualizer rendering."""
        elevated_nodes_out = [n.to_dict() for n in self.elevated_graph.elevated_nodes.values()]
        elevated_edges_out = [e.to_dict() for e in self.elevated_graph.elevated_edges.values()]

        maze_nodes_out = [n.to_dict() for n in self.maze_graph.maze_nodes.values()]
        maze_edges_out = [e.to_dict() for e in self.maze_graph.maze_edges.values()]

        return {
            "scenario_name": self.scenario_name,
            "config": {
                "initial_budget": self.simulation_state.initial_budget,
                "budget_available": self.simulation_state.budget_available,
                "budget_reserved": round(self.simulation_state.budget_reserved, 2),
                "beta_elevation": self.simulation_state.beta_elevation,
                "alpha_danger": self.simulation_state.alpha_danger,
                "d0_normalization": self.simulation_state.d0_normalization,
                "helicopter_cost": self.simulation_state.helicopter_cost,
                "helicopter_speed": self.simulation_state.helicopter_speed,
                "max_helicopter_uses": self.simulation_state.max_helicopter_uses,
                "helicopter_fleet_size": self.simulation_state.helicopter_fleet_size,
                "total_repair_personnel": self.simulation_state.total_repair_personnel,
                "max_time_limit": self.simulation_state.max_time_limit,
            },
            "elevated_network": {
                "nodes": elevated_nodes_out,
                "edges": elevated_edges_out,
            },
            "maze_network": {
                "nodes": maze_nodes_out,
                "corridors": maze_edges_out,
            },
            "convoy": [e.to_dict() for e in self.simulation_state.enemies],
            "initial_maze_route": self.initial_maze_route,
            "mst_result": self.mst_result,
            "tower_selection_result": self.tower_selection_result,
        }
