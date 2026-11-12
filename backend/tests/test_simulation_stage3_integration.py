"""Integration tests for Stage 3 Simulation and REST API endpoints (Requirement F10, R6).

Verifies:
- POST /api/simulation/calculate-hazards
- POST /api/simulation/convoy/step
- POST /api/simulation/convoy/run
- POST /api/simulation/convoy/reset
- GET /api/simulation/convoy/status
- Convoy health depletion and state progression over Scenario 1
"""

import os
import pytest
from fastapi.testclient import TestClient
from main import app, BASE_DIR
from app.services.scenario_service import ScenarioService
from app.services.hazard_service import HazardService
from app.domain.soldier import DefenseUnit, SoldierType


@pytest.fixture(autouse=True)
def reload_default_scenario():
    """Ensure clean default scenario before each test."""
    scenario_path = os.path.join(BASE_DIR, "data", "scenario_1_basic.json")
    ScenarioService.get_instance().load_from_file(scenario_path)
    # Reset simulation
    client = TestClient(app)
    client.post("/api/simulation/convoy/reset")


class TestSimulationApiEndpoints:
    def test_calculate_hazards_endpoint_default(self):
        """Tests POST /api/simulation/calculate-hazards."""
        client = TestClient(app)
        response = client.post("/api/simulation/calculate-hazards", json={"alpha_danger": 1.5})
        assert response.status_code == 200
        data = response.json()

        assert "alpha_danger" in data
        assert data["alpha_danger"] == 1.5
        assert "corridor_hazards" in data
        assert "IN-M1" in data["corridor_hazards"] or "M1-IN" in data["corridor_hazards"]

        # Check corridor data structure
        any_corr = next(iter(data["corridor_hazards"].values()))
        assert "base_time" in any_corr
        assert "avg_danger" in any_corr
        assert "danger_potential" in any_corr
        assert "reactive_weight" in any_corr
        assert "q_ini" in any_corr
        assert "q_mid" in any_corr
        assert "q_end" in any_corr

    def test_calculate_hazards_with_query_param(self):
        """Tests POST /api/simulation/calculate-hazards?alpha=2.0."""
        client = TestClient(app)
        response = client.post("/api/simulation/calculate-hazards?alpha=2.0")
        assert response.status_code == 200
        data = response.json()
        assert data["alpha_danger"] == 2.0

    def test_convoy_step_progression(self):
        """Tests POST /api/simulation/convoy/step advances convoy node-to-node."""
        client = TestClient(app)

        # Reset convoy
        reset_res = client.post("/api/simulation/convoy/reset")
        assert reset_res.status_code == 200
        assert reset_res.json()["current_node"] == "IN"

        # Step 1: from IN to M1
        step1 = client.post("/api/simulation/convoy/step", json={"alpha_danger": 1.0})
        assert step1.status_code == 200
        data1 = step1.json()

        assert data1["step_index"] == 1
        assert data1["current_node"] == "M1"
        assert data1["previous_node"] == "IN"
        assert "IN" in data1["path_taken"]
        assert "M1" in data1["path_taken"]
        assert data1["is_finished"] is False

        # Step 2: from M1 towards exit (must NOT backtrack to IN!)
        step2 = client.post("/api/simulation/convoy/step", json={"alpha_danger": 1.0})
        assert step2.status_code == 200
        data2 = step2.json()

        assert data2["step_index"] == 2
        assert data2["previous_node"] == "M1"
        assert data2["current_node"] != "IN", "Convoy must not backtrack to IN!"
        assert data2["current_node"] in ["M2", "M4"]

    def test_convoy_run_full_simulation(self):
        """Tests POST /api/simulation/convoy/run executes entire journey."""
        client = TestClient(app)
        client.post("/api/simulation/convoy/reset")

        response = client.post("/api/simulation/convoy/run", json={"alpha_danger": 1.0, "max_steps": 20})
        assert response.status_code == 200
        data = response.json()

        assert data["total_steps"] > 0
        assert data["is_finished"] is True
        assert data["escaped"] or data["destroyed"]
        assert data["path_taken"][0] == "IN"
        if data["escaped"]:
            assert data["current_node"] == "OUT"

    def test_convoy_reset_restores_state(self):
        """Tests POST /api/simulation/convoy/reset restores health and position."""
        client = TestClient(app)

        # Advance 2 steps
        client.post("/api/simulation/convoy/step")
        client.post("/api/simulation/convoy/step")

        # Now reset
        res = client.post("/api/simulation/convoy/reset")
        assert res.status_code == 200
        data = res.json()

        assert data["current_node"] == "IN"
        assert data["previous_node"] is None
        assert data["hp"] == data["max_hp"]
        assert data["path_taken"] == ["IN"]
        assert data["is_finished"] is False

    def test_convoy_status_endpoint(self):
        """Tests GET /api/simulation/convoy/status."""
        client = TestClient(app)
        res = client.get("/api/simulation/convoy/status")
        assert res.status_code == 200
        data = res.json()

        assert "current_node" in data
        assert "hp" in data
        assert "max_hp" in data
        assert "convoy_status" in data

    def test_convoy_takes_damage_from_corridor_hazard(self):
        """Tests that moving through a hazardous corridor reduces convoy HP."""
        client = TestClient(app)
        hazard_srv = HazardService.get_instance()

        # Place deadly defense covering corridor IN-M1 (x=100 to x=220, y=380)
        # Defense at (160, 380) with huge effective range and sniper damage
        deadly_unit = DefenseUnit(SoldierType.SNIPER, x=160.0, y=380.0, effective_range=100.0, unit_id="deadly_snip")
        hazard_srv.set_custom_defenses([deadly_unit])

        # Reset convoy
        reset_res = client.post("/api/simulation/convoy/reset")
        initial_hp = reset_res.json()["hp"]
        assert initial_hp > 0

        # Step through IN -> M1
        step_res = client.post("/api/simulation/convoy/step")
        assert step_res.status_code == 200
        step_data = step_res.json()

        # Reset custom defenses
        hazard_srv.set_custom_defenses(None)

        # Convoy should have taken damage
        assert step_data["hp"] < initial_hp
        assert step_data["history"]["total_damage_taken"] > 0

    def test_frontend_static_assets_serving(self):
        """Tests that FastAPI serves the Stage 3 frontend index and static JS/CSS files."""
        client = TestClient(app)

        # 1. Index route
        index_res = client.get("/")
        assert index_res.status_code == 200
        html_content = index_res.text
        assert "Simulación de Defensa Estratégica" in html_content
        assert "panelStage3" in html_content
        assert "btnConvoyStep" in html_content
        assert "inputAlphaDanger" in html_content
        assert "btnCalcHazards" in html_content

        # 2. Static CSS
        css_res = client.get("/static/css/style.css")
        assert css_res.status_code == 200
        assert "--accent-purple" in css_res.text
        assert "log-tag-antibacktrack" in css_res.text

        # 3. Static JS: api.js
        api_res = client.get("/static/js/api.js")
        assert api_res.status_code == 200
        assert "calculateHazards" in api_res.text
        assert "convoyStep" in api_res.text

        # 4. Static JS: renderer_2d.js
        rend_res = client.get("/static/js/renderer_2d.js")
        assert rend_res.status_code == 200
        assert "drawConvoyTrail" in rend_res.text
        assert "drawConvoyToken" in rend_res.text
        assert "drawAntiBacktracking" in rend_res.text

        # 5. Static JS: app.js
        app_res = client.get("/static/js/app.js")
        assert app_res.status_code == 200
        assert "btnConvoyStep" in app_res.text
        assert "updateConvoyStats" in app_res.text
