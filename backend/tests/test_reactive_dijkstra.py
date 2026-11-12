"""Unit tests for Stage 3 Deterministic Reactive Dijkstra (Requirement R4, F7).

Verifies:
- Shortest path calculation with custom PriorityQueue min-heap
- Deterministic lexicographical tie-breaking for equal cost paths
- Forbidden edge avoidance
- Forbidden first step avoidance
- Unreachable / disconnected target returning None
- Identity path (start_node == target_node) returning 0 cost
"""

import pytest
from app.core.maze_graph import MazeGraph
from app.core.algorithms import dijkstra_reactive


class TestReactiveDijkstra:
    def test_simple_dijkstra_path(self):
        """Validates basic shortest path calculation along a line."""
        gm = MazeGraph()
        gm.add_maze_node("A", 0, 0)
        gm.add_maze_node("B", 10, 0)
        gm.add_maze_node("C", 20, 0)

        gm.add_corridor("A", "B", length=10.0, speed=1.0)  # base_time = 10.0
        gm.add_corridor("B", "C", length=10.0, speed=2.0)  # base_time = 5.0

        res = dijkstra_reactive(gm, "A", "C")
        assert res is not None
        cost, path = res
        assert path == ["A", "B", "C"]
        assert cost == pytest.approx(15.0)

    def test_deterministic_lexicographical_tie_breaking(self):
        """Two routes A -> B -> D and A -> C -> D have IDENTICAL reactive cost (15.0).
        Because 'B' < 'C', the deterministic tie-breaking must pick route through B.
        """
        gm = MazeGraph()
        gm.add_maze_node("A", 0, 0)
        gm.add_maze_node("B", 10, -5)
        gm.add_maze_node("C", 10, 5)
        gm.add_maze_node("D", 20, 0)

        # Route through B: 8 + 7 = 15.0
        gm.add_corridor("A", "B", length=8.0, speed=1.0)
        gm.add_corridor("B", "D", length=7.0, speed=1.0)

        # Route through C: 8 + 7 = 15.0
        gm.add_corridor("A", "C", length=8.0, speed=1.0)
        gm.add_corridor("C", "D", length=7.0, speed=1.0)

        res = dijkstra_reactive(gm, "A", "D")
        assert res is not None
        cost, path = res
        assert cost == pytest.approx(15.0)
        assert path == ["A", "B", "D"], f"Expected tie-break to choose 'B' < 'C', got {path}"

    def test_forbidden_edge_routing(self):
        """Triangle network:
        A - B: weight 4.0
        B - C: weight 4.0 (A -> B -> C cost = 8.0)
        A - C: weight 12.0
        Without forbidden edge, optimal is A -> B -> C (cost 8).
        With forbidden_edge=('A', 'B'), optimal diverts to A -> C (cost 12).
        """
        gm = MazeGraph()
        gm.add_maze_node("A", 0, 0)
        gm.add_maze_node("B", 5, 0)
        gm.add_maze_node("C", 10, 0)

        gm.add_corridor("A", "B", length=4.0, speed=1.0)
        gm.add_corridor("B", "C", length=4.0, speed=1.0)
        gm.add_corridor("A", "C", length=12.0, speed=1.0)

        # Unconstrained
        unconstrained = dijkstra_reactive(gm, "A", "C")
        assert unconstrained is not None
        assert unconstrained[1] == ["A", "B", "C"]
        assert unconstrained[0] == pytest.approx(8.0)

        # Forbid edge (A, B)
        forbidden = dijkstra_reactive(gm, "A", "C", forbidden_edge=("A", "B"))
        assert forbidden is not None
        assert forbidden[1] == ["A", "C"]
        assert forbidden[0] == pytest.approx(12.0)

        # Forbid edge passed in reverse (B, A)
        forbidden_rev = dijkstra_reactive(gm, "A", "C", forbidden_edge=("B", "A"))
        assert forbidden_rev is not None
        assert forbidden_rev[1] == ["A", "C"]
        assert forbidden_rev[0] == pytest.approx(12.0)

    def test_forbidden_first_step(self):
        """Forbidding B as the first step from A forces taking alternative path."""
        gm = MazeGraph()
        gm.add_maze_node("A", 0, 0)
        gm.add_maze_node("B", 5, 0)
        gm.add_maze_node("C", 10, 0)

        gm.add_corridor("A", "B", length=3.0, speed=1.0)
        gm.add_corridor("B", "C", length=3.0, speed=1.0)
        gm.add_corridor("A", "C", length=10.0, speed=1.0)

        res = dijkstra_reactive(gm, "A", "C", forbidden_first_step="B")
        assert res is not None
        assert res[1] == ["A", "C"]
        assert res[0] == pytest.approx(10.0)

    def test_unreachable_target_returns_none(self):
        """Disconnected target node returns None."""
        gm = MazeGraph()
        gm.add_maze_node("Island1", 0, 0)
        gm.add_maze_node("Island2", 100, 100)

        res = dijkstra_reactive(gm, "Island1", "Island2")
        assert res is None

    def test_start_equals_target(self):
        """Start node equal to target returns (0.0, [start_node])."""
        gm = MazeGraph()
        gm.add_maze_node("IN", 0, 0)

        res = dijkstra_reactive(gm, "IN", "IN")
        assert res is not None
        cost, path = res
        assert cost == 0.0
        assert path == ["IN"]

    def test_reactive_weight_updates_influence_path_choice(self):
        """Path choice dynamically changes when corridor reactive weight increases due to hazard."""
        gm = MazeGraph()
        gm.add_maze_node("START", 0, 0)
        gm.add_maze_node("MID1", 10, -5)
        gm.add_maze_node("MID2", 10, 5)
        gm.add_maze_node("EXIT", 20, 0)

        # Route 1: START -> MID1 -> EXIT (length 10 each, speed 1 -> base_time 20)
        c1 = gm.add_corridor("START", "MID1", length=10.0, speed=1.0)
        c2 = gm.add_corridor("MID1", "EXIT", length=10.0, speed=1.0)

        # Route 2: START -> MID2 -> EXIT (length 12 each, speed 1 -> base_time 24)
        c3 = gm.add_corridor("START", "MID2", length=12.0, speed=1.0)
        c4 = gm.add_corridor("MID2", "EXIT", length=12.0, speed=1.0)

        # Initially, Route 1 (cost 20) is preferred over Route 2 (cost 24)
        res_initial = dijkstra_reactive(gm, "START", "EXIT")
        assert res_initial is not None
        assert res_initial[1] == ["START", "MID1", "EXIT"]

        # Now, corridor c1 becomes heavily hazardous
        c1.update_danger(avg_danger=10.0, alpha=1.0)  # reactive_weight = 10 + 1.0 * (10 * 10) = 110!
        gm.adj["START"]["MID1"]["reactive_weight"] = c1.reactive_weight

        # Now, Route 2 (cost 24) is much safer and must be chosen!
        res_after = dijkstra_reactive(gm, "START", "EXIT")
        assert res_after is not None
        assert res_after[1] == ["START", "MID2", "EXIT"]
        assert res_after[0] == pytest.approx(24.0)
