"""Simulation Service for Reactive Convoy Navigation & Anti-Backtracking Rule.

Models convoy step progression through G_M.
At each visited intersection:
  1. Recalculates reactive corridor weights w(e) considering active defenses.
  2. Runs deterministic reactive Dijkstra to find optimal route to exit.
  3. Enforces the Anti-Backtracking Rule:
     - If optimal next node is immediately previous node visited (backtrack):
       - Evaluates alternative viable routes via neighbors other than previous node.
       - Selects best viable alternative route that reaches exit without backtracking.
       - Backtracking is permitted strictly if and only if no alternative viable route exists (dead-end).
  4. Maintains convoy HP, path history, step events, and status (in-progress, escaped, destroyed).
"""

from typing import Dict, List, Tuple, Optional, Any
from app.core.algorithms import dijkstra_reactive
from app.core.maze_graph import MazeGraph
from app.domain.enemy import EnemyMachine, EnemyType
from app.services.scenario_service import ScenarioService
from app.services.hazard_service import HazardService, DefenseUnit


class SimulationService:
    """Manages reactive convoy navigation simulation over G_M."""

    _instance: Optional["SimulationService"] = None

    def __init__(
        self,
        scenario_service: Optional[ScenarioService] = None,
        hazard_service: Optional[HazardService] = None,
    ):
        self._scenario_service = scenario_service
        self.hazard_service = hazard_service or (
            HazardService(self._scenario_service) if self._scenario_service is not None else HazardService.get_instance()
        )

        self.current_node: str = "IN"
        self.previous_node: Optional[str] = None
        self.target_node: str = "OUT"
        self.alpha_danger: float = self.scenario_service.simulation_state.alpha_danger

        self.step_index: int = 0
        self.visited_nodes: List[str] = [self.current_node]
        self.traversed_edges: List[Tuple[str, str]] = []
        self.total_damage_taken: float = 0.0
        self.total_time_elapsed: float = 0.0

        self.is_finished: bool = False
        self.escaped: bool = False
        self.destroyed: bool = False
        self.backtrack_count: int = 0
        self.step_history: List[Dict[str, Any]] = []

        self._initialize_from_scenario()

    @property
    def scenario_service(self) -> ScenarioService:
        if self._scenario_service is not None:
            return self._scenario_service
        return ScenarioService.get_instance()

    @classmethod
    def get_instance(cls) -> "SimulationService":
        if cls._instance is None:
            cls._instance = SimulationService()
        return cls._instance

    def _initialize_from_scenario(self) -> None:
        """Initializes entry and exit nodes from active maze network."""
        maze_graph = self.scenario_service.maze_graph

        entry_nodes = maze_graph.get_entry_nodes()
        if entry_nodes:
            self.current_node = entry_nodes[0].id
        elif maze_graph.has_node("IN"):
            self.current_node = "IN"
        elif maze_graph.nodes:
            self.current_node = sorted(maze_graph.nodes.keys())[0]

        exit_nodes = maze_graph.get_exit_nodes()
        if exit_nodes:
            self.target_node = exit_nodes[0].id
        elif maze_graph.has_node("OUT"):
            self.target_node = "OUT"
        elif maze_graph.nodes:
            self.target_node = sorted(maze_graph.nodes.keys())[-1]

        self.visited_nodes = [self.current_node]
        self.previous_node = None
        self.step_index = 0
        self.traversed_edges = []
        self.total_damage_taken = 0.0
        self.total_time_elapsed = 0.0
        self.is_finished = False
        self.escaped = False
        self.destroyed = False
        self.backtrack_count = 0
        self.step_history = []

        # If no enemies are defined, initialize default convoy
        if not self.scenario_service.simulation_state.enemies:
            self.scenario_service.simulation_state.enemies = [
                EnemyMachine(EnemyType.TANK, custom_hp=200.0, custom_reward=150),
                EnemyMachine(EnemyType.TRUCK, custom_hp=100.0, custom_reward=100),
                EnemyMachine(EnemyType.ROBOT, custom_hp=50.0, custom_reward=50),
            ]

    def reset(self, alpha_danger: Optional[float] = None) -> Dict[str, Any]:
        """Resets the convoy to the entry node, restores enemy HP, and recalculates hazards."""
        if alpha_danger is not None:
            self.alpha_danger = max(0.0, float(alpha_danger))
            self.scenario_service.simulation_state.alpha_danger = self.alpha_danger

        self._initialize_from_scenario()

        # Restore all enemies to full HP
        for enemy in self.scenario_service.simulation_state.enemies:
            enemy.current_hp = enemy.max_hp
            enemy.is_alive = True

        self.scenario_service.simulation_state.clock = 0.0
        self.scenario_service.simulation_state.is_game_over = False
        self.scenario_service.simulation_state.game_result = "En progreso"

        # Recalculate initial hazards
        hazards_res = self.hazard_service.evaluate_all_corridors(alpha=self.alpha_danger)

        # Initial Dijkstra route projection
        initial_route = dijkstra_reactive(
            self.scenario_service.maze_graph,
            self.current_node,
            self.target_node,
        )

        return {
            "status": "reset",
            "current_node": self.current_node,
            "previous_node": self.previous_node,
            "target_node": self.target_node,
            "hp": self.get_total_hp(),
            "max_hp": self.get_max_hp(),
            "path_taken": list(self.visited_nodes),
            "projected_path": initial_route[1] if initial_route else [],
            "projected_cost": round(initial_route[0], 2) if initial_route else 0.0,
            "is_finished": self.is_finished,
            "escaped": self.escaped,
            "destroyed": self.destroyed,
            "corridor_hazards": hazards_res.get("corridor_hazards", {}),
            "convoy_status": self.get_convoy_status(),
        }

    def get_total_hp(self) -> float:
        return sum(e.current_hp for e in self.scenario_service.simulation_state.enemies)

    def get_max_hp(self) -> float:
        return sum(e.max_hp for e in self.scenario_service.simulation_state.enemies)

    def get_convoy_status(self) -> Dict[str, Any]:
        alive_enemies = self.scenario_service.simulation_state.get_alive_enemies()
        total_hp = self.get_total_hp()
        max_hp = self.get_max_hp()

        return {
            "is_alive": total_hp > 0 and len(alive_enemies) > 0,
            "total_hp": round(total_hp, 2),
            "max_total_hp": round(max_hp, 2),
            "machines": [e.to_dict() for e in self.scenario_service.simulation_state.enemies],
        }

    def evaluate_step_decision(self, alpha: float) -> Dict[str, Any]:
        """Evaluates the next step decision using Dijkstra and the Anti-Backtracking rule."""
        maze_graph = self.scenario_service.maze_graph

        if self.current_node == self.target_node:
            return {
                "type": "REACHED_EXIT",
                "chosen_next_node": None,
                "projected_path": [self.target_node],
                "raw_shortest_path": [self.target_node],
                "raw_cost": 0.0,
                "backtrack_prevented": False,
                "discarded_node": None,
                "discarded_edge": None,
                "discarded_reason": None,
                "alternative_taken": False,
                "alternative_paths_evaluated": [],
            }

        # 1. Unconstrained Dijkstra
        unconstrained_res = dijkstra_reactive(
            graph=maze_graph,
            start_node=self.current_node,
            target_node=self.target_node,
        )

        if unconstrained_res is None:
            return {
                "type": "NO_ROUTE",
                "chosen_next_node": None,
                "projected_path": [],
                "raw_shortest_path": [],
                "raw_cost": float("inf"),
                "backtrack_prevented": False,
                "discarded_node": None,
                "discarded_edge": None,
                "discarded_reason": f"No existe ninguna ruta desde '{self.current_node}' hacia '{self.target_node}'.",
                "alternative_taken": False,
                "alternative_paths_evaluated": [],
            }

        raw_cost, raw_path = unconstrained_res
        next_candidate = raw_path[1] if len(raw_path) > 1 else None

        # 2. Check Anti-Backtracking condition
        if self.previous_node is not None and next_candidate == self.previous_node:
            # Backtrack detected! Evaluate alternative routes avoiding the immediately previous node
            alt_neighbors = [
                v for v in sorted(maze_graph.neighbors(self.current_node))
                if v != self.previous_node
            ]

            alternative_paths: List[Dict[str, Any]] = []

            for alt_v in alt_neighbors:
                corr = maze_graph.get_corridor(self.current_node, alt_v)
                w_edge = corr.reactive_weight if corr else 1.0

                if alt_v == self.target_node:
                    alternative_paths.append({
                        "next_node": alt_v,
                        "path": [self.current_node, alt_v],
                        "cost": round(w_edge, 4),
                    })
                    continue

                # Dijkstra from alt_v to target forbidding edge back to current_node
                res_from_v = dijkstra_reactive(
                    graph=maze_graph,
                    start_node=alt_v,
                    target_node=self.target_node,
                    forbidden_edge=(self.current_node, alt_v),
                )

                if res_from_v is not None:
                    cost_from_v, path_from_v = res_from_v
                    total_alt_cost = w_edge + cost_from_v
                    full_alt_path = [self.current_node] + path_from_v
                    alternative_paths.append({
                        "next_node": alt_v,
                        "path": full_alt_path,
                        "cost": round(total_alt_cost, 4),
                    })
                else:
                    # General check from alt_v if path does not immediately return to current_node
                    res_gen = dijkstra_reactive(
                        graph=maze_graph,
                        start_node=alt_v,
                        target_node=self.target_node,
                    )
                    if res_gen is not None:
                        cost_gen, path_gen = res_gen
                        if len(path_gen) > 1 and path_gen[1] != self.current_node:
                            alternative_paths.append({
                                "next_node": alt_v,
                                "path": [self.current_node] + path_gen,
                                "cost": round(w_edge + cost_gen, 4),
                            })

            if alternative_paths:
                # Deterministic selection: Lowest cost, then lexicographical next_node
                alternative_paths.sort(key=lambda item: (item["cost"], item["next_node"]))
                best_alt = alternative_paths[0]

                return {
                    "type": "ANTI_BACKTRACK_AVOIDED",
                    "chosen_next_node": best_alt["next_node"],
                    "projected_path": best_alt["path"],
                    "raw_shortest_path": raw_path,
                    "raw_cost": raw_cost,
                    "backtrack_prevented": True,
                    "discarded_node": self.previous_node,
                    "discarded_edge": [self.current_node, self.previous_node],
                    "discarded_reason": f"Ruta óptima implicaba retroceder de inmediato a '{self.previous_node}'. Regla anti-retroceso activada.",
                    "alternative_taken": True,
                    "alternative_paths_evaluated": alternative_paths,
                }
            else:
                # Dead-end! No alternative viable route to target_node exists
                # Backtracking permitted strictly as last resort
                return {
                    "type": "FORCED_DEAD_END_BACKTRACK",
                    "chosen_next_node": self.previous_node,
                    "projected_path": raw_path,
                    "raw_shortest_path": raw_path,
                    "raw_cost": raw_cost,
                    "backtrack_prevented": False,
                    "discarded_node": None,
                    "discarded_edge": None,
                    "discarded_reason": f"Callejón sin salida en '{self.current_node}': no existe ruta alternativa hacia '{self.target_node}'. Retroceso permitido como último recurso hacia '{self.previous_node}'.",
                    "alternative_taken": False,
                    "alternative_paths_evaluated": [],
                }

        # 3. Standard optimal forward step
        return {
            "type": "OPTIMAL",
            "chosen_next_node": next_candidate,
            "projected_path": raw_path,
            "raw_shortest_path": raw_path,
            "raw_cost": raw_cost,
            "backtrack_prevented": False,
            "discarded_node": None,
            "discarded_edge": None,
            "discarded_reason": None,
            "alternative_taken": False,
            "alternative_paths_evaluated": [],
        }

    def step(self, alpha_danger: Optional[float] = None) -> Dict[str, Any]:
        """Advances the convoy by exactly one intersection step."""
        if alpha_danger is not None:
            self.alpha_danger = max(0.0, float(alpha_danger))
            self.scenario_service.simulation_state.alpha_danger = self.alpha_danger

        maze_graph = self.scenario_service.maze_graph

        # If already finished, return current state
        if self.is_finished:
            hazards_res = self.hazard_service.evaluate_all_corridors(alpha=self.alpha_danger)
            return self._build_step_result(
                decision={"type": "ALREADY_FINISHED", "projected_path": []},
                hazards_res=hazards_res,
            )

        # 1. Recalculate reactive corridor weights considering currently active defenses
        hazards_res = self.hazard_service.evaluate_all_corridors(alpha=self.alpha_danger)

        # 2. Evaluate decision at current intersection
        decision = self.evaluate_step_decision(alpha=self.alpha_danger)
        chosen_next = decision.get("chosen_next_node")

        if not chosen_next:
            if decision.get("type") == "REACHED_EXIT":
                self.is_finished = True
                self.escaped = True
                self.scenario_service.simulation_state.is_game_over = True
                self.scenario_service.simulation_state.game_result = "Convoy escapó"
            else:
                self.is_finished = True
                self.escaped = False
                self.scenario_service.simulation_state.is_game_over = True
                self.scenario_service.simulation_state.game_result = "Convoy sin ruta"

            return self._build_step_result(decision=decision, hazards_res=hazards_res)

        # 3. Traverse corridor (current_node -> chosen_next)
        corridor = maze_graph.get_corridor(self.current_node, chosen_next)
        if corridor is not None:
            traverse_time = corridor.base_time
            damage_inflicted = corridor.danger_potential
        else:
            traverse_time = 1.0
            damage_inflicted = 0.0

        # Apply damage sequentially front-to-back to enemy machines
        remaining_damage = damage_inflicted
        for machine in self.scenario_service.simulation_state.enemies:
            if machine.is_alive and remaining_damage > 0:
                actual_dmg = machine.take_damage(remaining_damage)
                remaining_damage -= actual_dmg

        self.total_damage_taken += damage_inflicted
        self.total_time_elapsed += traverse_time
        self.scenario_service.simulation_state.clock += traverse_time

        if decision.get("backtrack_prevented"):
            self.backtrack_count += 1

        # Advance positions
        self.step_index += 1
        edge_traversed = (self.current_node, chosen_next)
        self.traversed_edges.append(edge_traversed)
        self.previous_node = self.current_node
        self.current_node = chosen_next
        self.visited_nodes.append(self.current_node)

        # Check termination conditions
        alive_enemies = self.scenario_service.simulation_state.get_alive_enemies()
        if not alive_enemies or self.get_total_hp() <= 0:
            self.is_finished = True
            self.destroyed = True
            self.escaped = False
            self.scenario_service.simulation_state.is_game_over = True
            self.scenario_service.simulation_state.game_result = "Convoy destruido"
        elif self.current_node == self.target_node:
            self.is_finished = True
            self.escaped = True
            self.destroyed = False
            self.scenario_service.simulation_state.is_game_over = True
            self.scenario_service.simulation_state.game_result = "Convoy escapó"

        result = self._build_step_result(decision=decision, hazards_res=hazards_res)
        self.step_history.append(result)
        return result

    def run(self, alpha_danger: Optional[float] = None, max_steps: int = 100) -> Dict[str, Any]:
        """Runs the convoy simulation until completion or step limit."""
        steps: List[Dict[str, Any]] = []

        while not self.is_finished and len(steps) < max_steps:
            step_res = self.step(alpha_danger=alpha_danger)
            steps.append(step_res)

        return {
            "total_steps": len(steps),
            "is_finished": self.is_finished,
            "escaped": self.escaped,
            "destroyed": self.destroyed,
            "current_node": self.current_node,
            "total_hp": round(self.get_total_hp(), 2),
            "total_damage_taken": round(self.total_damage_taken, 2),
            "total_time_elapsed": round(self.total_time_elapsed, 2),
            "backtracks_prevented": self.backtrack_count,
            "path_taken": list(self.visited_nodes),
            "steps": steps,
        }

    def _build_step_result(
        self,
        decision: Dict[str, Any],
        hazards_res: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "current_node": self.current_node,
            "previous_node": self.previous_node,
            "target_node": self.target_node,
            "hp": round(self.get_total_hp(), 2),
            "max_hp": round(self.get_max_hp(), 2),
            "path_taken": list(self.visited_nodes),
            "projected_path": decision.get("projected_path", []),
            "backtrack_prevented": decision.get("backtrack_prevented", False),
            "discarded_edge": decision.get("discarded_edge"),
            "discarded_node": decision.get("discarded_node"),
            "alternative_taken": decision.get("alternative_taken", False),
            "is_finished": self.is_finished,
            "escaped": self.escaped,
            "destroyed": self.destroyed,
            "corridor_hazards": hazards_res.get("corridor_hazards", {}),
            "dijkstra": {
                "raw_shortest_path": decision.get("raw_shortest_path", []),
                "raw_cost": round(decision.get("raw_cost", 0.0), 2) if decision.get("raw_cost") != float("inf") else -1.0,
                "tie_broken": False,
            },
            "decision": {
                "type": decision.get("type", "UNKNOWN"),
                "chosen_next_node": decision.get("chosen_next_node"),
                "backtrack_prevented": decision.get("backtrack_prevented", False),
                "discarded_node": decision.get("discarded_node"),
                "discarded_reason": decision.get("discarded_reason"),
                "alternative_paths_evaluated": decision.get("alternative_paths_evaluated", []),
            },
            "convoy_status": self.get_convoy_status(),
            "history": {
                "visited_nodes": list(self.visited_nodes),
                "traversed_edges": [[u, v] for u, v in self.traversed_edges],
                "total_damage_taken": round(self.total_damage_taken, 2),
                "total_time_elapsed": round(self.total_time_elapsed, 2),
            },
        }
