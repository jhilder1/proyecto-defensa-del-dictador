/**
 * REST API client for the defense simulation backend.
 */

const API_BASE_URL = window.location.origin;

const api = {
  async getCurrentScenario() {
    const res = await fetch(`${API_BASE_URL}/api/scenario/current`);
    if (!res.ok) {
      throw new Error(`Error ${res.status}: ${await res.text()}`);
    }
    return res.json();
  },

  async loadDefaultScenario(filename = "scenario_1_basic.json") {
    const res = await fetch(`${API_BASE_URL}/api/scenario/load-default?scenario_file=${encodeURIComponent(filename)}`, {
      method: "POST",
    });
    if (!res.ok) {
      throw new Error(`Error ${res.status}: ${await res.text()}`);
    }
    return res.json();
  },

  async uploadScenarioFile(file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE_URL}/api/scenario/upload`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      throw new Error(`Error ${res.status}: ${await res.text()}`);
    }
    return res.json();
  },

  async calculateMST() {
    const res = await fetch(`${API_BASE_URL}/api/planning/calculate-mst`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) {
      throw new Error(`Error ${res.status}: ${await res.text()}`);
    }
    return res.json();
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
    if (!res.ok) {
      throw new Error(`Error ${res.status}: ${await res.text()}`);
    }
    return res.json();
  },
};

window.api = api;

