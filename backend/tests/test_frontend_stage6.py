"""Integration tests for Stage 6 Frontend 2D assets and full simulation telemetry."""

import os
from fastapi.testclient import TestClient
from main import app, BASE_DIR
from app.services.scenario_service import ScenarioService


class TestStage6FrontendAndTelemetry:
    def test_index_contains_all_stage6_controls(self):
        with TestClient(app) as client:
            res = client.get("/")
            assert res.status_code == 200
            html = res.text

            required_ids = [
                "statSimClock",
                "badgeGameOutcome",
                "statBudget",
                "statBudgetReserved",
                "btnBuyInfantry",
                "btnBuySniper",
                "btnBuyGunner",
                "soldierRosterList",
                "selectTransportType",
                "selectDestTower",
                "btnDispatchUnits",
                "btnSimStep",
                "btnSimPlay",
                "btnSimReset",
                'data-speed="0.5"',
                'data-speed="1"',
                'data-speed="2"',
                'data-speed="5"',
                "chkShowSurveillanceRanges",
                "chkShowAttackRanges",
                "bridgeStatusList",
                "convoyMachinesList",
                "/static/css/visualizer.css",
                "/static/js/log_viewer.js",
                "/static/js/controls.js",
            ]
            for token in required_ids:
                assert token in html, f"Missing '{token}' in index.html"

    def test_static_css_and_js_modules_served(self):
        with TestClient(app) as client:
            checks = {
                "/static/css/visualizer.css": [".clock-display", ".speed-btn.active", ".bridge-bar"],
                "/static/js/log_viewer.js": ["class LogViewer", "syncBackendEvents"],
                "/static/js/controls.js": ["class SimulationControls", "renderBridgesPanel", "renderSoldierRoster"],
                "/static/js/api.js": ["buySoldier", "dispatchGround", "dispatchAir", "simulationStep", "getSimulationState"],
                "/static/js/renderer_2d.js": [
                    "setFullSimulationState",
                    "drawStationedSoldiers",
                    "drawTransportMissions",
                    "drawCombatEffects",
                ],
                "/static/js/app.js": ["syncFullSimulationState", "btnDispatchUnits", "btnSimPlay"],
            }
            for url, tokens in checks.items():
                r = client.get(url)
                assert r.status_code == 200, f"Failed GET {url}"
                for tok in tokens:
                    assert tok in r.text, f"Missing '{tok}' in {url}"

    def test_simulation_state_includes_corridor_hazards_and_logistics(self):
        scenario_path = os.path.join(BASE_DIR, "data", "scenario_1_basic.json")
        ScenarioService.get_instance().load_from_file(scenario_path)

        with TestClient(app) as client:
            client.post("/api/planning/select-towers", json={"k_towers": 3, "d0_normalization": 50.0})
            reset_res = client.post("/api/simulation/reset")
            assert reset_res.status_code == 200
            data = reset_res.json()

            assert "corridor_hazards" in data
            assert "max_avg_danger" in data
            assert len(data["corridor_hazards"]) > 0
            any_corr = next(iter(data["corridor_hazards"].values()))
            assert "q_ini" in any_corr
            assert "q_mid" in any_corr
            assert "q_end" in any_corr

            assert "budget" in data
            assert "available" in data["budget"]
            assert "reserved" in data["budget"]
            assert "bridges" in data["elevated_network"]
            assert "machines" in data["convoy"]

            step_res = client.post("/api/simulation/step", json={"dt": 1.0})
            assert step_res.status_code == 200
            step_data = step_res.json()
            assert step_data["clock"] == 1.0
            assert "corridor_hazards" in step_data
            assert "x" in step_data["convoy"]
            assert "y" in step_data["convoy"]
