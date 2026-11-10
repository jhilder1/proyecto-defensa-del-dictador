/**
 * Main application orchestrator for the visual interface.
 */

document.addEventListener("DOMContentLoaded", async () => {
  const canvas = document.getElementById("simCanvas");
  const renderer = new Renderer2D(canvas);

  // UI Elements
  const scenarioNameEl = document.getElementById("scenarioName");
  const statGeNodesEl = document.getElementById("statGeNodes");
  const statGmCorridorsEl = document.getElementById("statGmCorridors");
  const statActiveTowersEl = document.getElementById("statActiveTowers");
  const statCoverageEl = document.getElementById("statCoverage");
  const statBudgetEl = document.getElementById("statBudget");

  const btnLoadDefault = document.getElementById("btnLoadDefault");
  const fileInput = document.getElementById("fileInput");
  const btnUpload = document.getElementById("btnUpload");

  const btnCalcMst = document.getElementById("btnCalcMst");
  const btnSelectTowers = document.getElementById("btnSelectTowers");
  const inputKTowers = document.getElementById("inputKTowers");
  const inputD0 = document.getElementById("inputD0");

  const logViewer = document.getElementById("logViewer");
  const btnClearLog = document.getElementById("btnClearLog");

  let currentScenario = null;
  let currentMst = null;
  let currentTowerSelection = null;

  function appendLog(tag, message, type = "info") {
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className = "log-entry";

    let tagClass = "log-tag-info";
    if (tag === "MST") tagClass = "log-tag-mst";
    if (tag === "TORRE") tagClass = "log-tag-tower";

    entry.innerHTML = `
      <span class="log-time">[${time}]</span>
      <span class="${tagClass}">[${tag}]</span>
      <span class="log-msg">${message}</span>
    `;
    logViewer.appendChild(entry);
    logViewer.scrollTop = logViewer.scrollHeight;
  }

  function updateStats() {
    if (!currentScenario) return;

    scenarioNameEl.textContent = currentScenario.scenario_name || "Escenario cargado";
    statGeNodesEl.textContent = currentScenario.elevated_network?.nodes?.length || 0;
    statGmCorridorsEl.textContent = currentScenario.maze_network?.corridors?.length || 0;
    statBudgetEl.textContent = `$${currentScenario.config?.initial_budget || 0}`;

    const towersCount = currentTowerSelection?.towers_selected_count || 0;
    statActiveTowersEl.textContent = towersCount;

    const coverage = currentTowerSelection?.coverage_percentage !== undefined
      ? `${currentTowerSelection.coverage_percentage}%`
      : "0%";
    statCoverageEl.textContent = coverage;
  }

  async function refreshScenario() {
    try {
      currentScenario = await window.api.getCurrentScenario();
      currentMst = currentScenario.mst_result;
      currentTowerSelection = currentScenario.tower_selection_result;

      renderer.setData(currentScenario, currentMst, currentTowerSelection);
      updateStats();
      appendLog("ESCENARIO", `Escenario '${currentScenario.scenario_name}' sincronizado.`);
    } catch (err) {
      appendLog("ERROR", `Error cargando escenario: ${err.message}`);
    }
  }

  // Event Listeners
  btnLoadDefault.addEventListener("click", async () => {
    try {
      appendLog("CARGA", "Cargando escenario básico pedagógico...");
      currentScenario = await window.api.loadDefaultScenario("scenario_1_basic.json");
      currentMst = null;
      currentTowerSelection = null;
      renderer.setData(currentScenario, null, null);
      updateStats();
      appendLog("CARGA", "Escenario básico cargado correctamente.");
    } catch (err) {
      appendLog("ERROR", `Error al cargar escenario por defecto: ${err.message}`);
    }
  });

  btnUpload.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      appendLog("CARGA", `Subiendo archivo: ${file.name}...`);
      currentScenario = await window.api.uploadScenarioFile(file);
      currentMst = null;
      currentTowerSelection = null;
      renderer.setData(currentScenario, null, null);
      updateStats();
      appendLog("CARGA", `Escenario '${currentScenario.scenario_name}' cargado con éxito.`);
    } catch (err) {
      appendLog("ERROR", `Error subiendo escenario: ${err.message}`);
    }
  });

  btnCalcMst.addEventListener("click", async () => {
    try {
      appendLog("MST", "Calculando Árbol Generador Mínimo (Kruskal) sobre la componente de la Base...");
      const res = await window.api.calculateMST();
      currentMst = res;

      renderer.setData(currentScenario, currentMst, currentTowerSelection);

      appendLog("MST", `MST completado: ${res.mst_edges.length} aristas seleccionadas. Costo total: ${res.total_cost}s a pie.`);
      for (const step of res.steps) {
        if (step.action === "added") {
          appendLog("MST", `+ Arista ${step.u} ↔ ${step.v} (peso ${step.weight}s) agregada a T_E`);
        } else if (step.action === "rejected") {
          appendLog("MST", `- Arista ${step.u} ↔ ${step.v} (peso ${step.weight}s) descartada (${step.reason})`);
        }
      }
    } catch (err) {
      appendLog("ERROR", `Error en cálculo de MST: ${err.message}`);
    }
  });

  btnSelectTowers.addEventListener("click", async () => {
    try {
      const k = parseInt(inputKTowers.value, 10) || 3;
      const d0 = parseFloat(inputD0.value) || 50.0;

      appendLog("TORRE", `Iniciando selección voraz con K=${k}, D_0=${d0}...`);
      const res = await window.api.selectTowers(k, d0);
      currentTowerSelection = res;

      // Also ensure MST is displayed if it was triggered
      if (!currentMst) {
        currentScenario = await window.api.getCurrentScenario();
        currentMst = currentScenario.mst_result;
      }

      renderer.setData(currentScenario, currentMst, currentTowerSelection);
      updateStats();

      appendLog("TORRE", `Selección finalizada: ${res.towers_selected_count} torres activadas. Cobertura: ${res.coverage_percentage}%.`);

      for (const step of res.history) {
        appendLog("TORRE", `Iteración #${step.iteration}: Seleccionada Torre '${step.selected_tower_id}' con puntuación S(p)=${step.score}. Cubre ${step.new_corridors_covered} nuevo(s) corredor(es). Restan ${step.unwatched_remaining} por vigilar.`);
      }
    } catch (err) {
      appendLog("ERROR", `Error en selección voraz: ${err.message}`);
    }
  });

  btnClearLog.addEventListener("click", () => {
    logViewer.innerHTML = "";
  });

  // Initial load
  await refreshScenario();
});

