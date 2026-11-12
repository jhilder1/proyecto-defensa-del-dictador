"""Adversarial Challenger Test Suite (Milestone M4).

Empirically challenges and stress-tests:
1. Point hazard D(q) and the strict single-count artillery rule with 1, 2, 5, 20, 100 gunners.
2. Effective range boundary conditions (exact boundary, epsilon inside, epsilon outside, elevation scaling).
3. Corridor average D_bar(e), potential damage P(e), and reactive weight w(e) under extreme alpha (alpha=0, alpha=1e6, negative alpha clamping).
4. Custom deterministic Dijkstra: multi-way lexicographical tie-breaking, bidirectional forbidden edge isolation, unreachable components, numerical stability.
5. Anti-backtracking rule: immediate backtrack avoidance vs viable alternative routes, dead-end leaf node, multi-node dead-end subnetwork, deterministic tie-breaking among alternatives.
6. Convoy lifecycle under extreme combat environments.
"""

import math
import pytest
from app.domain.soldier import DefenseUnit, SoldierType
from app.domain.edge import MazeEdge
from app.core.maze_graph import MazeGraph
from app.core.priority_queue import PriorityQueue
from app.core.algorithms import dijkstra_reactive
from app.services.hazard_service import (
    calculate_point_damage,
    calculate_corridor_hazard,
    get_covering_defenses,
)
from app.services.scenario_service import ScenarioService
from app.services.simulation_service import SimulationService


class TestPointHazardAdversarial:
    """Stress tests for D(q) and defense coverage rules."""

    def test_single_count_artillery_massive_clustering(self):
        """CRITICAL: Single-count artillery rule under massive clustering.
        Deploying 1, 2, 5, 20, and 100 gunners covering the exact same point
        must NEVER exceed 20.0 damage rate from artillery.
        """
        target_point = (10.0, 10.0)

        # 1 gunner -> exactly 20.0
        g1 = [DefenseUnit(SoldierType.GUNNER, x=10.0, y=10.0, effective_range=5.0, unit_id="g1")]
        assert calculate_point_damage(target_point, g1) == pytest.approx(20.0)

        # 2 gunners -> exactly 20.0
        g2 = g1 + [DefenseUnit(SoldierType.GUNNER, x=11.0, y=10.0, effective_range=5.0, unit_id="g2")]
        assert calculate_point_damage(target_point, g2) == pytest.approx(20.0)

        # 5 gunners -> exactly 20.0
        g5 = g2 + [
            DefenseUnit(SoldierType.GUNNER, x=10.0, y=11.0, effective_range=5.0, unit_id="g3"),
            DefenseUnit(SoldierType.GUNNER, x=9.0, y=10.0, effective_range=5.0, unit_id="g4"),
            DefenseUnit(SoldierType.GUNNER, x=10.0, y=9.0, effective_range=5.0, unit_id="g5"),
        ]
        assert calculate_point_damage(target_point, g5) == pytest.approx(20.0)

        # 20 gunners -> exactly 20.0
        g20 = [
            DefenseUnit(SoldierType.GUNNER, x=10.0 + 0.1 * i, y=10.0, effective_range=5.0, unit_id=f"g_{i}")
            for i in range(20)
        ]
        assert calculate_point_damage(target_point, g20) == pytest.approx(20.0)

        # 100 gunners -> exactly 20.0
        g100 = [
            DefenseUnit(SoldierType.GUNNER, x=10.0 + 0.01 * i, y=10.0, effective_range=5.0, unit_id=f"g100_{i}")
            for i in range(100)
        ]
        assert calculate_point_damage(target_point, g100) == pytest.approx(20.0)

    def test_mixed_army_with_100_gunners_and_other_units(self):
        """100 Gunners + 3 Snipers (3 * 25.0 = 75.0) + 4 Infantry (4 * 10.0 = 40.0)
        Total D(q) must be exactly 20.0 + 75.0 + 40.0 = 135.0.
        """
        target_point = (0.0, 0.0)
        army = [
            DefenseUnit(SoldierType.GUNNER, x=0.0, y=0.0, effective_range=10.0, unit_id=f"g_{i}")
            for i in range(100)
        ]
        army += [
            DefenseUnit(SoldierType.SNIPER, x=0.0, y=0.0, effective_range=10.0, unit_id=f"s_{i}")
            for i in range(3)
        ]
        army += [
            DefenseUnit(SoldierType.INFANTRY, x=0.0, y=0.0, effective_range=10.0, unit_id=f"inf_{i}")
            for i in range(4)
        ]
        damage = calculate_point_damage(target_point, army)
        assert damage == pytest.approx(135.0)

    def test_boundary_distance_precision(self):
        """Unit at (0, 0) with range 10.0:
        - Point at 10.0 - 1e-5: covered
        - Point at 10.0 exact: covered (dist <= R_ef + 1e-9)
        - Point at 10.0 + 1e-4: NOT covered
        """
        unit = DefenseUnit(SoldierType.SNIPER, x=0.0, y=0.0, effective_range=10.0)

        inside_pt = (10.0 - 1e-5, 0.0)
        assert calculate_point_damage(inside_pt, [unit]) == pytest.approx(25.0)

        exact_pt = (10.0, 0.0)
        assert calculate_point_damage(exact_pt, [unit]) == pytest.approx(25.0)

        outside_pt = (10.0 + 1e-4, 0.0)
        assert calculate_point_damage(outside_pt, [unit]) == pytest.approx(0.0)

    def test_elevation_extreme_scaling(self):
        """Verify R_ef = R_base * (1 + beta * z) with large z and clamped negative z."""
        # Sniper: base_range = 20.0. z = 100.0, beta = 0.05 -> 20.0 * (1 + 5.0) = 120.0
        snip_high = DefenseUnit(SoldierType.SNIPER, x=0, y=0, z=100.0, beta=0.05)
        assert snip_high.effective_range == pytest.approx(120.0)

        # Negative z clamps to 0 -> effective_range == base_range 20.0
        snip_sub = DefenseUnit(SoldierType.SNIPER, x=0, y=0, z=-50.0, beta=0.05)
        assert snip_sub.effective_range == pytest.approx(20.0)


class TestCorridorHazardAdversarial:
    """Stress tests for D_bar(e), P(e), and w(e)."""

    def test_asymmetric_3point_coverage(self):
        """Corridor e with u=(0, 0) to v=(60, 0).
        q_ini = (0, 0), q_mid = (30, 0), q_end = (60, 0).
        Put 1 sniper only at q_ini (D=25), 1 gunner only at q_mid (D=20), nothing at q_end (D=0).
        D_bar(e) = (25 + 20 + 0) / 3 = 15.0.
        Length = 60, speed = 2.0 -> base_time = 30.0s.
        P(e) = 15.0 * 30.0 = 450.0.
        w(e) for alpha=1.0: 30.0 + 1.0 * 450.0 = 480.0.
        """
        gm = MazeGraph()
        gm.add_maze_node("U", 0.0, 0.0)
        gm.add_maze_node("V", 60.0, 0.0)
        corr = gm.add_corridor("U", "V", length=60.0, speed=2.0)

        snip = DefenseUnit(SoldierType.SNIPER, x=0.0, y=0.0, effective_range=5.0)
        gun = DefenseUnit(SoldierType.GUNNER, x=30.0, y=0.0, effective_range=5.0)

        hazard = calculate_corridor_hazard(corr, [snip, gun], alpha=1.0, maze_graph=gm)
        assert hazard.avg_danger == pytest.approx(15.0)
        assert hazard.danger_potential == pytest.approx(450.0)
        assert hazard.reactive_weight == pytest.approx(480.0)

    def test_extreme_alpha_boundary_conditions(self):
        """Test boundary conditions for risk factor alpha:
        - alpha = 0.0 -> w(e) == base_time
        - alpha = 1e6 -> w(e) == base_time + 1e6 * P(e)
        - alpha with zero defenses -> w(e) == base_time for any alpha
        """
        gm = MazeGraph()
        gm.add_maze_node("A", 0.0, 0.0)
        gm.add_maze_node("B", 10.0, 0.0)
        corr = gm.add_corridor("A", "B", length=10.0, speed=1.0)  # base_time = 10.0

        deadly = DefenseUnit(SoldierType.SNIPER, x=5.0, y=0.0, effective_range=10.0)

        # 1. alpha = 0.0 neutralizes risk completely
        h_zero = calculate_corridor_hazard(corr, [deadly], alpha=0.0, maze_graph=gm)
        assert h_zero.reactive_weight == pytest.approx(10.0)
        assert h_zero.danger_potential > 0.0

        # 2. alpha = 1e6 yields massive penalty
        h_huge = calculate_corridor_hazard(corr, [deadly], alpha=1e6, maze_graph=gm)
        expected_w = 10.0 + 1e6 * h_huge.danger_potential
        assert h_huge.reactive_weight == pytest.approx(expected_w)

        # 3. zero defenses: w(e) is invariant to alpha
        h_empty_1 = calculate_corridor_hazard(corr, [], alpha=0.0, maze_graph=gm)
        h_empty_2 = calculate_corridor_hazard(corr, [], alpha=999.0, maze_graph=gm)
        assert h_empty_1.reactive_weight == pytest.approx(10.0)
        assert h_empty_2.reactive_weight == pytest.approx(10.0)


class TestDeterministicDijkstraAdversarial:
    """Stress tests for Dijkstra optimality, tie-breaking, and constraints."""

    def test_five_way_tie_breaking(self):
        """Construct a diamond network with 5 parallel symmetric routes:
        START -> N_A -> END
        START -> N_B -> END
        START -> N_C -> END
        START -> N_D -> END
        START -> N_E -> END
        All paths have total cost 10.0.
        Deterministic tie-breaking MUST pick N_A because 'N_A' < 'N_B' < 'N_C' < 'N_D' < 'N_E'.
        """
        gm = MazeGraph()
        gm.add_maze_node("START", 0, 0)
        gm.add_maze_node("END", 20, 0)

        for name, y in [("N_E", 10), ("N_D", 5), ("N_C", 0), ("N_B", -5), ("N_A", -10)]:
            gm.add_maze_node(name, 10, y)
            gm.add_corridor("START", name, length=5.0, speed=1.0)
            gm.add_corridor(name, "END", length=5.0, speed=1.0)

        res = dijkstra_reactive(gm, "START", "END")
        assert res is not None
        cost, path = res
        assert cost == pytest.approx(10.0)
        assert path == ["START", "N_A", "END"]

    def test_bidirectional_forbidden_edge_blocking(self):
        """Triangle network: START -> P1 -> END (cost 4+4=8) vs START -> END (cost 12).
        Forbidding edge as (P1, START) or (START, P1) must block the corridor equally.
        """
        gm = MazeGraph()
        gm.add_maze_node("START", 0, 0)
        gm.add_maze_node("P1", 5, 0)
        gm.add_maze_node("END", 10, 0)

        gm.add_corridor("START", "P1", length=4.0, speed=1.0)
        gm.add_corridor("P1", "END", length=4.0, speed=1.0)
        gm.add_corridor("START", "END", length=12.0, speed=1.0)

        # Forward tuple
        res1 = dijkstra_reactive(gm, "START", "END", forbidden_edge=("START", "P1"))
        assert res1 is not None
        assert res1[1] == ["START", "END"]
        assert res1[0] == pytest.approx(12.0)

        # Reverse tuple
        res2 = dijkstra_reactive(gm, "START", "END", forbidden_edge=("P1", "START"))
        assert res2 is not None
        assert res2[1] == ["START", "END"]
        assert res2[0] == pytest.approx(12.0)

    def test_disconnected_graph_returns_none_safely(self):
        """Target in a completely disconnected component returns None without infinite loop."""
        gm = MazeGraph()
        gm.add_maze_node("A1", 0, 0)
        gm.add_maze_node("A2", 1, 1)
        gm.add_corridor("A1", "A2", length=1.0, speed=1.0)

        gm.add_maze_node("B1", 10, 10)
        gm.add_maze_node("B2", 11, 11)
        gm.add_corridor("B1", "B2", length=1.0, speed=1.0)

        assert dijkstra_reactive(gm, "A1", "B1") is None

    def test_nonexistent_node_lookup(self):
        """Looking up paths with nodes not in the graph returns None safely."""
        gm = MazeGraph()
        gm.add_maze_node("REAL", 0, 0)
        assert dijkstra_reactive(gm, "REAL", "GHOST") is None
        assert dijkstra_reactive(gm, "GHOST", "REAL") is None


class TestAntiBacktrackingAdversarial:
    """Stress tests for Anti-Backtracking edge cases, dead ends, and branches."""

    def test_anti_backtrack_diverts_to_longer_safe_path(self):
        """Convoy moves IN -> M1.
        At M1, returning to IN has lower unconstrained cost than going forward to OUT.
        Convoy MUST divert to the forward path to OUT.
        """
        scenario_srv = ScenarioService()
        gm = MazeGraph()

        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("M1", 10, 0)
        gm.add_maze_node("M2", 20, 0)
        gm.add_maze_node("CHEAP_BACK", 0, 10)
        gm.add_maze_node("OUT", 30, 0, is_exit=True)

        # Corridors:
        # IN -> M1 (cost 4)
        gm.add_corridor("IN", "M1", length=4.0, speed=1.0)
        # IN -> CHEAP_BACK -> OUT (cost 1 + 1 = 2)
        gm.add_corridor("IN", "CHEAP_BACK", length=1.0, speed=1.0)
        gm.add_corridor("CHEAP_BACK", "OUT", length=1.0, speed=1.0)
        # M1 -> M2 -> OUT (cost 8 + 8 = 16)
        gm.add_corridor("M1", "M2", length=8.0, speed=1.0)
        gm.add_corridor("M2", "OUT", length=8.0, speed=1.0)

        scenario_srv.maze_graph = gm
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        sim_srv.current_node = "M1"
        sim_srv.previous_node = "IN"
        sim_srv.visited_nodes = ["IN", "M1"]

        # Backtrack route through IN: cost = 4 + 1 + 1 = 6.0
        # Forward route through M2: cost = 8 + 8 = 16.0
        # Unconstrained Dijkstra would choose IN (cost 6).
        decision = sim_srv.evaluate_step_decision(alpha=1.0)

        assert decision["type"] == "ANTI_BACKTRACK_AVOIDED"
        assert decision["backtrack_prevented"] is True
        assert decision["discarded_node"] == "IN"
        assert decision["chosen_next_node"] == "M2"
        assert decision["alternative_taken"] is True
        assert decision["projected_path"] == ["M1", "M2", "OUT"]

    def test_single_leaf_dead_end_allows_backtrack(self):
        """Convoy enters a dead-end leaf node DEAD.
        No other neighbor exists. Backtrack MUST be permitted as last resort.
        """
        scenario_srv = ScenarioService()
        gm = MazeGraph()

        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("FORK", 10, 0)
        gm.add_maze_node("DEAD", 10, 10)
        gm.add_maze_node("OUT", 20, 0, is_exit=True)

        gm.add_corridor("IN", "FORK", length=5.0, speed=1.0)
        gm.add_corridor("FORK", "DEAD", length=3.0, speed=1.0)
        gm.add_corridor("FORK", "OUT", length=10.0, speed=1.0)

        scenario_srv.maze_graph = gm
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        sim_srv.current_node = "DEAD"
        sim_srv.previous_node = "FORK"
        sim_srv.visited_nodes = ["IN", "FORK", "DEAD"]

        decision = sim_srv.evaluate_step_decision(alpha=1.0)
        assert decision["type"] == "FORCED_DEAD_END_BACKTRACK"
        assert decision["chosen_next_node"] == "FORK"
        assert decision["backtrack_prevented"] is False

    def test_multi_node_dead_end_subnetwork_allows_backtrack(self):
        """Convoy is at D1, arrived from MAIN.
        D1 connects to D2 (another leaf).
        Neither D1 nor D2 has any path to OUT without going back to MAIN.
        Therefore, D2 is NOT a viable path to OUT!
        Backtracking to MAIN MUST be permitted as the only route to OUT.
        """
        scenario_srv = ScenarioService()
        gm = MazeGraph()

        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("MAIN", 10, 0)
        gm.add_maze_node("D1", 10, 10)
        gm.add_maze_node("D2", 10, 20)  # Leaf connected only to D1
        gm.add_maze_node("OUT", 20, 0, is_exit=True)

        gm.add_corridor("IN", "MAIN", length=5.0, speed=1.0)
        gm.add_corridor("MAIN", "D1", length=3.0, speed=1.0)
        gm.add_corridor("D1", "D2", length=2.0, speed=1.0)
        gm.add_corridor("MAIN", "OUT", length=10.0, speed=1.0)

        scenario_srv.maze_graph = gm
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        sim_srv.current_node = "D1"
        sim_srv.previous_node = "MAIN"
        sim_srv.visited_nodes = ["IN", "MAIN", "D1"]

        decision = sim_srv.evaluate_step_decision(alpha=1.0)
        # D2 cannot reach OUT, so alternative_paths is empty!
        # Forced backtrack to MAIN!
        assert decision["type"] == "FORCED_DEAD_END_BACKTRACK"
        assert decision["chosen_next_node"] == "MAIN"
        assert decision["backtrack_prevented"] is False

    def test_full_escape_sequence_with_dead_end_recovery(self):
        """Convoy starts at IN, accidentally visits DEAD, backtracks to FORK, and escapes at OUT."""
        scenario_srv = ScenarioService()
        gm = MazeGraph()

        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("FORK", 10, 0)
        gm.add_maze_node("DEAD", 10, 10)
        gm.add_maze_node("OUT", 20, 0, is_exit=True)

        gm.add_corridor("IN", "FORK", length=5.0, speed=1.0)
        gm.add_corridor("FORK", "DEAD", length=3.0, speed=1.0)
        gm.add_corridor("FORK", "OUT", length=5.0, speed=1.0)

        scenario_srv.maze_graph = gm
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        # Step 1: IN -> FORK
        s1 = sim_srv.step()
        assert s1["current_node"] == "FORK"
        assert s1["previous_node"] == "IN"

        # Force next step into DEAD to simulate exploration into a dead end
        sim_srv.current_node = "DEAD"
        sim_srv.previous_node = "FORK"
        sim_srv.visited_nodes.append("DEAD")

        # Step 2: From DEAD, must backtrack to FORK
        s2 = sim_srv.step()
        assert s2["current_node"] == "FORK"
        assert s2["previous_node"] == "DEAD"
        assert s2["is_finished"] is False

        # Step 3: From FORK (prev=DEAD), must continue to OUT (not back to DEAD)
        s3 = sim_srv.step()
        assert s3["current_node"] == "OUT"
        assert s3["is_finished"] is True
        assert s3["escaped"] is True
