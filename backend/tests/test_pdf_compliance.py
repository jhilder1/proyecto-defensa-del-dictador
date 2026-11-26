"""Tests verifying full compliance with the official SismoLab AVL PDF specification."""

import os
import pytest
from main import BASE_DIR
from app.core.algorithms import dijkstra_elevated, kruskal_mst
from app.domain.soldier import SoldierType
from app.domain.transport import TransportType
from app.services.scenario_service import ScenarioService
from app.services.planning_service import PlanningService
from app.services.logistics_service import LogisticsService
from app.services.simulation_service import SimulationService


def _minimal_valid_dict():
    return {
        "scenario_name": "Valid Base",
        "config": {"initial_budget": 1500.0},
        "elevated_network": {
            "nodes": [
                {"id": "Base", "x": 0, "y": 0, "z": 1, "type": "Base"},
                {"id": "H1", "x": 0, "y": 10, "z": 1, "type": "Helipuerto"},
                {"id": "T1", "x": 10, "y": 5, "z": 5, "type": "Candidato", "surveillance_radius": 20},
                {"id": "T2", "x": 20, "y": 5, "z": 5, "type": "Candidato", "surveillance_radius": 20},
            ],
            "edges": [
                {"u": "Base", "v": "T1", "foot_time": 4.0, "moto_time": 2.0},
                {"u": "Base", "v": "H1", "foot_time": 5.0, "moto_time": 2.0},
                {"u": "T1", "v": "T2", "foot_time": 5.0, "moto_time": 2.0},
            ],
        },
        "maze_network": {
            "nodes": [
                {"id": "IN", "x": 0, "y": 5, "is_entry": True},
                {"id": "OUT", "x": 25, "y": 5, "is_exit": True},
            ],
            "corridors": [{"u": "IN", "v": "OUT", "length": 25.0, "speed": 2.0}],
        },
        "convoy": {"Tanque": 1, "Camión": 2, "Soldado robot": 3},
    }


class TestPdfScenarioValidations:
    def test_convoy_dict_counts_format(self):
        srv = ScenarioService()
        srv.load_from_dict(_minimal_valid_dict())
        enemies = srv.simulation_state.enemies
        assert len(enemies) == 6
        assert sum(1 for e in enemies if e.enemy_type.value == "Tanque") == 1
        assert sum(1 for e in enemies if e.enemy_type.value == "Camión") == 2
        assert sum(1 for e in enemies if e.enemy_type.value == "Robot") == 3

    def test_rejects_missing_or_duplicate_base(self):
        data = _minimal_valid_dict()
        data["elevated_network"]["nodes"][0]["type"] = "Tránsito"
        with pytest.raises(ValueError, match="exactamente una Base"):
            ScenarioService().load_from_dict(data)

        data2 = _minimal_valid_dict()
        data2["elevated_network"]["nodes"][1]["type"] = "Base"
        with pytest.raises(ValueError, match="exactamente una Base"):
            ScenarioService().load_from_dict(data2)

    def test_rejects_negative_ge_coordinates_and_same_entry_exit(self):
        data = _minimal_valid_dict()
        data["elevated_network"]["nodes"][0]["x"] = -1.0
        with pytest.raises(ValueError, match="no negativas"):
            ScenarioService().load_from_dict(data)

        data2 = _minimal_valid_dict()
        data2["maze_network"]["nodes"] = [{"id": "SAME", "x": 0, "y": 0, "is_entry": True, "is_exit": True}]
        data2["maze_network"]["corridors"] = []
        with pytest.raises(ValueError, match="diferentes"):
            ScenarioService().load_from_dict(data2)

    def test_rejects_disconnected_maze_without_entry_exit_path(self):
        data = _minimal_valid_dict()
        data["maze_network"]["corridors"] = []
        with pytest.raises(ValueError, match="camino inicial válido"):
            ScenarioService().load_from_dict(data)

    def test_optional_foot_and_moto_edges(self):
        data = _minimal_valid_dict()
        # T1-T2 is foot-only (moto_time=None)
        data["elevated_network"]["edges"][2] = {"u": "T1", "v": "T2", "foot_time": 5.0, "moto_time": None}
        srv = ScenarioService()
        srv.load_from_dict(data)
        ge = srv.elevated_graph

        # MST uses foot_time -> succeeds and includes T1-T2
        mst = kruskal_mst(ge, "Base")
        assert "T2" in mst["tree_distances"]

        # Foot Dijkstra can reach T2, Moto Dijkstra CANNOT cross T1-T2
        assert dijkstra_elevated(ge, "Base", "T2", TransportType.FOOT) is not None
        assert dijkstra_elevated(ge, "Base", "T2", TransportType.MOTORCYCLE) is None


class TestPdfLogisticsAndSimulationRules:
    def test_bridge_reconstruction_personnel_pool_and_queue(self):
        data = _minimal_valid_dict()
        data["config"]["total_repair_personnel"] = 4
        data["elevated_network"]["edges"] = [
            {
                "u": "Base", "v": "T1", "foot_time": 2.0, "moto_time": 1.0,
                "is_bridge": True, "max_resistance": 1, "reconstruction_duration": 5.0, "repair_personnel": 3,
            },
            {
                "u": "Base", "v": "T2", "foot_time": 2.0, "moto_time": 1.0,
                "is_bridge": True, "max_resistance": 1, "reconstruction_duration": 5.0, "repair_personnel": 3,
            },
        ]
        srv = ScenarioService()
        srv.load_from_dict(data)
        ge = srv.elevated_graph
        ge.get_elevated_node("T1").is_active_tower = True
        ge.get_elevated_node("T2").is_active_tower = True

        # Collapse both bridges simultaneously
        ge.record_motorcycle_bridge_crossing("Base", "T1")
        ge.record_motorcycle_bridge_crossing("Base", "T2")
        b1 = ge.get_elevated_edge("Base", "T1")
        b2 = ge.get_elevated_edge("Base", "T2")
        assert b1.is_destroyed and b2.is_destroyed

        state = srv.simulation_state
        # First 5s: only 1 bridge can acquire 3 workers out of 4 total!
        rebuilt1 = ge.update_reconstruction_timers(5.0, simulation_state=state)
        assert len(rebuilt1) == 1
        assert b1.is_destroyed is False
        assert b2.is_destroyed is True
        assert state.available_repair_personnel == 4  # freed once b1 finished

        # Next 5s: second bridge now acquires 3 workers and finishes!
        rebuilt2 = ge.update_reconstruction_timers(5.0, simulation_state=state)
        assert len(rebuilt2) == 1
        assert b2.is_destroyed is False
        assert state.available_repair_personnel == 4

    def test_helicopter_max_uses_and_fleet_availability(self):
        data = _minimal_valid_dict()
        data["config"]["max_helicopter_uses"] = 1
        data["config"]["helicopter_fleet_size"] = 1
        data["config"]["helicopter_speed"] = 10.0
        srv = ScenarioService()
        srv.load_from_dict(data)
        srv.elevated_graph.get_elevated_node("T1").is_active_tower = True
        srv.elevated_graph.get_elevated_node("T2").is_active_tower = True

        log_srv = LogisticsService(srv)
        s_ids = [s["id"] for s in log_srv.buy_soldier(SoldierType.INFANTRY, 4)["purchased"]]

        # Dispatch 4 to T1 (3 slots -> 1 surplus auto-routed to T2): entire circuit uses 1 use!
        mission = log_srv.dispatch_air(s_ids, "T1")
        assert mission["path"] == ["H1", "T1", "T2"]
        assert srv.simulation_state.remaining_helicopter_uses == 0

        # 2nd air dispatch fails because max uses exhausted
        s_extra = log_srv.buy_soldier(SoldierType.INFANTRY, 1)["purchased"][0]["id"]
        with pytest.raises(ValueError, match="No quedan usos disponibles"):
            log_srv.dispatch_air([s_extra], "T2")

        # Fleet busy test when max_uses = 2 and fleet = 1
        srv.simulation_state.remaining_helicopter_uses = 2
        with pytest.raises(ValueError, match="flota en vuelo"):
            log_srv.dispatch_air([s_extra], "T2")

    def test_tower_freeze_after_simulation_starts(self):
        srv = ScenarioService()
        srv.load_from_dict(_minimal_valid_dict())
        plan = PlanningService(srv)
        sim = SimulationService(srv)

        # Allowed before clock starts
        plan.select_towers(k_towers=2, d0_normalization=30.0)

        # Advance 1 tick
        sim.tick(dt=1.0)
        with pytest.raises(ValueError, match="una vez iniciado el enfrentamiento"):
            plan.select_towers(k_towers=2, d0_normalization=30.0)

    def test_ground_relocation_between_towers(self):
        srv = ScenarioService()
        srv.load_from_dict(_minimal_valid_dict())
        t1 = srv.elevated_graph.get_elevated_node("T1")
        t2 = srv.elevated_graph.get_elevated_node("T2")
        t1.is_active_tower = True
        t2.is_active_tower = True

        log_srv = LogisticsService(srv)
        s_id = log_srv.buy_soldier(SoldierType.INFANTRY, 1)["purchased"][0]["id"]
        log_srv.dispatch_ground(TransportType.MOTORCYCLE, [s_id], "T1")
        log_srv.advance_missions(2.0)
        assert s_id in t1.stationed_soldiers

        # Relocate from T1 to T2
        log_srv.dispatch_ground(TransportType.MOTORCYCLE, [s_id], "T2", origin_id="T1")
        assert s_id not in t1.stationed_soldiers
        assert t2.reserved_slots == 1

        log_srv.advance_missions(2.0)
        assert s_id in t2.stationed_soldiers
        assert t2.reserved_slots == 0
        assert srv.simulation_state.soldiers[s_id].location_node_id == "T2"


class TestTacticalScenariosEndToEnd:
    @pytest.mark.parametrize("filename", ["scenario_1_basic.json", "scenario_2_complex.json"])
    def test_scenarios_support_mst_towers_and_real_combat(self, filename):
        srv = ScenarioService()
        summary = srv.load_from_file(os.path.join(BASE_DIR, "data", filename))
        assert summary["initial_maze_route"] is not None

        plan = PlanningService(srv)
        mst = plan.calculate_mst()
        # Scenario 2 has disconnected island T_ISL which must be excluded from MST
        if filename == "scenario_2_complex.json":
            assert "T_ISL" not in mst["tree_distances"]

        sel = plan.select_towers(k_towers=4, d0_normalization=35.0)
        assert sel["towers_selected_count"] >= 3
        assert sel["coverage_percentage"] >= 70.0

        # Deploy Sniper to first selected tower & run ticks -> verify real combat damage happens!
        sim = SimulationService(srv)
        sim.reset_full()
        target_tower = sel["selected_towers"][0]["tower_id"]
        snip_id = sim.logistics_service.buy_soldier(SoldierType.SNIPER, 1)["purchased"][0]["id"]
        sim.logistics_service.dispatch_ground(TransportType.MOTORCYCLE, [snip_id], target_tower)

        any_attack = False
        for _ in range(30):
            st = sim.tick(dt=1.0)
            if st["last_combat"] and len(st["last_combat"].get("attacks", [])) > 0:
                any_attack = True
                break
            if st["is_game_over"]:
                break
        assert any_attack is True, f"No combat shots landed in {filename}!"
