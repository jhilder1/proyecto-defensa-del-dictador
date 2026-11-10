"""Service for loading, parsing and managing scenario data."""

from typing import Dict, Any, Optional, List
import json
import os
from app.core.elevated_graph import ElevatedGraph
from app.core.maze_graph import MazeGraph
from app.domain.node import ElevatedNodeType
from app.domain.enemy import EnemyMachine, EnemyType
from app.domain.simulation_state import SimulationState


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

    @classmethod
    def get_instance(cls) -> "ScenarioService":
        if cls._instance is None:
            cls._instance = ScenarioService()
        return cls._instance

    def load_from_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parses a scenario dictionary and constructs the graphs and domain entities."""
        self.scenario_name = data.get("scenario_name", "Escenario Personalizado")

        # Config
        cfg = data.get("config", {})
        initial_budget = cfg.get("initial_budget", 1200.0)
        beta_elevation = cfg.get("beta_elevation", 0.1)
        alpha_danger = cfg.get("alpha_danger", 1.0)
        d0_normalization = cfg.get("d0_normalization", 50.0)
        helicopter_cost = cfg.get("helicopter_cost", 150.0)
        max_time_limit = cfg.get("max_time_limit", 300.0)

        self.simulation_state = SimulationState(
            initial_budget=initial_budget,
            helicopter_cost=helicopter_cost,
            beta_elevation=beta_elevation,
            alpha_danger=alpha_danger,
            d0_normalization=d0_normalization,
            max_time_limit=max_time_limit,
        )

        # Build Elevated Graph
        elev_data = data.get("elevated_network", {})
        self.elevated_graph = ElevatedGraph()

        for node_info in elev_data.get("nodes", []):
            raw_type = node_info.get("type", "Tránsito")
            # Map type string to enum safely
            matched_type = ElevatedNodeType.TRANSITO
            for t in ElevatedNodeType:
                if t.value.lower() == raw_type.lower():
                    matched_type = t
                    break

            self.elevated_graph.add_elevated_node(
                node_id=str(node_info["id"]),
                x=float(node_info["x"]),
                y=float(node_info["y"]),
                z=float(node_info.get("z", 0.0)),
                node_type=matched_type,
                surveillance_radius=float(node_info.get("surveillance_radius", 20.0)),
            )

        for edge_info in elev_data.get("edges", []):
            self.elevated_graph.add_elevated_edge(
                u=str(edge_info["u"]),
                v=str(edge_info["v"]),
                foot_time=float(edge_info.get("foot_time", 10.0)),
                moto_time=float(edge_info.get("moto_time", 4.0)),
                is_bridge=bool(edge_info.get("is_bridge", False)),
                max_resistance=int(edge_info.get("max_resistance", 3)),
                reconstruction_duration=float(edge_info.get("reconstruction_duration", 30.0)),
            )

        # Build Maze Graph
        maze_data = data.get("maze_network", {})
        self.maze_graph = MazeGraph()

        for node_info in maze_data.get("nodes", []):
            self.maze_graph.add_maze_node(
                node_id=str(node_info["id"]),
                x=float(node_info["x"]),
                y=float(node_info["y"]),
                is_entry=bool(node_info.get("is_entry", False)),
                is_exit=bool(node_info.get("is_exit", False)),
            )

        for corr_info in maze_data.get("corridors", []):
            length = corr_info.get("length")
            if length is not None:
                length = float(length)
            self.maze_graph.add_corridor(
                u=str(corr_info["u"]),
                v=str(corr_info["v"]),
                length=length,
                speed=float(corr_info.get("speed", 1.0)),
            )

        # Build Enemies
        self.simulation_state.enemies.clear()
        for enemy_info in data.get("convoy", []):
            raw_type = enemy_info.get("type", "Tanque")
            matched_enemy_type = EnemyType.TANK
            for et in EnemyType:
                if et.value.lower() == raw_type.lower():
                    matched_enemy_type = et
                    break

            hp = enemy_info.get("hp")
            reward = enemy_info.get("reward")
            machine = EnemyMachine(
                enemy_type=matched_enemy_type,
                custom_hp=float(hp) if hp is not None else None,
                custom_reward=int(reward) if reward is not None else None,
            )
            self.simulation_state.enemies.append(machine)

        # Reset planning results
        self.mst_result = None
        self.tower_selection_result = None

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
                "beta_elevation": self.simulation_state.beta_elevation,
                "alpha_danger": self.simulation_state.alpha_danger,
                "d0_normalization": self.simulation_state.d0_normalization,
                "helicopter_cost": self.simulation_state.helicopter_cost,
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
            "mst_result": self.mst_result,
            "tower_selection_result": self.tower_selection_result,
        }

