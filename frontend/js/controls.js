/**
 * Simulation playback controls (Play, Pause, Step, 0.5x-5x speed) and Logistics UI helpers.
 */

class SimulationControls {
  constructor(onTickCallback) {
    this.onTickCallback = onTickCallback;
    this.speedMultiplier = 1.0;
    this.timerId = null;
    this.isPlaying = false;
    this.inFlight = false;
  }

  isRunning() {
    return this.isPlaying;
  }

  getIntervalMs() {
    return Math.max(150, Math.round(1000 / this.speedMultiplier));
  }

  setSpeed(multiplier) {
    const parsed = parseFloat(multiplier);
    if (!isNaN(parsed) && parsed > 0) {
      this.speedMultiplier = parsed;
      if (this.isPlaying) {
        this._restartTimer();
      }
    }
  }

  start() {
    if (this.isPlaying) return;
    this.isPlaying = true;
    this._restartTimer();
  }

  pause() {
    if (this.timerId) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
    this.isPlaying = false;
  }

  toggle() {
    if (this.isPlaying) {
      this.pause();
    } else {
      this.start();
    }
    return this.isPlaying;
  }

  _restartTimer() {
    if (this.timerId) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
    this.timerId = setInterval(async () => {
      if (!this.isPlaying || this.inFlight) return;
      this.inFlight = true;
      try {
        const shouldContinue = await this.onTickCallback();
        if (shouldContinue === false) {
          this.pause();
        }
      } finally {
        this.inFlight = false;
      }
    }, this.getIntervalMs());
  }

  // ------------------------------------------
  // UI Rendering Helpers for Logistics & Status
  // ------------------------------------------

  static renderSoldierRoster(soldiers, containerEl, selectedIdsSet, summaryEl = null, originNodeId = "") {
    if (!containerEl) return;

    const inBase = soldiers.filter((s) => s.status === "en_base");
    const inTransit = soldiers.filter((s) => s.status === "en_transito");
    const stationed = soldiers.filter((s) => s.status === "apostado");

    if (summaryEl) {
      summaryEl.textContent = `Base: ${inBase.length} | Tránsito: ${inTransit.length} | Torres: ${stationed.length}`;
    }

    const availableAtOrigin = originNodeId
      ? soldiers.filter((s) => s.status === "apostado" && s.location_node_id === originNodeId)
      : inBase;

    const availIdSet = new Set(availableAtOrigin.map((s) => s.id));
    for (const id of Array.from(selectedIdsSet)) {
      if (!availIdSet.has(id)) {
        selectedIdsSet.delete(id);
      }
    }

    containerEl.innerHTML = "";
    if (availableAtOrigin.length === 0) {
      const empty = document.createElement("span");
      empty.style.cssText = "color: var(--text-muted); font-size: 0.72rem;";
      empty.textContent = originNodeId
        ? `No hay soldados apostados en ${originNodeId}.`
        : "No hay soldados esperando en Base.";
      containerEl.appendChild(empty);
      return;
    }

    for (const s of availableAtOrigin) {
      const chip = document.createElement("label");
      const isSelected = selectedIdsSet.has(s.id);
      chip.className = `soldier-chip${isSelected ? " selected" : ""}`;

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = isSelected;
      checkbox.value = s.id;
      checkbox.addEventListener("change", (e) => {
        if (e.target.checked) {
          selectedIdsSet.add(s.id);
          chip.classList.add("selected");
        } else {
          selectedIdsSet.delete(s.id);
          chip.classList.remove("selected");
        }
      });

      const shortType =
        s.type === "Infantería" ? "INF" : s.type === "Francotirador" ? "FRANC" : "ART";
      const labelText = document.createElement("span");
      labelText.textContent = `${shortType} (${s.id.slice(-4)})`;

      chip.appendChild(checkbox);
      chip.appendChild(labelText);
      containerEl.appendChild(chip);
    }
  }

  static renderOriginSelector(nodes, selectEl) {
    if (!selectEl) return;
    const prev = selectEl.value;
    selectEl.innerHTML = "";

    const baseOpt = document.createElement("option");
    baseOpt.value = "";
    baseOpt.textContent = "Base / Helipuerto";
    selectEl.appendChild(baseOpt);

    const towersWithTroops = (nodes || []).filter(
      (n) => n.is_active_tower && n.type !== "Base" && (n.stationed_soldiers || []).length > 0
    );
    for (const t of towersWithTroops) {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = `Torre ${t.id} (${t.stationed_soldiers.length} tropa(s))`;
      selectEl.appendChild(opt);
    }

    if (prev && towersWithTroops.some((t) => t.id === prev)) {
      selectEl.value = prev;
    }
  }

  static renderDestinationTowers(nodes, selectEl) {
    if (!selectEl) return;

    const previousValue = selectEl.value;
    const activeTowers = (nodes || []).filter(
      (n) => n.is_active_tower && n.type !== "Base"
    );

    selectEl.innerHTML = "";
    if (activeTowers.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Activa torres primero";
      selectEl.appendChild(opt);
      return;
    }

    for (const t of activeTowers) {
      const opt = document.createElement("option");
      opt.value = t.id;
      const stationedCount = (t.stationed_soldiers || []).length;
      const reservedCount = t.reserved_slots || 0;
      opt.textContent = `${t.id} (${stationedCount}+${reservedCount}/3)`;
      selectEl.appendChild(opt);
    }

    if (activeTowers.some((t) => t.id === previousValue)) {
      selectEl.value = previousValue;
    }
  }

  static renderBridgesPanel(bridges, containerEl) {
    if (!containerEl) return;

    containerEl.innerHTML = "";
    if (!bridges || bridges.length === 0) {
      const empty = document.createElement("div");
      empty.style.cssText = "color: var(--text-muted); font-size: 0.74rem;";
      empty.textContent = "Sin puentes en este escenario.";
      containerEl.appendChild(empty);
      return;
    }

    for (const b of bridges) {
      const item = document.createElement("div");
      item.className = `bridge-item${b.is_destroyed ? " bridge-collapsed" : ""}`;

      const header = document.createElement("div");
      header.className = "bridge-header";

      const title = document.createElement("span");
      title.style.fontWeight = "600";
      title.textContent = `Puente ${b.u} ↔ ${b.v}`;

      const status = document.createElement("span");
      status.style.fontFamily = "monospace";
      if (b.is_destroyed) {
        status.style.color = "var(--accent-red)";
        if (b.is_reconstructing) {
          status.textContent = `🔧 ${b.reconstruction_timer}s (${b.assigned_personnel} op.)`;
        } else {
          status.textContent = `⏸ ESPERANDO ${b.repair_personnel} op.`;
        }
      } else {
        status.style.color = "var(--accent-gold)";
        status.textContent = `${b.current_resistance}/${b.max_resistance} (${b.repair_personnel} op.)`;
      }

      header.appendChild(title);
      header.appendChild(status);

      const bar = document.createElement("div");
      bar.className = "bridge-bar";
      const fill = document.createElement("div");
      fill.className = "bridge-bar-fill";

      const ratio = b.max_resistance > 0 ? b.current_resistance / b.max_resistance : 0;
      if (b.is_destroyed) {
        const elapsedRatio =
          b.reconstruction_duration > 0
            ? Math.max(0, 1 - b.reconstruction_timer / b.reconstruction_duration)
            : 0;
        fill.style.width = `${Math.round(elapsedRatio * 100)}%`;
        fill.style.background = "var(--accent-red)";
      } else {
        fill.style.width = `${Math.round(ratio * 100)}%`;
        fill.style.background =
          ratio > 0.5 ? "var(--accent-green)" : "var(--accent-yellow)";
      }

      bar.appendChild(fill);
      item.appendChild(header);
      item.appendChild(bar);
      containerEl.appendChild(item);
    }
  }

  static renderConvoyMachines(machines, containerEl) {
    if (!containerEl) return;

    containerEl.innerHTML = "";
    if (!machines || machines.length === 0) return;

    for (const m of machines) {
      const row = document.createElement("div");
      row.className = `machine-row${!m.is_alive ? " machine-destroyed" : ""}`;

      const header = document.createElement("div");
      header.className = "machine-header";

      const name = document.createElement("span");
      name.textContent = `${m.type} (+$${m.reward})`;

      const hpText = document.createElement("span");
      hpText.style.fontFamily = "monospace";
      hpText.textContent = `${Math.round(m.current_hp)}/${Math.round(m.max_hp)} HP`;

      header.appendChild(name);
      header.appendChild(hpText);

      const bar = document.createElement("div");
      bar.className = "mini-hp-bar";
      const fill = document.createElement("div");
      fill.className = "mini-hp-fill";
      const ratio = m.max_hp > 0 ? Math.max(0, m.current_hp / m.max_hp) : 0;
      fill.style.width = `${Math.round(ratio * 100)}%`;
      fill.style.background =
        ratio > 0.5 ? "var(--accent-green)" : ratio > 0.25 ? "var(--accent-yellow)" : "var(--accent-red)";

      bar.appendChild(fill);
      row.appendChild(header);
      row.appendChild(bar);
      containerEl.appendChild(row);
    }
  }
}

window.SimulationControls = SimulationControls;
