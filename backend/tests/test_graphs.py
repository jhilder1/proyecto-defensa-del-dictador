"""Unit tests for Stage 1: Custom Data Structures and Domain Models."""

import pytest
from app.core.dsu import DisjointSetUnion
from app.core.priority_queue import PriorityQueue
from app.core.graph import BaseGraph
from app.core.elevated_graph import ElevatedGraph
from app.core.maze_graph import MazeGraph
from app.domain.node import ElevatedNode, ElevatedNodeType, MazeNode
from app.domain.edge import ElevatedEdge, MazeEdge
from app.domain.soldier import Soldier, SoldierType
from app.domain.enemy import EnemyMachine, EnemyType
from app.domain.transport import TransportMission, TransportType
from app.domain.simulation_state import SimulationState


class TestDisjointSetUnion:
    """Verifies DSU with path compression and union by rank."""

    def test_singleton_and_find(self):
        dsu = DisjointSetUnion(["A", "B", "C"])
        assert dsu.find("A") == "A"
        assert dsu.find("B") == "B"
        assert not dsu.connected("A", "B")

    def test_union_by_rank_and_connectivity(self):
        dsu = DisjointSetUnion(["A", "B", "C", "D"])
        assert dsu.union("A", "B") is True
        assert dsu.connected("A", "B") is True
        assert dsu.connected("A", "C") is False

        assert dsu.union("C", "D") is True
        assert dsu.connected("C", "D") is True

        # Redundant union returns False
        assert dsu.union("A", "B") is False

        # Merge components
        assert dsu.union("B", "C") is True
        assert dsu.connected("A", "D") is True

        components = dsu.get_components()
        assert len(components) == 1
        root = list(components.keys())[0]
        assert set(components[root]) == {"A", "B", "C", "D"}


class TestPriorityQueue:
    """Verifies custom Min-Heap implementation from scratch."""

    def test_push_and_pop_ordering(self):
        pq = PriorityQueue()
        assert pq.is_empty()
        assert len(pq) == 0

        items = [15, 3, 8, 1, 20, 2]
        for item in items:
            pq.push(item)

        assert len(pq) == len(items)
        assert pq.peek() == 1

        popped = []
        while not pq.is_empty():
            popped.append(pq.pop())

        assert popped == [1, 2, 3, 8, 15, 20]
        assert pq.is_empty()

    def test_tuple_with_tie_breaker(self):
        """Ensures consistent deterministic tie-breaking with tuples (cost, id, value)."""
        pq = PriorityQueue()
        pq.push((10.0, "node_C", "payload_C"))
        pq.push((5.0, "node_B", "payload_B"))
        pq.push((10.0, "node_A", "payload_A"))
        pq.push((2.0, "node_Z", "payload_Z"))

        res1 = pq.pop()
        assert res1 == (2.0, "node_Z", "payload_Z")

        res2 = pq.pop()
        assert res2 == (5.0, "node_B", "payload_B")

        # Tie at cost 10.0 should break lexicographically: node_A before node_C
        res3 = pq.pop()
        assert res3 == (10.0, "node_A", "payload_A")

        res4 = pq.pop()
        assert res4 == (10.0, "node_C", "payload_C")

    def test_empty_exceptions(self):
        pq = PriorityQueue()
        with pytest.raises(IndexError):
            pq.pop()
        with pytest.raises(IndexError):
            pq.peek()


class TestBaseGraph:
    """Verifies generic adjacency list base graph."""

    def test_undirected_graph(self):
        g = BaseGraph(directed=False)
        g.add_node("A", label="Alpha")
        g.add_node("B", label="Beta")
        g.add_edge("A", "B", weight=4.5)

        assert g.node_count == 2
        assert g.edge_count == 1
        assert g.has_edge("A", "B")
        assert g.has_edge("B", "A")
        assert g.neighbors("A") == ["B"]
        assert g.neighbors("B") == ["A"]

    def test_connected_components_bfs(self):
        g = BaseGraph(directed=False)
        g.add_edge("1", "2")
        g.add_edge("2", "3")
        g.add_edge("4", "5")
        g.add_node("6")  # Isolated

        comps = g.get_connected_components()
        assert len(comps) == 3
        comp_sets = [frozenset(c) for c in comps]
        assert frozenset({"1", "2", "3"}) in comp_sets
        assert frozenset({"4", "5"}) in comp_sets
        assert frozenset({"6"}) in comp_sets


class TestElevatedGraphAndBridges:
    """Verifies G_E structure, node types and dynamic bridge mechanics."""

    def test_nodes_and_edges_creation(self):
        ge = ElevatedGraph()
        base = ge.add_elevated_node("Base", x=0, y=0, z=5.0, node_type=ElevatedNodeType.BASE)
        cand = ge.add_elevated_node("T1", x=10, y=0, z=12.0, node_type=ElevatedNodeType.CANDIDATO)
        heli = ge.add_elevated_node("H1", x=0, y=10, z=2.0, node_type=ElevatedNodeType.HELIPUERTO)

        assert ge.get_base_node().id == "Base"
        assert ge.get_heliport_node().id == "H1"
        assert len(ge.get_candidate_nodes()) == 1

        bridge = ge.add_elevated_edge(
            "Base", "T1",
            foot_time=15.0,
            moto_time=5.0,
            is_bridge=True,
            max_resistance=2,
            reconstruction_duration=20.0,
        )

        assert bridge.is_bridge is True
        assert bridge.current_resistance == 2
        assert bridge.is_passable() is True

    def test_bridge_collapse_and_reconstruction(self):
        ge = ElevatedGraph()
        ge.add_elevated_node("A", 0, 0)
        ge.add_elevated_node("B", 10, 0)
        bridge = ge.add_elevated_edge(
            "A", "B",
            foot_time=10.0,
            moto_time=3.0,
            is_bridge=True,
            max_resistance=2,
            reconstruction_duration=20.0,
        )

        # Motorcycle cross 1: resistance drops to 1
        collapsed = bridge.on_motorcycle_cross_complete()
        assert collapsed is False
        assert bridge.current_resistance == 1
        assert bridge.is_passable() is True

        # Motorcycle cross 2: resistance hits 0, bridge collapses
        collapsed = bridge.on_motorcycle_cross_complete()
        assert collapsed is True
        assert bridge.current_resistance == 0
        assert bridge.is_destroyed is True
        assert bridge.is_passable() is False
        assert bridge.reconstruction_timer == 20.0

        # Advance timer 10 seconds -> still destroyed
        rebuilt = ge.update_reconstruction_timers(10.0)
        assert len(rebuilt) == 0
        assert bridge.is_destroyed is True
        assert bridge.reconstruction_timer == 10.0

        # Advance another 10 seconds -> rebuilt
        rebuilt = ge.update_reconstruction_timers(10.0)
        assert len(rebuilt) == 1
        assert bridge.is_destroyed is False
        assert bridge.current_resistance == 2
        assert bridge.is_passable() is True


class TestMazeGraph:
    """Verifies G_M structure, corridors and key evaluation points."""

    def test_corridors_and_points(self):
        gm = MazeGraph()
        n_in = gm.add_maze_node("IN", x=0, y=0, is_entry=True)
        n_mid = gm.add_maze_node("M1", x=10, y=0)
        n_out = gm.add_maze_node("OUT", x=10, y=20, is_exit=True)

        assert len(gm.get_entry_nodes()) == 1
        assert len(gm.get_exit_nodes()) == 1

        corridor1 = gm.add_corridor("IN", "M1", length=10.0, speed=2.0)
        assert corridor1.base_time == 5.0  # 10.0 / 2.0

        # Test key points (q_ini, q_mid, q_end)
        pts = gm.get_corridor_points("IN", "M1")
        assert pts is not None
        q_ini, q_mid, q_end = pts
        assert q_ini == (0.0, 0.0)
        assert q_mid == (5.0, 0.0)
        assert q_end == (10.0, 0.0)


class TestSoldiersAndCombatDomain:
    """Verifies soldiers, effective range formula, and cooldowns."""

    def test_soldier_types_and_effective_range(self):
        infantry = Soldier(SoldierType.INFANTRY)
        sniper = Soldier(SoldierType.SNIPER)
        gunner = Soldier(SoldierType.GUNNER)

        assert infantry.cost == 100
        assert sniper.cost == 300
        assert gunner.cost == 500

        # Effective range: R_ef = R_base * (1 + beta * z)
        # For sniper at z = 10, beta = 0.1: R_ef = 20 * (1 + 0.1 * 10) = 40.0
        ref_sniper = sniper.get_effective_range(z_height=10.0, beta=0.1)
        assert pytest.approx(ref_sniper, 0.001) == 40.0

        # For gunner at z = 5, beta = 0.1: R_ef = 15 * (1 + 0.1 * 5) = 22.5
        ref_gunner = gunner.get_effective_range(z_height=5.0, beta=0.1)
        assert pytest.approx(ref_gunner, 0.001) == 22.5

    def test_attack_and_cooldown(self):
        sniper = Soldier(SoldierType.SNIPER)  # fire_rate = 0.5 attacks/s -> 2.0s cooldown
        assert sniper.can_attack() is True

        sniper.trigger_attack()
        assert sniper.can_attack() is False
        assert pytest.approx(sniper.cooldown, 0.001) == 2.0

        sniper.update_cooldown(1.0)
        assert sniper.can_attack() is False
        assert pytest.approx(sniper.cooldown, 0.001) == 1.0

        sniper.update_cooldown(1.0)
        assert sniper.can_attack() is True


class TestEnemiesAndSimulationState:
    """Verifies enemies and simulation resource limits."""

    def test_enemy_machines_damage_and_bounty(self):
        tank = EnemyMachine(EnemyType.TANK)
        truck = EnemyMachine(EnemyType.TRUCK)
        robot = EnemyMachine(EnemyType.ROBOT)

        assert tank.max_hp == 200.0
        assert tank.reward == 150
        assert truck.max_hp == 100.0
        assert truck.reward == 100
        assert robot.max_hp == 50.0
        assert robot.reward == 50

        dmg = tank.take_damage(60.0)
        assert dmg == 60.0
        assert tank.current_hp == 140.0
        assert tank.is_alive is True

        dmg_fatal = tank.take_damage(200.0)
        assert dmg_fatal == 140.0
        assert tank.current_hp == 0.0
        assert tank.is_alive is False

    def test_tower_occupancy_limit_of_three(self):
        node = ElevatedNode("T1", 0, 0, node_type=ElevatedNodeType.CANDIDATO)
        assert node.available_slots == 3
        assert node.can_receive_soldier() is True

        node.stationed_soldiers.append("soldier_1")
        assert node.available_slots == 2

        node.reserved_slots = 2
        assert node.available_slots == 0
        assert node.can_receive_soldier() is False

    def test_simulation_budget_and_rewards(self):
        state = SimulationState(initial_budget=1000.0)
        assert state.budget_available == 1000.0

        # Purchase unit for 300
        success = state.spend_budget(300.0)
        assert success is True
        assert state.budget_available == 700.0

        # Reserve 150 for transport
        assert state.reserve_budget(150.0) is True
        assert state.budget_available == 550.0
        assert state.budget_reserved == 150.0

        # Add enemy reward
        state.add_reward(150.0)
        assert state.budget_available == 700.0

