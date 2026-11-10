"""Unit tests for Kruskal MST and tree distance calculations on G_E."""

import pytest
from app.core.elevated_graph import ElevatedGraph
from app.domain.node import ElevatedNodeType
from app.core.algorithms import kruskal_mst


class TestKruskalMST:
    def test_simple_mst_foot_time(self):
        """Tests standard MST calculation on a small elevated graph."""
        ge = ElevatedGraph()
        ge.add_elevated_node("Base", 0, 0, z=0, node_type=ElevatedNodeType.BASE)
        ge.add_elevated_node("N1", 10, 0, z=5, node_type=ElevatedNodeType.TRANSITO)
        ge.add_elevated_node("N2", 10, 10, z=5, node_type=ElevatedNodeType.TRANSITO)
        ge.add_elevated_node("T1", 0, 10, z=10, node_type=ElevatedNodeType.CANDIDATO)

        # Triangle / square with different foot times
        ge.add_elevated_edge("Base", "N1", foot_time=10.0, moto_time=3.0)
        ge.add_elevated_edge("N1", "N2", foot_time=10.0, moto_time=3.0)
        ge.add_elevated_edge("N2", "T1", foot_time=10.0, moto_time=3.0)
        ge.add_elevated_edge("T1", "Base", foot_time=30.0, moto_time=10.0)  # Expensive cycle edge
        ge.add_elevated_edge("Base", "N2", foot_time=25.0, moto_time=8.0)  # Diagonal

        result = kruskal_mst(ge, base_node_id="Base")
        mst_edges = result["mst_edges"]

        # 4 nodes -> 3 edges in MST
        assert len(mst_edges) == 3
        assert result["total_cost"] == 30.0  # 10 + 10 + 10

        # Tree distances along T_E
        tree_dist = result["tree_distances"]
        assert tree_dist["Base"] == 0.0
        assert tree_dist["N1"] == 10.0
        assert tree_dist["N2"] == 20.0
        assert tree_dist["T1"] == 30.0

    def test_disconnected_component_is_excluded(self):
        """Nodes disconnected from the Base must NOT be included in MST."""
        ge = ElevatedGraph()
        ge.add_elevated_node("Base", 0, 0, node_type=ElevatedNodeType.BASE)
        ge.add_elevated_node("N1", 5, 0, node_type=ElevatedNodeType.TRANSITO)
        ge.add_elevated_edge("Base", "N1", foot_time=5.0, moto_time=2.0)

        # Disconnected island
        ge.add_elevated_node("Island1", 100, 100, node_type=ElevatedNodeType.CANDIDATO)
        ge.add_elevated_node("Island2", 110, 100, node_type=ElevatedNodeType.TRANSITO)
        ge.add_elevated_edge("Island1", "Island2", foot_time=1.0, moto_time=0.5)

        result = kruskal_mst(ge, base_node_id="Base")

        assert result["base_component"] == ["Base", "N1"]
        assert len(result["mst_edges"]) == 1
        assert "Island1" not in result["tree_distances"]
        assert "Island2" not in result["tree_distances"]

    def test_deterministic_lexicographical_tie_breaking(self):
        """When two edges have equal weights, tie-breaker must be deterministic."""
        ge = ElevatedGraph()
        ge.add_elevated_node("Base", 0, 0, node_type=ElevatedNodeType.BASE)
        ge.add_elevated_node("A", 1, 0, node_type=ElevatedNodeType.TRANSITO)
        ge.add_elevated_node("B", 0, 1, node_type=ElevatedNodeType.TRANSITO)

        # Equal weights 10.0 for Base-A, Base-B, and A-B
        ge.add_elevated_edge("Base", "A", foot_time=10.0, moto_time=2.0)
        ge.add_elevated_edge("Base", "B", foot_time=10.0, moto_time=2.0)
        ge.add_elevated_edge("A", "B", foot_time=10.0, moto_time=2.0)

        result = kruskal_mst(ge, base_node_id="Base")
        assert len(result["mst_edges"]) == 2
        # Edges should be picked deterministically without crashing or cycles
        assert result["total_cost"] == 20.0

