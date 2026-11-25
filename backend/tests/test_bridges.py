"""Unit tests for Stage 4: elevated Dijkstra, ground dispatches, bridge wear, collapse, rerouting & reconstruction."""

import pytest
from app.core.algorithms import dijkstra_elevated
from app.domain.node import ElevatedNodeType
from app.domain.soldier import SoldierType
from app.domain.transport import TransportType
from app.services.scenario_service import ScenarioService
from app.services.logistics_service import LogisticsService


def build_bridge_scenario() -> ScenarioService:
    """Creates an isolated ScenarioService with elevated bridges and two paths."""
    srv = ScenarioService()
    srv.load_from_dict({
        "scenario_name": "Bridge Test",
        "config": {"initial_budget": 2000.0},
        "elevated_network": {
            "nodes": [
                {"id": "Base", "x": 0.0, "y": 0.0, "z": 0.0, "type": "Base"},
                {"id": "N1", "x": 10.0, "y": 0.0, "z": 2.0, "type": "Tránsito"},
                {"id": "N2", "x": 10.0, "y": 10.0, "z": 2.0, "type": "Tránsito"},
                {"id": "T1", "x": 20.0, "y": 0.0, "z": 5.0, "type": "Candidato", "surveillance_radius": 50.0},
            ],
            "edges": [
                {"u": "Base", "v": "N1", "foot_time": 4.0, "moto_time": 2.0, "is_bridge": False},
                {
                    "u": "N1",
                    "v": "T1",
                    "foot_time": 6.0,
                    "moto_time": 3.0,
                    "is_bridge": True,
                    "max_resistance": 1,
                    "reconstruction_duration": 10.0,
                },
                {"u": "Base", "v": "N2", "foot_time": 10.0, "moto_time": 5.0, "is_bridge": False},
                {"u": "N2", "v": "T1", "foot_time": 10.0, "moto_time": 5.0, "is_bridge": False},
            ],
        },
        "maze_network": {
            "nodes": [
                {"id": "IN", "x": 0.0, "y": 20.0, "is_entry": True},
                {"id": "OUT", "x": 30.0, "y": 20.0, "is_exit": True},
            ],
            "corridors": [{"u": "IN", "v": "OUT", "length": 30.0, "speed": 1.0}],
        },
        "convoy": [{"type": "Robot", "hp": 50.0, "reward": 50}],
    })
    srv.elevated_graph.get_elevated_node("T1").is_active_tower = True
    return srv


class TestElevatedDijkstraAndBridges:
    def test_dijkstra_elevated_foot_vs_moto_and_tie_break(self):
        srv = build_bridge_scenario()
        ge = srv.elevated_graph

        foot_cost, foot_path = dijkstra_elevated(ge, "Base", "T1", TransportType.FOOT)
        assert foot_path == ["Base", "N1", "T1"]
        assert foot_cost == pytest.approx(10.0)

        moto_cost, moto_path = dijkstra_elevated(ge, "Base", "T1", TransportType.MOTORCYCLE)
        assert moto_path == ["Base", "N1", "T1"]
        assert moto_cost == pytest.approx(5.0)

        # Equal weight path tie-breaker test
        ge.add_elevated_node("A", 1, 1, node_type=ElevatedNodeType.TRANSITO)
        ge.add_elevated_node("B", 1, -1, node_type=ElevatedNodeType.TRANSITO)
        ge.add_elevated_node("Z", 2, 0, node_type=ElevatedNodeType.TRANSITO)
        ge.add_elevated_edge("Base", "B", foot_time=5.0, moto_time=2.0)
        ge.add_elevated_edge("B", "Z", foot_time=5.0, moto_time=2.0)
        ge.add_elevated_edge("Base", "A", foot_time=5.0, moto_time=2.0)
        ge.add_elevated_edge("A", "Z", foot_time=5.0, moto_time=2.0)

        _, tie_path = dijkstra_elevated(ge, "Base", "Z", TransportType.FOOT)
        assert tie_path == ["Base", "A", "Z"]

    def test_foot_dispatch_capacity_and_no_bridge_wear(self):
        srv = build_bridge_scenario()
        log_srv = LogisticsService(srv)

        buy_res = log_srv.buy_soldier(SoldierType.INFANTRY, quantity=2)
        s_ids = [s["id"] for s in buy_res["purchased"]]

        # Foot transport allows at most 1 soldier
        with pytest.raises(ValueError, match="máximo 1"):
            log_srv.dispatch_ground(TransportType.FOOT, s_ids, "T1")

        mission = log_srv.dispatch_ground(TransportType.FOOT, [s_ids[0]], "T1")
        assert mission["path"] == ["Base", "N1", "T1"]

        # Advance 10s (4s + 6s): arrives at T1, bridge resistance unchanged
        log_srv.advance_missions(10.0)
        bridge = srv.elevated_graph.get_elevated_edge("N1", "T1")
        assert bridge.current_resistance == 1
        assert bridge.is_destroyed is False
        assert s_ids[0] in srv.elevated_graph.get_elevated_node("T1").stationed_soldiers

    def test_motorcycle_bridge_wear_collapse_and_in_progress_finish(self):
        srv = build_bridge_scenario()
        log_srv = LogisticsService(srv)

        buy_res = log_srv.buy_soldier(SoldierType.INFANTRY, quantity=3)
        s_ids = [s["id"] for s in buy_res["purchased"]]

        # Motorcycle rejects > 2 soldiers
        with pytest.raises(ValueError, match="máximo 2"):
            log_srv.dispatch_ground(TransportType.MOTORCYCLE, s_ids, "T1")

        # Moto 1 carries 1 soldier, Moto 2 carries 1 soldier, starting 1s apart
        m1 = log_srv.dispatch_ground(TransportType.MOTORCYCLE, [s_ids[0]], "T1")
        # Advance 3s: Moto 1 finishes Base->N1 (2s) and is 1s into N1->T1 (bridge, total 3s)
        log_srv.advance_missions(3.0)

        # Dispatch Moto 2 at t=3s; advance 2s -> Moto 1 finishes N1->T1 (bridge collapses!)
        # Meanwhile Moto 2 has finished Base->N1 (2s) and tries to enter N1->T1 (now collapsed!)
        m2 = log_srv.dispatch_ground(TransportType.MOTORCYCLE, [s_ids[1]], "T1")
        events = log_srv.advance_missions(2.0)

        bridge = srv.elevated_graph.get_elevated_edge("N1", "T1")
        assert bridge.is_destroyed is True
        assert bridge.current_resistance == 0
        assert srv.simulation_state.soldiers[s_ids[0]].status == "apostado"

        # Now test in-progress crossing allowed to finish:
        # Reset bridge resistance to 1, send Moto A & Moto B at the same time on N1->T1
        bridge.current_resistance = 1
        bridge.is_destroyed = False
        srv.elevated_graph._sync_bridge_adj(bridge)

        # Ensure T1 has room for 2 more -> remove s_ids[0] temporarily or use fresh scenario
        srv2 = build_bridge_scenario()
        log_srv2 = LogisticsService(srv2)
        s2_ids = [s["id"] for s in log_srv2.buy_soldier(SoldierType.INFANTRY, quantity=2)["purchased"]]

        log_srv2.dispatch_ground(TransportType.MOTORCYCLE, [s2_ids[0]], "T1")
        log_srv2.advance_missions(2.5)  # Moto A is already 0.5s inside bridge N1->T1 (edge_progress=0.5)
        log_srv2.dispatch_ground(TransportType.MOTORCYCLE, [s2_ids[1]], "T1")
        log_srv2.advance_missions(2.1)  # Moto A at 2.6s on bridge; Moto B is 0.1s inside bridge N1->T1!

        b2 = srv2.elevated_graph.get_elevated_edge("N1", "T1")
        assert b2.is_destroyed is False  # Moto A hasn't finished yet

        # Advance 0.5s: Moto A finishes crossing -> bridge collapses, BUT Moto B already started crossing so it continues!
        log_srv2.advance_missions(0.5)
        assert b2.is_destroyed is True
        assert srv2.simulation_state.soldiers[s2_ids[0]].status == "apostado"

        # Advance remaining 2.4s: Moto B finishes crossing the collapsed bridge safely!
        log_srv2.advance_missions(2.4)
        assert srv2.simulation_state.soldiers[s2_ids[1]].status == "apostado"

    def test_blocked_mission_reroutes_along_alternative_path(self):
        srv = build_bridge_scenario()
        log_srv = LogisticsService(srv)
        s_ids = [s["id"] for s in log_srv.buy_soldier(SoldierType.INFANTRY, quantity=1)["purchased"]]

        # Dispatch on foot (Base -> N1 -> T1 = 10s). Advance 4.0s -> arrives at N1 just as bridge collapses!
        m = log_srv.dispatch_ground(TransportType.FOOT, s_ids, "T1")
        mission_obj = srv.simulation_state.active_missions[0]

        # Collapse bridge N1-T1 BEFORE soldier enters it
        bridge = srv.elevated_graph.get_elevated_edge("N1", "T1")
        bridge.on_motorcycle_cross_complete()
        srv.elevated_graph._sync_bridge_adj(bridge)

        # Advance 4.0s to reach N1, then 0.5s to evaluate N1->T1 -> must reroute via N1->Base->N2->T1!
        log_srv.advance_missions(4.5)
        assert mission_obj.is_blocked is False
        assert mission_obj.path == ["N1", "Base", "N2", "T1"]

        # Finish remaining travel: 3.5s (to Base) + 10s (Base->N2) + 10s (N2->T1) = 23.5s
        log_srv.advance_missions(23.5)
        assert mission_obj.is_completed is True
        assert srv.simulation_state.soldiers[s_ids[0]].status == "apostado"

    def test_isolated_mission_waits_and_resumes_after_reconstruction(self):
        srv = ScenarioService()
        srv.load_from_dict({
            "scenario_name": "Single Bridge Isolation",
            "config": {"initial_budget": 1000.0},
            "elevated_network": {
                "nodes": [
                    {"id": "Base", "x": 0.0, "y": 0.0, "type": "Base"},
                    {"id": "N1", "x": 10.0, "y": 0.0, "type": "Tránsito"},
                    {"id": "T1", "x": 20.0, "y": 0.0, "type": "Candidato"},
                ],
                "edges": [
                    {"u": "Base", "v": "N1", "foot_time": 2.0, "moto_time": 1.0, "is_bridge": False},
                    {
                        "u": "N1",
                        "v": "T1",
                        "foot_time": 4.0,
                        "moto_time": 2.0,
                        "is_bridge": True,
                        "max_resistance": 1,
                        "reconstruction_duration": 5.0,
                    },
                ],
            },
            "maze_network": {
                "nodes": [{"id": "IN", "x": 0, "y": 10, "is_entry": True}, {"id": "OUT", "x": 10, "y": 10, "is_exit": True}],
                "corridors": [{"u": "IN", "v": "OUT", "length": 10.0, "speed": 1.0}],
            },
        })
        srv.elevated_graph.get_elevated_node("T1").is_active_tower = True
        log_srv = LogisticsService(srv)

        s_ids = [s["id"] for s in log_srv.buy_soldier(SoldierType.INFANTRY, quantity=2)["purchased"]]

        # Moto 1 crosses and collapses the only bridge N1-T1
        log_srv.dispatch_ground(TransportType.MOTORCYCLE, [s_ids[0]], "T1")
        log_srv.advance_missions(1.0)  # Moto 1 at N1, now dispatch foot soldier 2
        m2 = log_srv.dispatch_ground(TransportType.FOOT, [s_ids[1]], "T1")
        mission2 = srv.simulation_state.active_missions[1]

        # Advance 2.5s: Moto 1 finishes bridge -> bridge collapses; Foot 2 arrives at N1 and gets blocked!
        log_srv.advance_missions(2.5)
        bridge = srv.elevated_graph.get_elevated_edge("N1", "T1")
        assert bridge.is_destroyed is True
        assert mission2.is_blocked is True
        assert mission2.is_completed is False

        # Reconstruct bridge over 5.0s
        rebuilt = srv.elevated_graph.update_reconstruction_timers(5.0)
        assert rebuilt == ["N1-T1"]
        assert bridge.is_destroyed is False

        # Advance 4.0s: blocked mission automatically resumes and arrives at T1!
        log_srv.advance_missions(4.0)
        assert mission2.is_blocked is False
        assert mission2.is_completed is True
        assert len(srv.elevated_graph.get_elevated_node("T1").stationed_soldiers) == 2

    def test_tower_limit_three_includes_in_transit_reservations(self):
        srv = build_bridge_scenario()
        log_srv = LogisticsService(srv)
        s_ids = [s["id"] for s in log_srv.buy_soldier(SoldierType.INFANTRY, quantity=4)["purchased"]]

        # Reserve 2 on moto + 1 on foot = 3 slots committed on T1
        log_srv.dispatch_ground(TransportType.MOTORCYCLE, s_ids[:2], "T1")
        log_srv.dispatch_ground(TransportType.FOOT, [s_ids[2]], "T1")

        t1 = srv.elevated_graph.get_elevated_node("T1")
        assert t1.reserved_slots == 3
        assert t1.available_slots == 0

        # 4th soldier must be rejected!
        with pytest.raises(ValueError, match="Capacidad insuficiente"):
            log_srv.dispatch_ground(TransportType.FOOT, [s_ids[3]], "T1")
