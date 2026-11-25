"""Unit & integration tests for Stage 5: Discrete tick engine, combat, rewards, end conditions & REST API."""

import os
import pytest
from fastapi.testclient import TestClient
from main import app, BASE_DIR
from app.domain.soldier import SoldierType
from app.services.scenario_service import ScenarioService
from app.services.logistics_service import LogisticsService
from app.services.simulation_service import SimulationService


def build_combat_scenario(
    initial_budget: float = 2000.0,
    corridor_length: float = 20.0,
    corridor_speed: float = 1.0,
    max_time_limit: float = 300.0,
    convoy_list=None,
) -> ScenarioService:
    srv = ScenarioService()
    srv.load_from_dict({
        "scenario_name": "Stage 5 Combat Test",
        "config": {
            "initial_budget": initial_budget,
            "beta_elevation": 0.1,
            "alpha_danger": 1.0,
            "helicopter_cost": 150.0,
            "helicopter_speed": 20.0,
            "max_time_limit": max_time_limit,
        },
        "elevated_network": {
            "nodes": [
                {"id": "Base", "x": 0.0, "y": 0.0, "z": 0.0, "type": "Base"},
                {"id": "H1", "x": 0.0, "y": 10.0, "z": 0.0, "type": "Helipuerto"},
                {"id": "T1", "x": 10.0, "y": 0.0, "z": 10.0, "type": "Candidato", "surveillance_radius": 50.0},
            ],
            "edges": [
                {"u": "Base", "v": "T1", "foot_time": 1.0, "moto_time": 1.0, "is_bridge": False},
            ],
        },
        "maze_network": {
            "nodes": [
                {"id": "IN", "x": 0.0, "y": 0.0, "is_entry": True},
                {"id": "OUT", "x": corridor_length, "y": 0.0, "is_exit": True},
            ],
            "corridors": [
                {"u": "IN", "v": "OUT", "length": corridor_length, "speed": corridor_speed},
            ],
        },
        "convoy": convoy_list or [
            {"type": "Tanque", "hp": 200.0, "reward": 150},
            {"type": "Camión", "hp": 100.0, "reward": 100},
            {"type": "Robot", "hp": 50.0, "reward": 50},
        ],
    })
    srv.elevated_graph.get_elevated_node("T1").is_active_tower = True
    return srv


class TestStage5TickCombatAndEndConditions:
    def test_single_target_lowest_hp_and_bounty_reward(self):
        srv = build_combat_scenario(initial_budget=1000.0, corridor_length=30.0, corridor_speed=1.0)
        sim = SimulationService(srv)
        sim.reset_full()

        # Buy 1 Sniper ($300, dmg=50, base_r=20 -> R_ef at z=10 is 20*(1+0.1*10)=40.0, f=0.5 -> every 2s)
        s_res = sim.logistics_service.buy_soldier(SoldierType.SNIPER, quantity=1)
        s_id = s_res["purchased"][0]["id"]
        assert srv.simulation_state.budget_available == 700.0

        sim.logistics_service.dispatch_ground("Moto", [s_id], "T1")

        # Tick 1 (dt=1.0): Moto arrives at T1 in step 1 -> Sniper immediately fires in step 2!
        # Targets lowest HP enemy: Robot (50 HP) -> destroyed -> +$50 reward!
        state1 = sim.tick(dt=1.0)
        assert state1["clock"] == 1.0
        assert len(state1["last_combat"]["attacks"]) == 1
        assert state1["last_combat"]["attacks"][0]["targets"][0] == srv.simulation_state.enemies[2].id
        assert srv.simulation_state.enemies[2].is_alive is False
        assert state1["last_combat"]["rewards_earned"] == 50
        assert state1["budget"]["available"] == 750.0
        assert state1["is_game_over"] is False

        # Tick 2 (dt=1.0): Sniper is on 2.0s cooldown (remaining 1.0s after dt=1.0 update -> 0.0 at end, wait:
        # trigger_attack sets cooldown=2.0; update_cooldown(1.0) sets cooldown=1.0 -> cannot attack on tick 2!)
        state2 = sim.tick(dt=1.0)
        assert len(state2["last_combat"]["attacks"]) == 0

        # Tick 3 (dt=1.0): Cooldown drops from 1.0 to 0.0 -> fires at Camión (100 HP -> 50 HP)
        state3 = sim.tick(dt=1.0)
        assert len(state3["last_combat"]["attacks"]) == 1
        assert srv.simulation_state.enemies[1].current_hp == 50.0

    def test_artillery_area_damage_and_elimination_victory(self):
        srv = build_combat_scenario(
            initial_budget=1500.0,
            corridor_length=40.0,
            corridor_speed=1.0,
            convoy_list=[
                {"type": "Camión", "hp": 100.0, "reward": 100},
                {"type": "Robot", "hp": 50.0, "reward": 50},
            ],
        )
        sim = SimulationService(srv)
        sim.reset_full()

        # Place 1 Artillero ($500, dmg=100, base_r=15 -> R_ef at z=10 = 30.0) directly on T1 via 1s moto
        s_id = sim.logistics_service.buy_soldier(SoldierType.GUNNER, quantity=1)["purchased"][0]["id"]
        sim.logistics_service.dispatch_ground("Moto", [s_id], "T1")

        state = sim.tick(dt=1.0)
        # Artillero hits BOTH Camión (100->0) and Robot (50->0) in one area blast!
        assert state["is_game_over"] is True
        assert state["game_result"] == "Victoria por eliminación"
        assert state["convoy"]["alive_count"] == 0
        assert state["budget"]["available"] == 1000.0 + 150.0  # 1500 - 500 + 100 + 50

    def test_defeat_when_convoy_reaches_exit(self):
        srv = build_combat_scenario(corridor_length=10.0, corridor_speed=5.0)  # 2.0s to OUT
        sim = SimulationService(srv)
        sim.reset_full()

        s1 = sim.tick(dt=1.0)
        assert s1["is_game_over"] is False
        s2 = sim.tick(dt=1.0)
        assert s2["is_game_over"] is True
        assert s2["game_result"] == "Derrota"
        assert s2["convoy"]["current_node"] == "OUT"

    def test_resistance_victory_at_300_seconds(self):
        # Very long corridor (speed=1, length=1000) so convoy cannot reach OUT in 300s
        srv = build_combat_scenario(corridor_length=1000.0, corridor_speed=1.0, max_time_limit=300.0)
        sim = SimulationService(srv)
        sim.reset_full()

        # Advance 299s -> still running
        s_mid = sim.tick(dt=299.0)
        assert s_mid["clock"] == 299.0
        assert s_mid["is_game_over"] is False

        # Advance 1s -> hits 300.0s -> Victoria por resistencia
        s_end = sim.tick(dt=1.0)
        assert s_end["clock"] == 300.0
        assert s_end["is_game_over"] is True
        assert s_end["game_result"] == "Victoria por resistencia"

    def test_convoy_does_not_reverse_mid_corridor_and_recalculates_at_intersection(self):
        srv = ScenarioService()
        srv.load_from_dict({
            "scenario_name": "Mid-corridor & Intersection Re-eval",
            "config": {"initial_budget": 2000.0, "alpha_danger": 2.0, "beta_elevation": 0.1},
            "elevated_network": {
                "nodes": [
                    {"id": "Base", "x": 0.0, "y": 0.0, "z": 0.0, "type": "Base"},
                    {"id": "T_top", "x": 20.0, "y": 15.0, "z": 0.0, "type": "Candidato"},
                ],
                "edges": [
                    {"u": "Base", "v": "T_top", "foot_time": 1.0, "moto_time": 1.0},
                ],
            },
            "maze_network": {
                "nodes": [
                    {"id": "IN", "x": 0.0, "y": 0.0, "is_entry": True},
                    {"id": "FORK", "x": 10.0, "y": 0.0},
                    {"id": "A", "x": 20.0, "y": 10.0},
                    {"id": "B", "x": 20.0, "y": -10.0},
                    {"id": "OUT", "x": 30.0, "y": 0.0, "is_exit": True},
                ],
                "corridors": [
                    {"u": "IN", "v": "FORK", "length": 10.0, "speed": 2.0},   # 5.0s
                    {"u": "FORK", "v": "A", "length": 10.0, "speed": 2.0},    # 5.0s (A < B lexicographically)
                    {"u": "A", "v": "OUT", "length": 10.0, "speed": 2.0},     # 5.0s
                    {"u": "FORK", "v": "B", "length": 12.0, "speed": 2.0},    # 6.0s
                    {"u": "B", "v": "OUT", "length": 12.0, "speed": 2.0},     # 6.0s
                ],
            },
            "convoy": [{"type": "Tanque", "hp": 5000.0, "reward": 150}],
        })
        srv.elevated_graph.get_elevated_node("T_top").is_active_tower = True
        sim = SimulationService(srv)
        sim.reset_full()

        # Tick 2s: convoy enters IN->FORK (mid-corridor, x=4.0)
        s1 = sim.tick(dt=2.0)
        assert s1["convoy"]["current_edge"] == ["IN", "FORK"]
        assert s1["convoy"]["x"] == pytest.approx(4.0)

        # Deploy Sniper onto T_top covering FORK->A->OUT while convoy is still inside IN->FORK
        snip_id = sim.logistics_service.buy_soldier("Francotirador", 1)["purchased"][0]["id"]
        sim.logistics_service.dispatch_ground("Moto", [snip_id], "T_top")

        # Tick 3s: convoy finishes IN->FORK (never reverses mid-corridor!) and Sniper arrives on T_top
        s2 = sim.tick(dt=3.0)
        assert s2["convoy"]["current_node"] == "FORK"
        assert s2["convoy"]["current_edge"] is None

        # Next tick from FORK: recalculates reactive weights -> avoids Sniper on A, picks FORK -> B!
        s3 = sim.tick(dt=1.0)
        assert s3["convoy"]["current_edge"] == ["FORK", "B"]


class TestStage4And5ApiEndpoints:
    def test_logistics_and_simulation_endpoints_end_to_end(self):
        scenario_path = os.path.join(BASE_DIR, "data", "scenario_1_basic.json")
        ScenarioService.get_instance().load_from_file(scenario_path)

        with TestClient(app) as client:
            sel_res = client.post("/api/planning/select-towers", json={"k_towers": 3, "d0_normalization": 50.0})
            assert sel_res.status_code == 200
            selected_towers = sel_res.json()["selected_towers"]
            assert len(selected_towers) >= 1
            active_tower_id = selected_towers[0]["tower_id"]

            reset_res = client.post("/api/simulation/reset")
            assert reset_res.status_code == 200
            assert reset_res.json()["clock"] == 0.0

            # 1. Buy 2 Infantry + 1 Sniper ($500 total)
            buy1 = client.post("/api/logistics/buy-soldier", json={"soldier_type": "Infantería", "quantity": 2})
            assert buy1.status_code == 200
            buy2 = client.post("/api/logistics/buy-soldier", json={"soldier_type": "Francotirador", "quantity": 1})
            assert buy2.status_code == 200

            inf_ids = [s["id"] for s in buy1.json()["purchased"]]
            snip_id = buy2.json()["purchased"][0]["id"]

            # 2. Dispatch ground motorcycle to active tower
            g_res = client.post(
                "/api/logistics/dispatch-ground",
                json={"transport_type": "Moto", "soldier_ids": inf_ids, "destination_id": active_tower_id},
            )
            assert g_res.status_code == 200
            assert g_res.json()["type"] == "Moto"

            # 3. Dispatch air helicopter to active tower
            a_res = client.post(
                "/api/logistics/dispatch-air",
                json={"soldier_ids": [snip_id], "destination_id": active_tower_id},
            )
            assert a_res.status_code == 200
            assert a_res.json()["type"] == "Helicóptero"

            # 4. Inspect logistics state
            log_state = client.get("/api/logistics/state")
            assert log_state.status_code == 200
            assert len(log_state.json()["missions"]) == 2

            # 5. Advance simulation ticks
            step_res = client.post("/api/simulation/step", json={"dt": 1.0})
            assert step_res.status_code == 200
            assert step_res.json()["clock"] == 1.0

            state_res = client.get("/api/simulation/state")
            assert state_res.status_code == 200
            assert state_res.json()["clock"] == 1.0
