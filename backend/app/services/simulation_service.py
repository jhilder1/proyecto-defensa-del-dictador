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
from app.domain.node import ElevatedNodeType
from app.services.scenario_service import ScenarioService
from app.services.hazard_service import HazardService, DefenseUnit
from app.services.logistics_service import LogisticsService
from app.services.combat_service import CombatService
from app.services.convoy_service import interpolate_convoy_position


class SimulationService:
    """Manages reactive convoy navigation simulation over G_M."""

    _instance: Optional["SimulationService"] = None

    def __init__(
        self,
        scenario_service: Optional[ScenarioService] = None,
        hazard_service: Optional[HazardService] = None,
        logistics_service: Optional[LogisticsService] = None,
        combat_service: Optional[CombatService] = None,
    ):
        self._scenario_service = scenario_service
        self.hazard_service = hazard_service or (
            HazardService(self._scenario_service) if self._scenario_service is not None else HazardService.get_instance()
        )
        self.logistics_service = logistics_service or (
            LogisticsService(self._scenario_service) if self._scenario_service is not None else LogisticsService.get_instance()
        )
        self.combat_service = combat_service or (
            CombatService(self._scenario_service) if self._scenario_service is not None else CombatService.get_instance()
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

        # Stage 5 continuous tick tracking
        self.convoy_edge: Optional[Tuple[str, str]] = None
        self.convoy_edge_progress: float = 0.0
        self.convoy_x: float = 0.0
        self.convoy_y: float = 0.0
        self.last_decision: Optional[Dict[str, Any]] = None
        self.last_combat_result: Dict[str, Any] = {}

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
        self.convoy_edge = None
        self.convoy_edge_progress = 0.0
        self.last_decision = None
        self.last_combat_result = {}

        entry_node = maze_graph.get_maze_node(self.current_node)
        self.convoy_x = entry_node.x if entry_node else 0.0
        self.convoy_y = entry_node.y if entry_node else 0.0

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

    # ------------------------------------------------------------------
    # Stage 5: Discrete Logical Clock (tick) Engine
    # ------------------------------------------------------------------

    def _advance_convoy_continuous(self, dt: float) -> List[Dict[str, Any]]:
        """Advances the convoy continuously along G_M for dt seconds without reversing mid-corridor."""
        maze_graph = self.scenario_service.maze_graph
        state = self.scenario_service.simulation_state
        events: List[Dict[str, Any]] = []
        remaining_dt = float(dt)

        if not state.get_alive_enemies():
            return events

        # If currently idle at an intersection (and not at target), select next corridor
        if self.convoy_edge is None and self.current_node != self.target_node:
            self.hazard_service.evaluate_all_corridors(alpha=self.alpha_danger)
            decision = self.evaluate_step_decision(alpha=self.alpha_danger)
            self.last_decision = decision
            chosen_next = decision.get("chosen_next_node")
            if chosen_next is not None:
                if decision.get("backtrack_prevented"):
                    self.backtrack_count += 1
                self.convoy_edge = (self.current_node, chosen_next)
                self.convoy_edge_progress = 0.0
                msg = f"Convoy en {self.current_node} eligió corredor hacia {chosen_next} ({decision.get('type')})."
                state.add_event("CONVOY_DECISION", msg, {"from": self.current_node, "to": chosen_next, "type": decision.get("type")})
                events.append({"type": "CONVOY_DECISION", "message": msg})

        while remaining_dt > 1e-9 and self.convoy_edge is not None:
            u, v = self.convoy_edge
            corridor = maze_graph.get_corridor(u, v)
            edge_duration = corridor.base_time if corridor else 1.0
            time_left = max(0.0, edge_duration - self.convoy_edge_progress)

            if remaining_dt >= time_left - 1e-9:
                remaining_dt -= time_left
                self.total_time_elapsed += time_left
                self.convoy_edge = None
                self.convoy_edge_progress = 0.0

                self.step_index += 1
                self.traversed_edges.append((u, v))
                self.previous_node = u
                self.current_node = v
                self.visited_nodes.append(v)

                node_v = maze_graph.get_maze_node(v)
                if node_v:
                    self.convoy_x = node_v.x
                    self.convoy_y = node_v.y

                if v == self.target_node:
                    break

                # Arrived at intermediate intersection: recalculate w(e) with active defenses
                if remaining_dt > 1e-9:
                    self.hazard_service.evaluate_all_corridors(alpha=self.alpha_danger)
                    decision = self.evaluate_step_decision(alpha=self.alpha_danger)
                    self.last_decision = decision
                    chosen_next = decision.get("chosen_next_node")
                    if chosen_next is None:
                        break
                    if decision.get("backtrack_prevented"):
                        self.backtrack_count += 1
                    self.convoy_edge = (self.current_node, chosen_next)
                    self.convoy_edge_progress = 0.0
                    msg = f"Convoy en {self.current_node} eligió corredor hacia {chosen_next} ({decision.get('type')})."
                    state.add_event("CONVOY_DECISION", msg, {"from": self.current_node, "to": chosen_next, "type": decision.get("type")})
                    events.append({"type": "CONVOY_DECISION", "message": msg})
            else:
                self.convoy_edge_progress += remaining_dt
                self.total_time_elapsed += remaining_dt
                remaining_dt = 0.0
                self.convoy_x, self.convoy_y = interpolate_convoy_position(
                    maze_graph, u, v, self.convoy_edge_progress, edge_duration
                )

        return events

    def tick(self, dt: float = 1.0, alpha_danger: Optional[float] = None) -> Dict[str, Any]:
        """Advances the entire simulation by one logical clock tick of dt seconds.

        Strict event order:
            1. Movements & position updates (convoy, ground transports, helicopters).
            2. Stationed soldier attacks (Infantry/Sniper lowest HP, Gunner area).
            3. Enemy destruction, bounty rewards, and reservation releases.
            4. Victory / Defeat checks (elimination, exit reached, 300s resistance).
            5. Bridge reconstruction timers.
        """
        dt = float(dt)
        if dt <= 0.0:
            raise ValueError("El intervalo dt del tick debe ser mayor a 0.")

        state = self.scenario_service.simulation_state
        if alpha_danger is not None:
            self.alpha_danger = max(0.0, float(alpha_danger))
            state.alpha_danger = self.alpha_danger

        if state.is_game_over or self.is_finished:
            return self.get_full_state(tick_events=[])

        state.is_running = True
        state.is_paused = False
        tick_events: List[Dict[str, Any]] = []

        # 1. Movements (convoy + ground & air missions)
        convoy_events = self._advance_convoy_continuous(dt)
        mission_events = self.logistics_service.advance_missions(dt)
        tick_events.extend(convoy_events)
        tick_events.extend(mission_events)

        # 2 & 3. Combat attacks, enemy destruction & bounty rewards
        combat_res = self.combat_service.execute_combat_tick(
            dt=dt,
            convoy_pos=(self.convoy_x, self.convoy_y),
            scenario_service=self.scenario_service,
        )
        self.last_combat_result = combat_res
        self.total_damage_taken += combat_res.get("total_damage_dealt", 0.0)

        # 4. Advance logical clock & check termination conditions
        state.clock = round(state.clock + dt, 6)
        alive_enemies = state.get_alive_enemies()

        if len(alive_enemies) == 0:
            state.is_game_over = True
            state.game_result = "Victoria por eliminación"
            self.is_finished = True
            self.destroyed = True
            self.escaped = False
        elif self.current_node == self.target_node and self.convoy_edge is None:
            state.is_game_over = True
            state.game_result = "Derrota"
            self.is_finished = True
            self.escaped = True
            self.destroyed = False
        elif state.clock >= state.max_time_limit - 1e-9:
            state.is_game_over = True
            state.game_result = "Victoria por resistencia"
            self.is_finished = True
            self.escaped = False
            self.destroyed = False

        if state.is_game_over:
            state.is_running = False
            state.is_paused = True
            end_msg = f"Simulación finalizada en t={round(state.clock, 2)}s: {state.game_result}."
            state.add_event("GAME_OVER", end_msg, {"result": state.game_result})
            tick_events.append({"type": "GAME_OVER", "message": end_msg})

        # 5. Update bridge reconstruction timers
        rebuilt_bridges = self.scenario_service.elevated_graph.update_reconstruction_timers(dt)
        for bridge_id in rebuilt_bridges:
            reb_msg = f"Puente {bridge_id} reconstruido completamente y operativo."
            state.add_event("BRIDGE_REBUILT", reb_msg, {"edge": bridge_id})
            tick_events.append({"type": "BRIDGE_REBUILT", "message": reb_msg})

        # Refresh corridor reactive weights for UI telemetry
        self.hazard_service.evaluate_all_corridors(alpha=self.alpha_danger)

        return self.get_full_state(
            tick_combat=combat_res,
            rebuilt_bridges=rebuilt_bridges,
            tick_events=tick_events,
        )

    def reset_full(self, alpha_danger: Optional[float] = None) -> Dict[str, Any]:
        """Performs a complete simulation reset (bridges, towers, budget, soldiers, missions, convoy)."""
        state = self.scenario_service.simulation_state
        ge = self.scenario_service.elevated_graph

        ge.reset_bridges()
        ge.reset_tower_occupancies()
        state.budget_available = state.initial_budget
        state.budget_reserved = 0.0
        state.soldiers.clear()
        state.active_missions.clear()
        state.event_log.clear()

        self.reset(alpha_danger=alpha_danger)
        state.is_running = False
        state.is_paused = True
        state.is_game_over = False
        state.game_result = "En preparación"

        return self.get_full_state()

    def get_full_state(
        self,
        tick_combat: Optional[Dict[str, Any]] = None,
        rebuilt_bridges: Optional[List[str]] = None,
        tick_events: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Returns comprehensive Stage 4 & 5 simulation state snapshot."""
        state = self.scenario_service.simulation_state
        ge = self.scenario_service.elevated_graph
        gm = self.scenario_service.maze_graph

        return {
            "clock": round(state.clock, 2),
            "max_time_limit": state.max_time_limit,
            "is_running": state.is_running,
            "is_paused": state.is_paused,
            "is_game_over": state.is_game_over,
            "game_result": state.game_result,
            "budget": {
                "initial": round(state.initial_budget, 2),
                "available": round(state.budget_available, 2),
                "reserved": round(state.budget_reserved, 2),
                "total": round(state.total_budget, 2),
            },
            "convoy": {
                "current_node": self.current_node,
                "previous_node": self.previous_node,
                "target_node": self.target_node,
                "current_edge": list(self.convoy_edge) if self.convoy_edge else None,
                "edge_progress": round(self.convoy_edge_progress, 2),
                "x": round(self.convoy_x, 2),
                "y": round(self.convoy_y, 2),
                "hp": round(self.get_total_hp(), 2),
                "max_hp": round(self.get_max_hp(), 2),
                "alive_count": len(state.get_alive_enemies()),
                "escaped": self.escaped,
                "destroyed": self.destroyed,
                "backtracks_prevented": self.backtrack_count,
                "path_taken": list(self.visited_nodes),
                "last_decision": self.last_decision,
                "machines": [e.to_dict() for e in state.enemies],
            },
            "elevated_network": {
                "nodes": [n.to_dict() for n in ge.elevated_nodes.values()],
                "edges": [e.to_dict() for e in ge.elevated_edges.values()],
                "bridges": [b.to_dict() for b in ge.get_bridges()],
                "active_towers": [
                    n.to_dict()
                    for n in ge.elevated_nodes.values()
                    if n.is_active_tower and n.node_type != ElevatedNodeType.BASE
                ],
            },
            "maze_network": {
                "nodes": [n.to_dict() for n in gm.maze_nodes.values()],
                "corridors": [c.to_dict() for c in gm.maze_edges.values()],
            },
            "soldiers": [s.to_dict() for s in state.soldiers.values()],
            "missions": [m.to_dict() for m in state.active_missions],
            "last_combat": tick_combat if tick_combat is not None else self.last_combat_result,
            "rebuilt_bridges": rebuilt_bridges or [],
            "tick_events": tick_events or [],
            "event_log": list(state.event_log[-50:]),
        }
