"""Unit tests for greedy tower selection formula S(p) and coverage."""

import pytest
from app.core.elevated_graph import ElevatedGraph
from app.core.maze_graph import MazeGraph
from app.domain.node import ElevatedNodeType
from app.core.algorithms import kruskal_mst, select_towers_greedy


class TestTowerSelectionGreedy:
    def test_greedy_selection_ranking(self):
        """Tests that candidate with higher S(p) is selected before a lower one."""
        ge = ElevatedGraph()
        gm = MazeGraph()

        # Elevated Graph: Base at (0, 0), Cand1 at (10, 0), Cand2 at (30, 0)
        ge.add_elevated_node("Base", 0, 0, node_type=ElevatedNodeType.BASE)
        ge.add_elevated_node("T1", 10, 0, node_type=ElevatedNodeType.CANDIDATO, surveillance_radius=15.0)
        ge.add_elevated_node("T2", 30, 0, node_type=ElevatedNodeType.CANDIDATO, surveillance_radius=15.0)

        ge.add_elevated_edge("Base", "T1", foot_time=10.0, moto_time=3.0)
        ge.add_elevated_edge("T1", "T2", foot_time=20.0, moto_time=6.0)

        # Maze Graph:
        # Corridor 1: (5, 5) to (15, 5), length 10. Midpoint = (10, 5).
        # Distance from T1(10, 0) to (10, 5) is 5.0 <= 15 (Watched by T1)
        # Distance from T2(30, 0) to (10, 5) is sqrt(20^2 + 5^2) = 20.6 > 15 (NOT watched by T2)
        gm.add_maze_node("M1", 5, 5)
        gm.add_maze_node("M2", 15, 5)
        gm.add_corridor("M1", "M2", length=10.0, speed=1.0)

        # Corridor 2: (25, 5) to (35, 5), length 10. Midpoint = (30, 5).
        # Distance from T2(30, 0) to (30, 5) is 5.0 <= 15 (Watched by T2)
        # Distance from T1(10, 0) to (30, 5) is 20.6 > 15 (NOT watched by T1)
        gm.add_maze_node("M3", 25, 5)
        gm.add_maze_node("M4", 35, 5)
        gm.add_corridor("M3", "M4", length=10.0, speed=1.0)

        mst_res = kruskal_mst(ge, base_node_id="Base")
        tree_dist = mst_res["tree_distances"]
        assert tree_dist["T1"] == 10.0
        assert tree_dist["T2"] == 30.0

        # With D_0 = 50:
        # S(T1) = 10 / (1 + 10 / 50) = 10 / 1.2 = 8.333
        # S(T2) = 10 / (1 + 30 / 50) = 10 / 1.6 = 6.25
        # T1 must be selected first!
        res_k1 = select_towers_greedy(ge, gm, tree_dist, k_towers=1, d0_normalization=50.0)
        assert res_k1["towers_selected_count"] == 1
        assert res_k1["selected_towers"][0]["tower_id"] == "T1"
        assert pytest.approx(res_k1["selected_towers"][0]["score"], 0.01) == 8.333

        # With K = 2: Both T1 and T2 get selected
        res_k2 = select_towers_greedy(ge, gm, tree_dist, k_towers=2, d0_normalization=50.0)
        assert res_k2["towers_selected_count"] == 2
        assert [t["tower_id"] for t in res_k2["selected_towers"]] == ["T1", "T2"]
        assert res_k2["coverage_percentage"] == 100.0

    def test_stop_criterion_when_no_new_coverage(self):
        """If 5 towers are requested but only 1 candidate can cover the only corridor, stop after 1."""
        ge = ElevatedGraph()
        gm = MazeGraph()

        ge.add_elevated_node("Base", 0, 0, node_type=ElevatedNodeType.BASE)
        ge.add_elevated_node("T1", 10, 0, node_type=ElevatedNodeType.CANDIDATO, surveillance_radius=10.0)
        ge.add_elevated_node("T2", 100, 100, node_type=ElevatedNodeType.CANDIDATO, surveillance_radius=10.0)
        ge.add_elevated_edge("Base", "T1", foot_time=10.0, moto_time=3.0)
        ge.add_elevated_edge("T1", "T2", foot_time=20.0, moto_time=5.0)

        # Single corridor only near T1
        gm.add_maze_node("M1", 8, 0)
        gm.add_maze_node("M2", 12, 0)
        gm.add_corridor("M1", "M2", length=4.0, speed=1.0)

        mst_res = kruskal_mst(ge, base_node_id="Base")
        res = select_towers_greedy(ge, gm, mst_res["tree_distances"], k_towers=5, d0_normalization=50.0)

        # Only T1 is selected because T2 covers 0 unwatched corridors (C(p) = 0)
        assert res["towers_selected_count"] == 1
        assert res["selected_towers"][0]["tower_id"] == "T1"

