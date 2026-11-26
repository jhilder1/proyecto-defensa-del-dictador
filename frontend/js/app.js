/**
 * Main application orchestrator for the 2D Defense Simulation frontend (Stages 1-6).
 */

document.addEventListener("DOMContentLoaded", async () => {
  const canvas = document.getElementById("simCanvas");
  const renderer = new Renderer2D(canvas);

  // Header & Toolbar Elements
  const scenarioNameEl = document.getElementById("scenarioName");
  const statSimClockEl = document.getElementById("statSimClock");
  const badgeGameOutcomeEl = document.getElementById("badgeGameOutcome");
  const statGeNodesEl = document.getElementById("statGeNodes");
  const statGmCorridorsEl = document.getElementById("statGmCorridors");
  const statActiveTowersEl = document.getElementById("statActiveTowers");
  const statCoverageEl = document.getElementById("statCoverage");
  const statBudgetEl = document.getElementById("statBudget");
  const statBudgetReservedEl = document.getElementById("statBudgetReserved");

  // Stage 1 & 2 Controls
  const btnLoadDefault = document.getElementById("btnLoadDefault");
  const btnLoadComplex = document.getElementById("btnLoadComplex");
  const fileInput = document.getElementById("fileInput");
  const btnUpload = document.getElementById("btnUpload");
  const btnCalcMst = document.getElementById("btnCalcMst");
  const btnSelectTowers = document.getElementById("btnSelectTowers");
  const inputKTowers = document.getElementById("inputKTowers");
  const inputD0 = document.getElementById("inputD0");

  // Stage 4 Logistics Controls
  const btnBuyInfantry = document.getElementById("btnBuyInfantry");
  const btnBuySniper = document.getElementById("btnBuySniper");
  const btnBuyGunner = document.getElementById("btnBuyGunner");
  const soldierRosterListEl = document.getElementById("soldierRosterList");
  const rosterSummaryTextEl = document.getElementById("rosterSummaryText");
  const statHeliUsesEl = document.getElementById("statHeliUses");
  const statRepairPersonnelEl = document.getElementById("statRepairPersonnel");
  const selectOriginNode = document.getElementById("selectOriginNode");
  const selectTransportType = document.getElementById("selectTransportType");
  const selectDestTower = document.getElementById("selectDestTower");
  const btnDispatchUnits = document.getElementById("btnDispatchUnits");
  const bridgeStatusListEl = document.getElementById("bridgeStatusList");
  const convoyMachinesListEl = document.getElementById("convoyMachinesList");

  // Stage 5 & 6 Tick Controls
  const btnSimStep = document.getElementById("btnSimStep");
  const btnSimPlay = document.getElementById("btnSimPlay");
  const btnSimReset = document.getElementById("btnSimReset");
  const labelSpeedActiveEl = document.getElementById("labelSpeedActive");
  const speedButtons = document.querySelectorAll(".speed-btn");
  const chkShowSurveillanceRanges = document.getElementById("chkShowSurveillanceRanges");
  const chkShowAttackRanges = document.getElementById("chkShowAttackRanges");
  const btnResetView = document.getElementById("btnResetView");
  const chkShowEdgeLabels = document.getElementById("chkShowEdgeLabels");
  const btnToggleLegend = document.getElementById("btnToggleLegend");
  const legendBox = document.getElementById("legendBox");

  // Stage 3 Reactive Convoy Elements
  const statConvoyPosEl = document.getElementById("statConvoyPos");
  const statConvoyHpEl = document.getElementById("statConvoyHp");
  const statConvoyDamageEl = document.getElementById("statConvoyDamage");
  const statAntiBacktracksEl = document.getElementById("statAntiBacktracks");
  const badgeConvoyStatusEl = document.getElementById("badgeConvoyStatus");

  const inputAlphaDanger = document.getElementById("inputAlphaDanger");
  const labelAlphaValue = document.getElementById("labelAlphaValue");
  const btnCalcHazards = document.getElementById("btnCalcHazards");
  const btnConvoyStep = document.getElementById("btnConvoyStep");
  const btnConvoyPlay = document.getElementById("btnConvoyPlay");
  const btnConvoyRunAll = document.getElementById("btnConvoyRunAll");
  const btnConvoyReset = document.getElementById("btnConvoyReset");
  const chkShowHeatmap = document.getElementById("chkShowHeatmap");
  const chkShowEvalPoints = document.getElementById("chkShowEvalPoints");

  // Log Viewer
  const logViewerEl = document.getElementById("logViewer");
  const btnClearLog = document.getElementById("btnClearLog");
  const logViewer = new window.LogViewer(logViewerEl, btnClearLog);

  // Application State
  let currentScenario = null;
  let currentMst = null;
  let currentTowerSelection = null;
  let currentConvoyState = null;
  let currentFullState = null;
  const selectedSoldierIds = new Set();

  let legacyPlayInterval = null;
  let isLegacyPlaying = false;

  function appendLog(tag, message) {
    logViewer.append(tag, message);
  }

  function updateStats() {
    if (!currentScenario) return;

    scenarioNameEl.textContent = currentScenario.scenario_name || "Escenario cargado";
    statGeNodesEl.textContent = currentScenario.elevated_network?.nodes?.length || 0;
    statGmCorridorsEl.textContent = currentScenario.maze_network?.corridors?.length || 0;

    if (!currentFullState) {
      statBudgetEl.textContent = `$${currentScenario.config?.budget_available ?? currentScenario.config?.initial_budget ?? 0}`;
      statBudgetReservedEl.textContent = `$${currentScenario.config?.budget_reserved ?? 0}`;
    }

    const towersCount = currentTowerSelection?.towers_selected_count || 0;
    statActiveTowersEl.textContent = towersCount;

    const coverage =
      currentTowerSelection?.coverage_percentage !== undefined
        ? `${currentTowerSelection.coverage_percentage}%`
        : "0%";
    statCoverageEl.textContent = coverage;
  }

  function updateConvoyStats(state) {
    if (!state) return;

    if (statConvoyPosEl) {
      statConvoyPosEl.textContent = state.current_node || "IN";
    }

    const hp = state.hp !== undefined ? state.hp : state.convoy_status?.total_hp || 0;
    const maxHp = state.max_hp !== undefined ? state.max_hp : state.convoy_status?.max_total_hp || 350;
    const ratio = maxHp > 0 ? hp / maxHp : 0;
    const pct = Math.round(ratio * 100);

    if (statConvoyHpEl) {
      statConvoyHpEl.textContent = `${pct}% (${Math.round(hp)}/${Math.round(maxHp)})`;
      statConvoyHpEl.style.color =
        ratio > 0.5 ? "var(--accent-green)" : ratio > 0.25 ? "var(--accent-yellow)" : "var(--accent-red)";
    }

    const damage =
      state.history?.total_damage_taken !== undefined
        ? state.history.total_damage_taken
        : Math.max(0, maxHp - hp);
    if (statConvoyDamageEl) {
      statConvoyDamageEl.textContent = `${Math.round(damage)} HP`;
    }

    const backtracks =
      state.backtracks_prevented !== undefined ? state.backtracks_prevented : state.backtrack_count || 0;
    if (statAntiBacktracksEl) {
      statAntiBacktracksEl.textContent = backtracks;
    }

    if (badgeConvoyStatusEl) {
      if (state.is_finished) {
        if (state.escaped) {
          badgeConvoyStatusEl.className = "badge badge-success";
          badgeConvoyStatusEl.textContent = "Escapó";
        } else if (state.destroyed) {
          badgeConvoyStatusEl.className = "badge badge-danger";
          badgeConvoyStatusEl.textContent = "Destruido";
        } else {
          badgeConvoyStatusEl.className = "badge badge-warning";
          badgeConvoyStatusEl.textContent = "Finalizado";
        }
      } else if (state.step_index > 0 || state.current_edge) {
        badgeConvoyStatusEl.className = "badge badge-purple";
        badgeConvoyStatusEl.textContent = "En Marcha";
      } else {
        badgeConvoyStatusEl.className = "badge badge-purple";
        badgeConvoyStatusEl.textContent = "En Espera";
      }
    }
  }

  function syncFullSimulationState(fullState) {
    if (!fullState) return;
    currentFullState = fullState;

    // 1. Clock & Outcome HUD
    if (statSimClockEl) {
      const limit = fullState.max_time_limit ?? 300;
      statSimClockEl.textContent = `⏱ ${Number(fullState.clock || 0).toFixed(1)}s / ${limit}s`;
    }

    if (badgeGameOutcomeEl) {
      badgeGameOutcomeEl.textContent = fullState.game_result || "En preparación";
      badgeGameOutcomeEl.className = "outcome-banner";
      if (fullState.is_game_over) {
        if (fullState.game_result === "Derrota") {
          badgeGameOutcomeEl.classList.add("outcome-defeat");
        } else {
          badgeGameOutcomeEl.classList.add("outcome-victory");
        }
      } else if (fullState.is_running) {
        badgeGameOutcomeEl.classList.add("outcome-running");
      }
    }

    // 2. Budget Split, Helicopter Uses, Repair Personnel
    if (fullState.budget) {
      statBudgetEl.textContent = `$${fullState.budget.available}`;
      statBudgetReservedEl.textContent = `$${fullState.budget.reserved}`;
    }
    if (statHeliUsesEl && fullState.helicopter) {
      statHeliUsesEl.textContent = `${fullState.helicopter.remaining_uses}/${fullState.helicopter.max_uses} (flota ${fullState.helicopter.available_fleet}/${fullState.helicopter.fleet_size})`;
    }
    if (statRepairPersonnelEl && fullState.personnel) {
      statRepairPersonnelEl.textContent = `${fullState.personnel.available}/${fullState.personnel.total}`;
    }

    // 3. Logistics Origin, Roster, Destination Towers, Bridges, Convoy Machines
    window.SimulationControls.renderOriginSelector(
      fullState.elevated_network?.nodes || [],
      selectOriginNode
    );
    window.SimulationControls.renderSoldierRoster(
      fullState.soldiers || [],
      soldierRosterListEl,
      selectedSoldierIds,
      rosterSummaryTextEl,
      selectOriginNode ? selectOriginNode.value : ""
    );
    window.SimulationControls.renderDestinationTowers(
      fullState.elevated_network?.nodes || [],
      selectDestTower
    );
    window.SimulationControls.renderBridgesPanel(
      fullState.elevated_network?.bridges || [],
      bridgeStatusListEl
    );
    window.SimulationControls.renderConvoyMachines(
      fullState.convoy?.machines || [],
      convoyMachinesListEl
    );

    if (statActiveTowersEl && fullState.elevated_network?.active_towers) {
      statActiveTowersEl.textContent = fullState.elevated_network.active_towers.length;
    }

    // 4. Canvas Renderer & Convoy Stats
    renderer.setFullSimulationState(fullState);
    if (fullState.convoy) {
      updateConvoyStats({
        current_node: fullState.convoy.current_node,
        current_edge: fullState.convoy.current_edge,
        hp: fullState.convoy.hp,
        max_hp: fullState.convoy.max_hp,
        backtracks_prevented: fullState.convoy.backtracks_prevented,
        is_finished: fullState.is_game_over,
        escaped: fullState.convoy.escaped,
        destroyed: fullState.convoy.destroyed,
        step_index: (fullState.convoy.path_taken?.length || 1) - 1,
      });
    }

    // 5. Sync Audit Log Events
    logViewer.syncBackendEvents(fullState.event_log);
  }

  function updateSimPlayButton(playing) {
    if (!btnSimPlay) return;
    btnSimPlay.innerHTML = playing ? "<span>⏸</span> Pausar" : "<span>▶</span> Play";
  }

  async function executeSimulationTick() {
    try {
      const alpha = parseFloat(inputAlphaDanger.value);
      const state = await window.api.simulationStep(1.0, alpha);
      syncFullSimulationState(state);

      if (state.is_game_over) {
        tickControls.pause();
        updateSimPlayButton(false);
        return false;
      }
      return true;
    } catch (err) {
      tickControls.pause();
      updateSimPlayButton(false);
      appendLog("ERROR", `Error en tick de simulación: ${err.message}`);
      return false;
    }
  }

  const tickControls = new window.SimulationControls(executeSimulationTick);

  function stopAutoPlay() {
    if (legacyPlayInterval) {
      clearInterval(legacyPlayInterval);
      legacyPlayInterval = null;
    }
    isLegacyPlaying = false;
    if (btnConvoyPlay) {
      btnConvoyPlay.innerHTML = '<span id="playIcon">▶</span> Marcha';
    }
  }

  async function executeStep() {
    const alpha = parseFloat(inputAlphaDanger.value);
    const res = await window.api.convoyStep(alpha);
    currentConvoyState = res;
    renderer.setConvoyState(res);
    updateConvoyStats(res);

    const dec = res.decision || {};
    if (dec.type === "ANTI_BACKTRACK_AVOIDED") {
      appendLog(
        "ANTI-RETROCESO",
        `⛔ Regla activada en nodo '${res.previous_node}': se descartó regreso a '${dec.discarded_node}'. Desvío tomado hacia '${res.current_node}' (${dec.projected_path?.join(" ➔ ")}).`
      );
    } else if (dec.type === "FORCED_DEAD_END_BACKTRACK") {
      appendLog(
        "ALERTA",
        `🛑 Callejón sin salida en '${res.previous_node}'. Retroceso forzado hacia '${res.current_node}'.`
      );
    } else if (dec.type === "OPTIMAL") {
      appendLog(
        "CONVOY",
        `Paso #${res.step_index}: Convoy avanzó de '${res.previous_node}' a '${res.current_node}'. Ruta proyectada: ${dec.projected_path?.join(" ➔ ")} (w: ${res.dijkstra?.raw_cost}s).`
      );
    }

    if (res.is_finished) {
      stopAutoPlay();
      if (res.escaped) {
        appendLog("DERROTA", `💀 El convoy escapó por '${res.target_node}'.`);
      } else if (res.destroyed) {
        appendLog("VICTORIA", `💥 ¡Convoy completamente destruido!`);
      }
    }
    return res;
  }

  async function syncStateFromBackend() {
    const fullState = await window.api.getSimulationState();
    syncFullSimulationState(fullState);
  }

  async function refreshScenario() {
    try {
      currentScenario = await window.api.getCurrentScenario();
      currentMst = currentScenario.mst_result;
      currentTowerSelection = currentScenario.tower_selection_result;

      renderer.setData(currentScenario, currentMst, currentTowerSelection);
      updateStats();
      appendLog("ESCENARIO", `Escenario '${currentScenario.scenario_name}' sincronizado.`);

      const alpha = parseFloat(inputAlphaDanger.value) || 1.0;
      const resetState = await window.api.simulationReset(alpha);
      logViewer.resetSync();
      syncFullSimulationState(resetState);
    } catch (err) {
      appendLog("ERROR", `Error cargando escenario: ${err.message}`);
    }
  }

  // ==========================================
  // Event Listeners - Stage 1 & 2
  // ==========================================

  async function loadPresetScenario(filename, label) {
    try {
      stopAutoPlay();
      tickControls.pause();
      updateSimPlayButton(false);
      appendLog("ESCENARIO", `Cargando ${label}...`);
      currentScenario = await window.api.loadDefaultScenario(filename);
      currentMst = null;
      currentTowerSelection = null;
      renderer.setData(currentScenario, null, null);
      updateStats();

      const alpha = parseFloat(inputAlphaDanger.value) || 1.0;
      const resetState = await window.api.simulationReset(alpha);
      logViewer.resetSync();
      syncFullSimulationState(resetState);
      appendLog("ESCENARIO", `${label} cargado correctamente.`);
    } catch (err) {
      appendLog("ERROR", `Error al cargar ${label}: ${err.message}`);
    }
  }

  btnLoadDefault.addEventListener("click", () => loadPresetScenario("scenario_1_basic.json", "Escenario Básico (1)"));
  if (btnLoadComplex) {
    btnLoadComplex.addEventListener("click", () => loadPresetScenario("scenario_2_complex.json", "Escenario Complejo (2)"));
  }

  btnUpload.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      stopAutoPlay();
      tickControls.pause();
      updateSimPlayButton(false);
      appendLog("ESCENARIO", `Subiendo archivo: ${file.name}...`);
      currentScenario = await window.api.uploadScenarioFile(file);
      currentMst = null;
      currentTowerSelection = null;
      renderer.setData(currentScenario, null, null);
      updateStats();

      const alpha = parseFloat(inputAlphaDanger.value) || 1.0;
      const resetState = await window.api.simulationReset(alpha);
      logViewer.resetSync();
      syncFullSimulationState(resetState);
      appendLog("ESCENARIO", `Escenario '${currentScenario.scenario_name}' cargado con éxito.`);
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

      if (!currentMst) {
        currentScenario = await window.api.getCurrentScenario();
        currentMst = currentScenario.mst_result;
      }

      renderer.setData(currentScenario, currentMst, currentTowerSelection);
      updateStats();

      appendLog("TORRE", `Selección finalizada: ${res.towers_selected_count} torres activadas. Cobertura: ${res.coverage_percentage}%.`);
      for (const step of res.history) {
        appendLog(
          "TORRE",
          `Iteración #${step.iteration}: Torre '${step.selected_tower_id}' (S(p)=${step.score}, cubrió ${step.new_corridors_covered} tramo(s)).`
        );
      }

      await syncStateFromBackend();
    } catch (err) {
      appendLog("ERROR", `Error en selección voraz: ${err.message}`);
    }
  });

  // ==========================================
  // Event Listeners - Stage 4 Logistics
  // ==========================================

  async function handleBuySoldier(soldierType) {
    try {
      const res = await window.api.buySoldier(soldierType, 1);
      for (const s of res.purchased || []) {
        selectedSoldierIds.add(s.id);
      }
      await syncStateFromBackend();
    } catch (err) {
      appendLog("ERROR", `Compra rechazada: ${err.message}`);
    }
  }

  btnBuyInfantry.addEventListener("click", () => handleBuySoldier("Infantería"));
  btnBuySniper.addEventListener("click", () => handleBuySoldier("Francotirador"));
  btnBuyGunner.addEventListener("click", () => handleBuySoldier("Artillero"));

  if (selectOriginNode) {
    selectOriginNode.addEventListener("change", () => {
      selectedSoldierIds.clear();
      if (currentFullState) {
        window.SimulationControls.renderSoldierRoster(
          currentFullState.soldiers || [],
          soldierRosterListEl,
          selectedSoldierIds,
          rosterSummaryTextEl,
          selectOriginNode.value
        );
      }
    });
  }

  btnDispatchUnits.addEventListener("click", async () => {
    try {
      const originId = selectOriginNode ? selectOriginNode.value : "";
      const transportType = selectTransportType.value;
      const destinationId = selectDestTower.value;
      if (!destinationId) {
        appendLog("ALERTA", "Selecciona o activa primero una torre destino.");
        return;
      }

      let idsToSend = Array.from(selectedSoldierIds);
      if (idsToSend.length === 0) {
        const pool = originId
          ? (currentFullState?.soldiers || []).filter((s) => s.status === "apostado" && s.location_node_id === originId)
          : (currentFullState?.soldiers || []).filter((s) => s.status === "en_base");
        const maxCap = transportType === "A pie" ? 1 : transportType === "Moto" ? 2 : 4;
        idsToSend = pool.slice(0, maxCap).map((s) => s.id);
      }

      if (idsToSend.length === 0) {
        appendLog("ALERTA", "No hay soldados disponibles en el origen seleccionado para despachar.");
        return;
      }

      if (transportType === "Helicóptero") {
        await window.api.dispatchAir(idsToSend, destinationId, originId || null);
      } else {
        await window.api.dispatchGround(transportType, idsToSend, destinationId, originId || null);
      }

      idsToSend.forEach((id) => selectedSoldierIds.delete(id));
      await syncStateFromBackend();
    } catch (err) {
      appendLog("ERROR", `Despacho rechazado: ${err.message}`);
    }
  });

  // ==========================================
  // Event Listeners - Stage 5 & 6 Tick Controls
  // ==========================================

  btnSimStep.addEventListener("click", async () => {
    tickControls.pause();
    updateSimPlayButton(false);
    await executeSimulationTick();
  });

  btnSimPlay.addEventListener("click", () => {
    if (currentFullState?.is_game_over) {
      appendLog("ALERTA", "La simulación ya terminó. Pulsa 'Reiniciar Simulación Completa' para volver a jugar.");
      return;
    }
    const playing = tickControls.toggle();
    updateSimPlayButton(playing);
    appendLog("INFO", playing ? `Simulación iniciada a velocidad ${tickControls.speedMultiplier}x.` : "Simulación pausada.");
  });

  btnSimReset.addEventListener("click", async () => {
    try {
      stopAutoPlay();
      tickControls.pause();
      updateSimPlayButton(false);
      selectedSoldierIds.clear();

      const alpha = parseFloat(inputAlphaDanger.value);
      const resetState = await window.api.simulationReset(alpha);
      logViewer.resetSync();
      syncFullSimulationState(resetState);
      appendLog("INFO", "Simulación reiniciada por completo (reloj, presupuesto, puentes, tropas y convoy).");
    } catch (err) {
      appendLog("ERROR", `Error al reiniciar simulación: ${err.message}`);
    }
  });

  speedButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      speedButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const speed = parseFloat(btn.dataset.speed);
      tickControls.setSpeed(speed);
      if (labelSpeedActiveEl) {
        labelSpeedActiveEl.textContent = `${speed}x`;
      }
    });
  });

  if (chkShowSurveillanceRanges) {
    chkShowSurveillanceRanges.addEventListener("change", (e) => {
      renderer.showSurveillanceRanges = e.target.checked;
      renderer.render();
    });
  }

  if (chkShowAttackRanges) {
    chkShowAttackRanges.addEventListener("change", (e) => {
      renderer.showAttackRanges = e.target.checked;
      renderer.render();
    });
  }

  if (btnResetView) {
    btnResetView.addEventListener("click", () => renderer.resetView());
  }

  if (chkShowEdgeLabels) {
    chkShowEdgeLabels.addEventListener("change", (e) => {
      renderer.showEdgeLabels = e.target.checked;
      renderer.render();
    });
  }

  if (btnToggleLegend && legendBox) {
    btnToggleLegend.addEventListener("click", () => {
      legendBox.classList.toggle("collapsed");
    });
  }

  // ==========================================
  // Event Listeners - Stage 3 Reactive Controls
  // ==========================================

  inputAlphaDanger.addEventListener("input", (e) => {
    labelAlphaValue.textContent = parseFloat(e.target.value).toFixed(1);
  });

  if (chkShowHeatmap) {
    chkShowHeatmap.addEventListener("change", (e) => {
      renderer.showHeatmap = e.target.checked;
      renderer.render();
    });
  }

  if (chkShowEvalPoints) {
    chkShowEvalPoints.addEventListener("change", (e) => {
      renderer.showEvalPoints = e.target.checked;
      renderer.render();
    });
  }

  btnCalcHazards.addEventListener("click", async () => {
    try {
      const alpha = parseFloat(inputAlphaDanger.value);
      appendLog("PELIGRO", `Calculando peligros en corredores G_M con α=${alpha}...`);
      const hazards = await window.api.calculateHazards(alpha);
      renderer.setSimulationData(hazards, renderer.convoyState);

      appendLog(
        "PELIGRO",
        `Cálculo exitoso: D̄ máx=${hazards.max_avg_danger}. Defensas activas=${hazards.active_defenses_count}.`
      );
      for (const c of Object.values(hazards.corridor_hazards || {})) {
        if (c.avg_danger > 0) {
          const artBadge = c.has_artillery ? " [💥 ARTILLERÍA]" : "";
          appendLog("PELIGRO", `${c.u} ↔ ${c.v}: D̄=${c.avg_danger}, P(e)=${c.danger_potential}, w(e)=${c.reactive_weight}s${artBadge}`);
        }
      }
    } catch (err) {
      appendLog("ERROR", `Error al calcular peligros: ${err.message}`);
    }
  });

  btnConvoyStep.addEventListener("click", async () => {
    try {
      await executeStep();
    } catch (err) {
      appendLog("ERROR", `Error al ejecutar paso del convoy: ${err.message}`);
    }
  });

  btnConvoyPlay.addEventListener("click", () => {
    if (isLegacyPlaying) {
      stopAutoPlay();
      appendLog("CONVOY", "Marcha reactiva pausada.");
    } else {
      isLegacyPlaying = true;
      btnConvoyPlay.innerHTML = '<span id="playIcon">⏸</span> Pausar';
      legacyPlayInterval = setInterval(async () => {
        try {
          const res = await executeStep();
          if (res.is_finished) stopAutoPlay();
        } catch (err) {
          stopAutoPlay();
          appendLog("ERROR", `Error en marcha automática: ${err.message}`);
        }
      }, 800);
    }
  });

  btnConvoyRunAll.addEventListener("click", async () => {
    stopAutoPlay();
    try {
      const alpha = parseFloat(inputAlphaDanger.value);
      const res = await window.api.convoyRun(alpha, 100);
      appendLog(
        "CONVOY",
        `Recorrido finalizado en ${res.total_steps} paso(s). Anti-retroceso: ${res.backtracks_prevented}. Daño: ${res.total_damage_taken} HP.`
      );
      if (res.steps && res.steps.length > 0) {
        let idx = 0;
        const animTimer = setInterval(() => {
          if (idx < res.steps.length) {
            const stepData = res.steps[idx];
            currentConvoyState = stepData;
            renderer.setConvoyState(stepData);
            updateConvoyStats(stepData);
            idx++;
          } else {
            clearInterval(animTimer);
          }
        }, 350);
      }
    } catch (err) {
      appendLog("ERROR", `Error en ejecución total: ${err.message}`);
    }
  });

  btnConvoyReset.addEventListener("click", async () => {
    stopAutoPlay();
    try {
      const alpha = parseFloat(inputAlphaDanger.value);
      const res = await window.api.convoyReset(alpha);
      currentConvoyState = res;
      renderer.setConvoyState(res);
      updateConvoyStats(res);
      appendLog("CONVOY", `Ruta del convoy reiniciada a '${res.current_node}'.`);
    } catch (err) {
      appendLog("ERROR", `Error al reiniciar ruta: ${err.message}`);
    }
  });

  await refreshScenario();
});
