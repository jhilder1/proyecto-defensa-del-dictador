"""Unit tests for Stage 3 Anti-Backtracking Rule (Requirement R4, F9).

Verifies:
- Detection of immediate backtracking condition (optimal next == previous_node)
- Evaluation and selection of best viable alternative forward route to exit
- Acceptance of backtracking strictly and only in dead-end scenarios (callejón sin salida)
- Deterministic tie-breaking between multiple viable alternatives
"""

import pytest
from app.core.maze_graph import MazeGraph
from app.services.scenario_service import ScenarioService
from app.services.hazard_service import HazardService
from app.services.simulation_service import SimulationService


class TestAntiBacktrackingRule:
    def test_diverts_to_viable_alternative_when_backtrack_optimal(self):
        """Scenario:
        IN -> M1 -> M2 -> M3 -> OUT
        Also corridor between M1 and OUT exists, but initially heavy.
        Convoy moves from IN to M1.
        At M1, suppose the path through IN (e.g. IN -> ALT -> OUT) has lower unconstrained cost,
        OR unconstrained Dijkstra says the optimal step is to return to IN.
        Because convoy arrived from IN, anti-backtracking triggers!
        The convoy selects the alternative path without returning to IN.
        """
        scenario_srv = ScenarioService()
        gm = MazeGraph()

        # Nodes
        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("M1", 10, 0)
        gm.add_maze_node("M2", 20, 0)
        gm.add_maze_node("ALT", 0, 10)
        gm.add_maze_node("OUT", 30, 0, is_exit=True)

        # Corridors:
        # IN -> M1: weight 5
        gm.add_corridor("IN", "M1", length=5.0, speed=1.0)
        # M1 -> M2: weight 10
        gm.add_corridor("M1", "M2", length=10.0, speed=1.0)
        # M2 -> OUT: weight 5
        gm.add_corridor("M2", "OUT", length=5.0, speed=1.0)
        # IN -> ALT -> OUT: very cheap route from IN (IN->ALT: 2, ALT->OUT: 2)
        gm.add_corridor("IN", "ALT", length=2.0, speed=1.0)
        gm.add_corridor("ALT", "OUT", length=2.0, speed=1.0)

        scenario_srv.maze_graph = gm
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        # Step 1: Convoy starts at IN. Optimal route is IN -> ALT -> OUT (cost 4).
        # But if it steps to M1:
        sim_srv.current_node = "M1"
        sim_srv.previous_node = "IN"
        sim_srv.visited_nodes = ["IN", "M1"]

        # At M1:
        # Route 1 (backtrack to IN): M1 -> IN -> ALT -> OUT. Cost = 5 + 2 + 2 = 9.0
        # Route 2 (forward through M2): M1 -> M2 -> OUT. Cost = 10 + 5 = 15.0
        # Unconstrained Dijkstra would choose M1 -> IN (cost 9)!
        # BUT IN is previous_node! Anti-backtracking must trigger and divert to M2!
        decision = sim_srv.evaluate_step_decision(alpha=1.0)

        assert decision["type"] == "ANTI_BACKTRACK_AVOIDED"
        assert decision["backtrack_prevented"] is True
        assert decision["discarded_node"] == "IN"
        assert decision["chosen_next_node"] == "M2"
        assert decision["alternative_taken"] is True
        assert decision["projected_path"] == ["M1", "M2", "OUT"]

    def test_dead_end_allows_backtracking_as_last_resort(self):
        """Scenario: Dead-end corridor (callejón sin salida).
        IN -> M1 -> DEAD_END
        DEAD_END has no connections other than M1.
        Convoy arrived from M1 to DEAD_END.
        At DEAD_END, there is NO alternative route to OUT.
        Backtracking to M1 must be permitted strictly as a last resort.
        """
        scenario_srv = ScenarioService()
        gm = MazeGraph()

        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("M1", 10, 0)
        gm.add_maze_node("DEAD", 10, 10)  # Leaf node
        gm.add_maze_node("OUT", 20, 0, is_exit=True)

        gm.add_corridor("IN", "M1", length=5.0, speed=1.0)
        gm.add_corridor("M1", "DEAD", length=3.0, speed=1.0)
        gm.add_corridor("M1", "OUT", length=10.0, speed=1.0)

        scenario_srv.maze_graph = gm
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        # Convoy arrived at DEAD from M1
        sim_srv.current_node = "DEAD"
        sim_srv.previous_node = "M1"
        sim_srv.visited_nodes = ["IN", "M1", "DEAD"]

        decision = sim_srv.evaluate_step_decision(alpha=1.0)

        assert decision["type"] == "FORCED_DEAD_END_BACKTRACK"
        assert decision["chosen_next_node"] == "M1"
        assert decision["backtrack_prevented"] is False
        assert "Callejón sin salida" in decision["discarded_reason"]

    def test_alternative_selection_tie_breaking(self):
        """When multiple non-backtracking alternatives exist with equal cost,
        tie is deterministically broken by lexicographical node ID.
        """
        scenario_srv = ScenarioService()
        gm = MazeGraph()

        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("CURR", 10, 0)
        gm.add_maze_node("ALT_B", 20, -5)
        gm.add_maze_node("ALT_C", 20, 5)
        gm.add_maze_node("SHORT_BACK", 0, 10)
        gm.add_maze_node("OUT", 30, 0, is_exit=True)

        # Backtrack route through IN: CURR -> IN -> SHORT_BACK -> OUT: cost 2 + 1 + 1 = 4.0
        gm.add_corridor("IN", "CURR", length=2.0, speed=1.0)
        gm.add_corridor("IN", "SHORT_BACK", length=1.0, speed=1.0)
        gm.add_corridor("SHORT_BACK", "OUT", length=1.0, speed=1.0)

        # Alternative B: CURR -> ALT_B -> OUT: cost 5 + 5 = 10.0
        gm.add_corridor("CURR", "ALT_B", length=5.0, speed=1.0)
        gm.add_corridor("ALT_B", "OUT", length=5.0, speed=1.0)

        # Alternative C: CURR -> ALT_C -> OUT: cost 5 + 5 = 10.0
        gm.add_corridor("CURR", "ALT_C", length=5.0, speed=1.0)
        gm.add_corridor("ALT_C", "OUT", length=5.0, speed=1.0)

        scenario_srv.maze_graph = gm
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        sim_srv.current_node = "CURR"
        sim_srv.previous_node = "IN"

        decision = sim_srv.evaluate_step_decision(alpha=1.0)
        assert decision["type"] == "ANTI_BACKTRACK_AVOIDED"
        # ALT_B < ALT_C lexicographically
        assert decision["chosen_next_node"] == "ALT_B"

    def test_first_step_from_entry_has_no_backtrack(self):
        """At start node with previous_node=None, normal optimal forward navigation proceeds."""
        scenario_srv = ScenarioService()
        gm = MazeGraph()

        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("M1", 10, 0)
        gm.add_maze_node("OUT", 20, 0, is_exit=True)

        gm.add_corridor("IN", "M1", length=5.0, speed=1.0)
        gm.add_corridor("M1", "OUT", length=5.0, speed=1.0)

        scenario_srv.maze_graph = gm
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        decision = sim_srv.evaluate_step_decision(alpha=1.0)
        assert decision["type"] == "OPTIMAL"
        assert decision["chosen_next_node"] == "M1"
        assert decision["backtrack_prevented"] is False
