/**
 * REST API client for the defense simulation backend (Stages 1-6).
 */

const API_BASE_URL = window.location.origin;

async function handleApiResponse(res) {
  if (!res.ok) {
    let errText = "";
    try {
      const data = await res.json();
      errText = data.detail || JSON.stringify(data);
    } catch {
      errText = await res.text();
    }
    throw new Error(errText || `Error HTTP ${res.status}`);
  }
  return res.json();
}

const api = {
  async getCurrentScenario() {
    const res = await fetch(`${API_BASE_URL}/api/scenario/current`);
    return handleApiResponse(res);
  },

  async loadDefaultScenario(filename = "scenario_1_basic.json") {
    const res = await fetch(
      `${API_BASE_URL}/api/scenario/load-default?scenario_file=${encodeURIComponent(filename)}`,
      { method: "POST" }
    );
    return handleApiResponse(res);
  },

  async uploadScenarioFile(file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE_URL}/api/scenario/upload`, {
      method: "POST",
      body: formData,
    });
    return handleApiResponse(res);
  },

  async calculateMST() {
    const res = await fetch(`${API_BASE_URL}/api/planning/calculate-mst`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    return handleApiResponse(res);
  },

  async selectTowers(kTowers, d0 = null) {
    const payload = {
      k_towers: parseInt(kTowers, 10),
    };
    if (d0 !== null && d0 !== undefined && !isNaN(d0)) {
      payload.d0_normalization = parseFloat(d0);
    }
    const res = await fetch(`${API_BASE_URL}/api/planning/select-towers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleApiResponse(res);
  },

  // ==========================================
  // Stage 3: Corridor Hazards & Convoy Navigation
  // ==========================================

  async calculateHazards(alpha = 1.0) {
    const res = await fetch(`${API_BASE_URL}/api/simulation/calculate-hazards`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alpha_danger: parseFloat(alpha) }),
    });
    return handleApiResponse(res);
  },

  async calculateCorridorHazards(alpha = 1.0) {
    return this.calculateHazards(alpha);
  },

  async convoyStep(alpha = 1.0) {
    const res = await fetch(`${API_BASE_URL}/api/simulation/convoy/step`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alpha_danger: parseFloat(alpha) }),
    });
    return handleApiResponse(res);
  },

  async convoyRun(alpha = 1.0, maxSteps = 100) {
    const res = await fetch(`${API_BASE_URL}/api/simulation/convoy/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        alpha_danger: parseFloat(alpha),
        max_steps: parseInt(maxSteps, 10),
      }),
    });
    return handleApiResponse(res);
  },

  async convoyReset(alpha = 1.0) {
    const res = await fetch(`${API_BASE_URL}/api/simulation/convoy/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alpha_danger: parseFloat(alpha) }),
    });
    return handleApiResponse(res);
  },

  async convoyStatus() {
    const res = await fetch(`${API_BASE_URL}/api/simulation/convoy/status`);
    return handleApiResponse(res);
  },

  // ==========================================
  // Stage 4 & 5: Logistics & Full Tick Engine
  // ==========================================

  async buySoldier(soldierType, quantity = 1) {
    const res = await fetch(`${API_BASE_URL}/api/logistics/buy-soldier`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        soldier_type: soldierType,
        quantity: parseInt(quantity, 10),
      }),
    });
    return handleApiResponse(res);
  },

  async dispatchGround(transportType, soldierIds, destinationId, originId = null) {
    const payload = {
      transport_type: transportType,
      soldier_ids: soldierIds,
      destination_id: destinationId,
    };
    if (originId) {
      payload.origin_id = originId;
    }
    const res = await fetch(`${API_BASE_URL}/api/logistics/dispatch-ground`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleApiResponse(res);
  },

  async dispatchAir(soldierIds, destinationId, originId = null) {
    const payload = {
      soldier_ids: soldierIds,
      destination_id: destinationId,
    };
    if (originId) {
      payload.origin_id = originId;
    }
    const res = await fetch(`${API_BASE_URL}/api/logistics/dispatch-air`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleApiResponse(res);
  },

  async getLogisticsState() {
    const res = await fetch(`${API_BASE_URL}/api/logistics/state`);
    return handleApiResponse(res);
  },

  async simulationStep(dt = 1.0, alpha = null) {
    const payload = { dt: parseFloat(dt) };
    if (alpha !== null && alpha !== undefined && !isNaN(alpha)) {
      payload.alpha_danger = parseFloat(alpha);
    }
    const res = await fetch(`${API_BASE_URL}/api/simulation/step`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleApiResponse(res);
  },

  async simulationReset(alpha = null) {
    const payload = {};
    if (alpha !== null && alpha !== undefined && !isNaN(alpha)) {
      payload.alpha_danger = parseFloat(alpha);
    }
    const res = await fetch(`${API_BASE_URL}/api/simulation/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleApiResponse(res);
  },

  async getSimulationState() {
    const res = await fetch(`${API_BASE_URL}/api/simulation/state`);
    return handleApiResponse(res);
  },
};

window.api = api;
