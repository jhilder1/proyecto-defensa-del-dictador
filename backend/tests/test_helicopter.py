"""Unit tests for Stage 4: Helicopter flight duration, budget reservations, and surplus redistribution."""

import pytest
from app.domain.soldier import SoldierType
from app.domain.transport import TransportType
from app.services.scenario_service import ScenarioService
from app.services.logistics_service import LogisticsService


def build_air_scenario(initial_budget: float = 2000.0) -> ScenarioService:
    srv = ScenarioService()
    srv.load_from_dict({
        "scenario_name": "Air Logistics Test",
        "config": {
            "initial_budget": initial_budget,
            "helicopter_cost": 150.0,
            "helicopter_speed": 10.0,
        },
        "elevated_network": {
            "nodes": [
                {"id": "Base", "x": 0.0, "y": 0.0, "type": "Base"},
                {"id": "H1", "x": 0.0, "y": 30.0, "type": "Helipuerto"},
                {"id": "T1", "x": 40.0, "y": 0.0, "type": "Candidato"},   # dist(H1, T1) = 50 -> 5.0s
                {"id": "T2", "x": 40.0, "y": 20.0, "type": "Candidato"},  # dist(T1, T2) = 20 -> 2.0s
                {"id": "T3", "x": 40.0, "y": 60.0, "type": "Candidato"},  # dist(T1, T3) = 60 -> 6.0s
            ],
            "edges": [
                {"u": "Base", "v": "H1", "foot_time": 10.0, "moto_time": 4.0},
            ],
        },
        "maze_network": {
            "nodes": [{"id": "IN", "x": 0, "y": 50, "is_entry": True}, {"id": "OUT", "x": 50, "y": 50, "is_exit": True}],
            "corridors": [{"u": "IN", "v": "OUT", "length": 50.0, "speed": 1.0}],
        },
        "convoy": [{"type": "Robot", "hp": 50.0, "reward": 50}],
    })
    for tid in ["T1", "T2", "T3"]:
        srv.elevated_graph.get_elevated_node(tid).is_active_tower = True
    return srv


class TestHelicopterLogistics:
    def test_helicopter_capacity_and_budget_validation(self):
        srv = build_air_scenario(initial_budget=600.0)
        log_srv = LogisticsService(srv)

        s_ids = [s["id"] for s in log_srv.buy_soldier(SoldierType.INFANTRY, quantity=5)["purchased"]]
        assert srv.simulation_state.budget_available == 100.0  # 600 - 500

        # > 4 soldiers rejected
        with pytest.raises(ValueError, match="capacidad máxima de 4"):
            log_srv.dispatch_air(s_ids, "T1")

        # Insufficient budget for flight ($150 required, $100 available)
        with pytest.raises(ValueError, match="Fondos insuficientes"):
            log_srv.dispatch_air(s_ids[:4], "T1")

    def test_direct_flight_euclidean_duration_and_budget_commit(self):
        srv = build_air_scenario(initial_budget=1000.0)
        log_srv = LogisticsService(srv)
        s_ids = [s["id"] for s in log_srv.buy_soldier(SoldierType.INFANTRY, quantity=2)["purchased"]]

        # Available: 800. Flight cost: 150 -> reserved during flight
        mission = log_srv.dispatch_air(s_ids, "T1")
        assert mission["path"] == ["H1", "T1"]
        assert mission["total_flight_distance"] == pytest.approx(50.0)
        assert mission["total_flight_duration"] == pytest.approx(5.0)
        assert srv.simulation_state.budget_available == pytest.approx(650.0)
        assert srv.simulation_state.budget_reserved == pytest.approx(150.0)

        # Mid-flight at t=2.5s
        log_srv.advance_missions(2.5)
        m_obj = srv.simulation_state.active_missions[0]
        assert m_obj.is_completed is False
        assert m_obj.current_x == pytest.approx(20.0)
        assert m_obj.current_y == pytest.approx(15.0)

        # Complete flight at t=5.0s
        log_srv.advance_missions(2.5)
        assert m_obj.is_completed is True
        assert srv.simulation_state.budget_reserved == pytest.approx(0.0)
        t1 = srv.elevated_graph.get_elevated_node("T1")
        assert len(t1.stationed_soldiers) == 2
        assert t1.reserved_slots == 0
        for sid in s_ids:
            assert srv.simulation_state.soldiers[sid].status == "apostado"

    def test_surplus_redistribution_to_nearest_towers_and_return_to_base(self):
        srv = build_air_scenario(initial_budget=2000.0)
        log_srv = LogisticsService(srv)
        ge = srv.elevated_graph

        # Pre-fill T1 with 1 soldier (2 slots left), T2 with 2 soldiers (1 slot left), T3 with 3 soldiers (0 slots left)
        t1, t2, t3 = ge.get_elevated_node("T1"), ge.get_elevated_node("T2"), ge.get_elevated_node("T3")
        t1.stationed_soldiers.append("pre_1")
        t2.stationed_soldiers.extend(["pre_2", "pre_3"])
        t3.stationed_soldiers.extend(["pre_4", "pre_5", "pre_6"])

        # Buy 4 new soldiers and fly to T1:
        # Should drop 2 at T1, fly to nearest open T2 and drop 1, then return 1 surplus to Base!
        s_ids = [s["id"] for s in log_srv.buy_soldier(SoldierType.INFANTRY, quantity=4)["purchased"]]
        mission = log_srv.dispatch_air(s_ids, "T1")

        assert mission["path"] == ["H1", "T1", "T2", "Base"]
        assert mission["returned_to_base_soldiers"] == [s_ids[3]]
        assert t1.reserved_slots == 2
        assert t2.reserved_slots == 1
        assert t3.reserved_slots == 0

        # Leg durations: H1->T1 (5.0s) + T1->T2 (2.0s) + T2->Base (sqrt(40^2+20^2)/10 = 4.4721s)
        # Advance 5.0s: T1 receives 2 soldiers
        log_srv.advance_missions(5.0)
        assert len(t1.stationed_soldiers) == 3
        assert t1.reserved_slots == 0
        assert srv.simulation_state.soldiers[s_ids[0]].status == "apostado"
        assert srv.simulation_state.soldiers[s_ids[1]].status == "apostado"

        # Advance 2.0s: T2 receives 1 soldier
        log_srv.advance_missions(2.0)
        assert len(t2.stationed_soldiers) == 3
        assert t2.reserved_slots == 0
        assert srv.simulation_state.soldiers[s_ids[2]].status == "apostado"

        # Advance 5.0s: Base receives returned surplus soldier
        log_srv.advance_missions(5.0)
        m_obj = srv.simulation_state.active_missions[0]
        assert m_obj.is_completed is True
        assert srv.simulation_state.soldiers[s_ids[3]].status == "en_base"
        assert srv.simulation_state.soldiers[s_ids[3]].location_node_id == "Base"

    def test_all_towers_full_returns_all_soldiers_to_base(self):
        srv = build_air_scenario(initial_budget=2000.0)
        log_srv = LogisticsService(srv)
        ge = srv.elevated_graph

        for tid in ["T1", "T2", "T3"]:
            ge.get_elevated_node(tid).stationed_soldiers.extend([f"{tid}_a", f"{tid}_b", f"{tid}_c"])

        s_ids = [s["id"] for s in log_srv.buy_soldier(SoldierType.INFANTRY, quantity=3)["purchased"]]
        mission = log_srv.dispatch_air(s_ids, "T1")

        # Leg 1 goes to T1 (0 dropped), Leg 2 goes straight back to Base with all 3
        assert mission["path"] == ["H1", "T1", "Base"]
        assert mission["returned_to_base_soldiers"] == s_ids

        log_srv.advance_missions(mission["total_flight_duration"] + 0.1)
        for sid in s_ids:
            assert srv.simulation_state.soldiers[sid].status == "en_base"
            assert srv.simulation_state.soldiers[sid].location_node_id == "Base"
        for tid in ["T1", "T2", "T3"]:
            assert len(ge.get_elevated_node(tid).stationed_soldiers) == 3

    def test_surplus_tie_breaking_uses_lexicographical_tower_id(self):
        srv = build_air_scenario(initial_budget=2000.0)
        ge = srv.elevated_graph
        # Make T2 and T3 equidistant from T1 (both distance 20.0)
        ge.get_elevated_node("T3").x = 40.0
        ge.get_elevated_node("T3").y = -20.0

        ge.get_elevated_node("T1").stationed_soldiers.extend(["a", "b"])  # 1 free slot
        log_srv = LogisticsService(srv)
        s_ids = [s["id"] for s in log_srv.buy_soldier(SoldierType.INFANTRY, quantity=2)["purchased"]]

        mission = log_srv.dispatch_air(s_ids, "T1")
        assert mission["path"] == ["H1", "T1", "T2"]  # T2 < T3 lexicographically
