/**
 * Audit Log Viewer module for real-time convoy, bridge, combat, and logistics telemetry.
 */

class LogViewer {
  constructor(containerEl, clearBtnEl = null) {
    this.containerEl = containerEl;
    this.clearBtnEl = clearBtnEl;
    this.maxEntries = 250;
    this.seenBackendKeys = new Set();

    if (this.clearBtnEl) {
      this.clearBtnEl.addEventListener("click", () => this.clear());
    }
  }

  _getTagClass(tag) {
    switch (tag) {
      case "MST":
        return "log-tag-mst";
      case "TORRE":
        return "log-tag-tower";
      case "CONVOY":
        return "log-tag-convoy";
      case "PELIGRO":
        return "log-tag-hazard";
      case "ANTI-RETROCESO":
        return "log-tag-antibacktrack";
      case "LOGÍSTICA":
        return "log-tag-logistics";
      case "COMBATE":
        return "log-tag-combat";
      case "PUENTE":
        return "log-tag-bridge";
      case "VICTORIA":
        return "log-tag-victory";
      case "DERROTA":
        return "log-tag-defeat";
      case "ALERTA":
      case "RETROCESO":
      case "ERROR":
        return "log-tag-warn";
      default:
        return "log-tag-info";
    }
  }

  _mapBackendTypeToTag(eventType) {
    if (!eventType) return "INFO";
    if (eventType.startsWith("BRIDGE_")) return "PUENTE";
    if (eventType === "COMBAT_ATTACK" || eventType === "ENEMY_DESTROYED") return "COMBATE";
    if (eventType === "CONVOY_DECISION") return "CONVOY";
    if (eventType === "GAME_OVER") return "VICTORIA";
    if (
      eventType.startsWith("SOLDIER_") ||
      eventType.startsWith("GROUND_") ||
      eventType.startsWith("AIR_") ||
      eventType.startsWith("MISSION_")
    ) {
      return "LOGÍSTICA";
    }
    return "INFO";
  }

  append(tag, message, timestampLabel = null) {
    if (!this.containerEl) return;

    const time = timestampLabel || new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className = "log-entry";

    const timeSpan = document.createElement("span");
    timeSpan.className = "log-time";
    timeSpan.textContent = `[${time}]`;

    const tagSpan = document.createElement("span");
    tagSpan.className = this._getTagClass(tag);
    tagSpan.textContent = `[${tag}]`;

    const msgSpan = document.createElement("span");
    msgSpan.className = "log-msg";
    msgSpan.textContent = message;

    entry.appendChild(timeSpan);
    entry.appendChild(tagSpan);
    entry.appendChild(msgSpan);

    this.containerEl.appendChild(entry);

    while (this.containerEl.children.length > this.maxEntries) {
      this.containerEl.removeChild(this.containerEl.firstChild);
    }

    this.containerEl.scrollTop = this.containerEl.scrollHeight;
  }

  syncBackendEvents(eventLog) {
    if (!Array.isArray(eventLog)) return;

    for (let i = 0; i < eventLog.length; i++) {
      const ev = eventLog[i];
      const key = `${ev.timestamp}|${ev.type}|${ev.message}`;
      if (this.seenBackendKeys.has(key)) continue;

      this.seenBackendKeys.add(key);
      let tag = this._mapBackendTypeToTag(ev.type);
      if (ev.type === "GAME_OVER" && ev.details?.result === "Derrota") {
        tag = "DERROTA";
      } else if (ev.type === "BRIDGE_COLLAPSED" || ev.type === "MISSION_BLOCKED") {
        tag = "ALERTA";
      }
      this.append(tag, ev.message, `t=${ev.timestamp}s`);
    }
  }

  resetSync() {
    this.seenBackendKeys.clear();
  }

  clear() {
    if (this.containerEl) {
      this.containerEl.innerHTML = "";
    }
  }
}

window.LogViewer = LogViewer;
