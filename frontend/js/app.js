/**
 * Main application orchestrator for the visual interface.
 * Coordinates Scenario Management, MST (Kruskal), Tower Selection (Stage 2),
 * and Reactive Convoy Simulation with Anti-Backtracking (Stage 3).
 */

document.addEventListener("DOMContentLoaded", async () => {
  const canvas = document.getElementById("simCanvas");
  const renderer = new Renderer2D(canvas);

  // UI Elements - Stage 1 & 2
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

  // UI Elements - Stage 3 Simulation & Reactive Convoy
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
  const playIcon = document.getElementById("playIcon");
  const btnConvoyRunAll = document.getElementById("btnConvoyRunAll");
  const btnConvoyReset = document.getElementById("btnConvoyReset");
  const chkShowHeatmap = document.getElementById("chkShowHeatmap");
  const chkShowEvalPoints = document.getElementById("chkShowEvalPoints");

  // Application State
  let currentScenario = null;
  let currentMst = null;
  let currentTowerSelection = null;
  let currentHazards = null;
  let currentConvoyState = null;
  let playInterval = null;
  let isPlaying = false;

  function appendLog(tag, message, type = "info") {
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className = "log-entry";

    let tagClass = "log-tag-info";
    if (tag === "MST") tagClass = "log-tag-mst";
    else if (tag === "TORRE") tagClass = "log-tag-tower";
    else if (tag === "CONVOY") tagClass = "log-tag-convoy";
    else if (tag === "PELIGRO") tagClass = "log-tag-hazard";
    else if (tag === "ANTI-RETROCESO") tagClass = "log-tag-antibacktrack";
    else if (tag === "ALERTA" || tag === "RETROCESO") tagClass = "log-tag-warn";

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

  function updateConvoyStats(state) {
    if (!state) return;

    // Node position
    if (statConvoyPosEl) {
      statConvoyPosEl.textContent = state.current_node || "IN";
    }

    // Health calculation
    const hp = state.hp !== undefined ? state.hp : (state.convoy_status?.total_hp || 0);
    const maxHp = state.max_hp !== undefined ? state.max_hp : (state.convoy_status?.max_total_hp || 350);
    const ratio = maxHp > 0 ? hp / maxHp : 0;
    const pct = Math.round(ratio * 100);

    if (statConvoyHpEl) {
      statConvoyHpEl.textContent = `${pct}% (${Math.round(hp)}/${Math.round(maxHp)})`;
      if (ratio > 0.5) {
        statConvoyHpEl.style.color = "var(--accent-green)";
      } else if (ratio > 0.25) {
        statConvoyHpEl.style.color = "var(--accent-yellow)";
      } else {
        statConvoyHpEl.style.color = "var(--accent-red)";
      }
    }

    // Damage taken
    const damage = state.history?.total_damage_taken !== undefined
      ? state.history.total_damage_taken
      : (state.total_damage_taken || 0);
    if (statConvoyDamageEl) {
      statConvoyDamageEl.textContent = `${Math.round(damage)} HP`;
    }

    // Backtracks count
    const backtracks = state.backtracks_prevented !== undefined
      ? state.backtracks_prevented
      : (state.backtrack_count || 0);
    if (statAntiBacktracksEl) {
      statAntiBacktracksEl.textContent = backtracks;
    }

    // Status badge
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
          badgeConvoyStatusEl.textContent = "Sin Ruta";
        }
      } else if (state.step_index > 0) {
        badgeConvoyStatusEl.className = "badge badge-purple";
        badgeConvoyStatusEl.textContent = "En Marcha";
      } else {
        badgeConvoyStatusEl.className = "badge badge-purple";
        badgeConvoyStatusEl.textContent = "En Espera";
      }
    }
  }

  function stopAutoPlay() {
    if (playInterval) {
      clearInterval(playInterval);
      playInterval = null;
    }
    isPlaying = false;
    if (btnConvoyPlay) {
      btnConvoyPlay.innerHTML = '<span id="playIcon">▶</span> Iniciar';
    }
  }

  async function executeStep() {
    const alpha = parseFloat(inputAlphaDanger.value);
    const res = await window.api.convoyStep(alpha);
    currentConvoyState = res;
    if (res.corridor_hazards) {
      currentHazards = res;
    }

    renderer.setConvoyState(res);
    updateConvoyStats(res);

    // Decision logging
    const dec = res.decision || {};
    if (dec.type === "ANTI_BACKTRACK_AVOIDED") {
      appendLog(
        "ANTI-RETROCESO",
        `⛔ Regla activada en nodo '${res.previous_node}': se descartó regreso a '${dec.discarded_node}'. Desvío alternativo tomado hacia '${res.current_node}' (Ruta hacia salida: ${dec.projected_path?.join(" ➔ ")}).`
      );
    } else if (dec.type === "FORCED_DEAD_END_BACKTRACK") {
      appendLog(
        "ALERTA",
        `🛑 Callejón sin salida en '${res.previous_node}'. Retroceso forzado como último recurso hacia '${res.current_node}'.`
      );
    } else if (dec.type === "OPTIMAL") {
      appendLog(
        "CONVOY",
        `Paso #${res.step_index}: Convoy avanzó de '${res.previous_node}' a '${res.current_node}'. Ruta proyectada: ${dec.projected_path?.join(" ➔ ")} (Costo w: ${res.dijkstra?.raw_cost}s).`
      );
    } else if (dec.type === "REACHED_EXIT") {
      appendLog("CONVOY", `Convoy ha arribado a la salida '${res.target_node}'.`);
    }

    appendLog(
      "CONVOY",
      `Telemetría Convoy: HP=${res.hp}/${res.max_hp}, Daño acumulado=${res.history?.total_damage_taken || 0} HP, Tiempo transcurrido=${res.history?.total_time_elapsed || 0}s.`
    );

    if (res.is_finished) {
      stopAutoPlay();
      if (res.escaped) {
        appendLog("CONVOY", `🎉 ¡MISIÓN ENEMIGA EXITOSA! El convoy blindado escapó por el nodo '${res.target_node}'.`);
      } else if (res.destroyed) {
        appendLog("CONVOY", `💥 ¡VICTORIA DEFENSIVA TOTAL! El convoy fue completamente destruido.`);
      }
    }

    return res;
  }

  async function refreshScenario() {
    try {
      currentScenario = await window.api.getCurrentScenario();
      currentMst = currentScenario.mst_result;
      currentTowerSelection = currentScenario.tower_selection_result;

      renderer.setData(currentScenario, currentMst, currentTowerSelection);
      updateStats();
      appendLog("ESCENARIO", `Escenario '${currentScenario.scenario_name}' sincronizado.`);

      // Sync initial Stage 3 simulation state
      try {
        const alpha = parseFloat(inputAlphaDanger.value) || 1.0;
        const resetRes = await window.api.convoyReset(alpha);
        currentConvoyState = resetRes;
        if (resetRes.corridor_hazards) {
          currentHazards = resetRes;
        }
        renderer.setConvoyState(resetRes);
        updateConvoyStats(resetRes);
      } catch (e) {
        console.warn("Could not auto-reset convoy on scenario refresh:", e);
      }
    } catch (err) {
      appendLog("ERROR", `Error cargando escenario: ${err.message}`);
    }
  }

  // ==========================================
  // Event Listeners - Stage 1 & 2
  // ==========================================

  btnLoadDefault.addEventListener("click", async () => {
    try {
      stopAutoPlay();
      appendLog("CARGA", "Cargando escenario básico pedagógico...");
      currentScenario = await window.api.loadDefaultScenario("scenario_1_basic.json");
      currentMst = null;
      currentTowerSelection = null;
      renderer.setData(currentScenario, null, null);
      updateStats();
      appendLog("CARGA", "Escenario básico cargado correctamente.");

      // Reset convoy state for new scenario
      const alpha = parseFloat(inputAlphaDanger.value) || 1.0;
      const resetRes = await window.api.convoyReset(alpha);
      currentConvoyState = resetRes;
      renderer.setConvoyState(resetRes);
      updateConvoyStats(resetRes);
    } catch (err) {
      appendLog("ERROR", `Error al cargar escenario por defecto: ${err.message}`);
    }
  });

  btnUpload.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      stopAutoPlay();
      appendLog("CARGA", `Subiendo archivo: ${file.name}...`);
      currentScenario = await window.api.uploadScenarioFile(file);
      currentMst = null;
      currentTowerSelection = null;
      renderer.setData(currentScenario, null, null);
      updateStats();
      appendLog("CARGA", `Escenario '${currentScenario.scenario_name}' cargado con éxito.`);

      const alpha = parseFloat(inputAlphaDanger.value) || 1.0;
      const resetRes = await window.api.convoyReset(alpha);
      currentConvoyState = resetRes;
      renderer.setConvoyState(resetRes);
      updateConvoyStats(resetRes);
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
          `Iteración #${step.iteration}: Seleccionada Torre '${step.selected_tower_id}' con puntuación S(p)=${step.score}. Cubre ${step.new_corridors_covered} nuevo(s) corredor(es). Restan ${step.unwatched_remaining} por vigilar.`
        );
      }

      // Automatically re-evaluate hazards with the newly deployed towers
      const alpha = parseFloat(inputAlphaDanger.value) || 1.0;
      const hazards = await window.api.calculateHazards(alpha);
      currentHazards = hazards;
      renderer.setSimulationData(hazards, currentConvoyState);
      appendLog("PELIGRO", `Peligros en corredores actualizados tras despliegue de torres.`);
    } catch (err) {
      appendLog("ERROR", `Error en selección voraz: ${err.message}`);
    }
  });

  btnClearLog.addEventListener("click", () => {
    logViewer.innerHTML = "";
  });

  // ==========================================
  // Event Listeners - Stage 3 Simulation & Controls
  // ==========================================

  // Risk slider real-time value display
  inputAlphaDanger.addEventListener("input", (e) => {
    const val = parseFloat(e.target.value).toFixed(1);
    labelAlphaValue.textContent = val;
  });

  // Display toggles
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

  // Calculate Hazards Button
  btnCalcHazards.addEventListener("click", async () => {
    try {
      const alpha = parseFloat(inputAlphaDanger.value);
      appendLog("PELIGRO", `Calculando peligros en corredores G_M con factor de riesgo α=${alpha}...`);
      const hazards = await window.api.calculateHazards(alpha);
      currentHazards = hazards;

      renderer.setSimulationData(hazards, currentConvoyState);

      appendLog(
        "PELIGRO",
        `Cálculo exitoso: Peligro promedio máx D̄=${hazards.max_avg_danger}. Defensas activas: ${hazards.active_defenses_count}.`
      );

      // Report active hazards on covered corridors
      let coveredCount = 0;
      for (const [key, c] of Object.entries(hazards.corridor_hazards || {})) {
        if (c.avg_danger > 0) {
          coveredCount++;
          const artBadge = c.has_artillery ? " [💥 ARTILLERÍA]" : "";
          appendLog(
            "PELIGRO",
            `Corredor ${c.u} ↔ ${c.v}: D̄=${c.avg_danger}, Daño pot P(e)=${c.danger_potential}, Peso reactivo w(e)=${c.reactive_weight}s${artBadge}`
          );
        }
      }
      if (coveredCount === 0) {
        appendLog("PELIGRO", `Ningún corredor cubierto actualmente por defensas desplegadas.`);
      }
    } catch (err) {
      appendLog("ERROR", `Error al calcular peligros: ${err.message}`);
    }
  });

  // Convoy Step Button
  btnConvoyStep.addEventListener("click", async () => {
    try {
      await executeStep();
    } catch (err) {
      appendLog("ERROR", `Error al ejecutar paso del convoy: ${err.message}`);
    }
  });

  // Convoy Play/Pause Button
  btnConvoyPlay.addEventListener("click", () => {
    if (isPlaying) {
      stopAutoPlay();
      appendLog("CONVOY", "Simulación pausada.");
    } else {
      if (currentConvoyState && currentConvoyState.is_finished) {
        appendLog("CONVOY", "El convoy ya finalizó su recorrido. Pulsa 'Reiniciar Convoy' para simular de nuevo.");
        return;
      }

      isPlaying = true;
      btnConvoyPlay.innerHTML = '<span id="playIcon">⏸</span> Pausar';
      appendLog("CONVOY", "Iniciando marcha reactiva automática paso a paso (800ms)...");

      playInterval = setInterval(async () => {
        try {
          const res = await executeStep();
          if (res.is_finished) {
            stopAutoPlay();
          }
        } catch (err) {
          stopAutoPlay();
          appendLog("ERROR", `Error en marcha automática: ${err.message}`);
        }
      }, 800);
    }
  });

  // Convoy Run All Button
  btnConvoyRunAll.addEventListener("click", async () => {
    stopAutoPlay();
    try {
      const alpha = parseFloat(inputAlphaDanger.value);
      appendLog("CONVOY", `Ejecutando recorrido completo del convoy con α=${alpha}...`);
      const res = await window.api.convoyRun(alpha, 100);

      appendLog(
        "CONVOY",
        `Simulación completa finalizada en ${res.total_steps} paso(s). Resultado: ${res.escaped ? "ESCAPÓ" : (res.destroyed ? "DESTRUIDO" : "FINALIZADO")}. Decisiones anti-retroceso: ${res.backtracks_prevented}. Daño total: ${res.total_damage_taken} HP.`
      );

      if (res.steps && res.steps.length > 0) {
        // Animate sequence smoothly for visual feedback
        let stepIdx = 0;
        const animTimer = setInterval(() => {
          if (stepIdx < res.steps.length) {
            const stepData = res.steps[stepIdx];
            currentConvoyState = stepData;
            renderer.setConvoyState(stepData);
            updateConvoyStats(stepData);

            const dec = stepData.decision || {};
            if (dec.type === "ANTI_BACKTRACK_AVOIDED") {
              appendLog(
                "ANTI-RETROCESO",
                `[Paso ${stepData.step_index}] ⛔ Regla activada: Descartado '${dec.discarded_node}', desvío tomado hacia '${stepData.current_node}'.`
              );
            }
            stepIdx++;
          } else {
            clearInterval(animTimer);
            appendLog("CONVOY", `Visualización de recorrido total concluida.`);
          }
        }, 350);
      }
    } catch (err) {
      appendLog("ERROR", `Error en ejecución total del convoy: ${err.message}`);
    }
  });

  // Convoy Reset Button
  btnConvoyReset.addEventListener("click", async () => {
    stopAutoPlay();
    try {
      const alpha = parseFloat(inputAlphaDanger.value);
      appendLog("CONVOY", "Reiniciando convoy a posición de ENTRADA (IN)...");
      const res = await window.api.convoyReset(alpha);
      currentConvoyState = res;
      if (res.corridor_hazards) {
        currentHazards = res;
      }

      renderer.setConvoyState(res);
      updateConvoyStats(res);

      appendLog(
        "CONVOY",
        `Convoy reiniciado a '${res.current_node}'. HP restaurado: ${res.hp}/${res.max_hp} (100%). Ruta proyectada hacia salida: ${res.projected_path?.join(" ➔ ")} (Costo w: ${res.projected_cost}s).`
      );
    } catch (err) {
      appendLog("ERROR", `Error al reiniciar convoy: ${err.message}`);
    }
  });

  // Initial load
  await refreshScenario();
});
