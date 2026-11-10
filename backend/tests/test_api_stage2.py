"""Integration tests for Stage 2 REST endpoints."""

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_get_current_scenario_on_startup(client):
    response = client.get("/api/scenario/current")
    assert response.status_code == 200
    data = response.json()
    assert "scenario_name" in data
    assert len(data["elevated_network"]["nodes"]) > 0
    assert len(data["maze_network"]["corridors"]) > 0


def test_calculate_mst_endpoint(client):
    response = client.post("/api/planning/calculate-mst")
    assert response.status_code == 200
    data = response.json()
    assert "mst_edges" in data
    assert "total_cost" in data
    assert "tree_distances" in data
    assert data["total_cost"] > 0
    assert "Base" in data["tree_distances"]


def test_select_towers_endpoint(client):
    response = client.post("/api/planning/select-towers", json={"k_towers": 2, "d0_normalization": 50.0})
    assert response.status_code == 200
    data = response.json()
    assert "selected_towers" in data
    assert len(data["selected_towers"]) <= 2
    assert "watched_corridors" in data
    assert data["coverage_percentage"] > 0
