/**
 * 2D Canvas renderer for Elevated Network (G_E) and Maze Network (G_M).
 * Features auto-fit scaling, interactive pan/zoom, hover tooltips, crisp pill labels,
 * 2-layer depth separation (recessed maze vs. elevated network), and full Stage 1-6 telemetry.
 */

const SOLDIER_BASE_STATS = {
  "Infantería": { baseRange: 5.0, color: "#3fb950", shortLabel: "I" },
  "Francotirador": { baseRange: 20.0, color: "#58a6ff", shortLabel: "F" },
  "Artillero": { baseRange: 15.0, color: "#f85149", shortLabel: "A" },
};

class Renderer2D {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.scenarioData = null;
    this.mstResult = null;
    this.towerSelectionResult = null;

    // Stage 3-6 Simulation State
    this.corridorHazards = null;
    this.convoyState = null;
    this.soldiers = [];
    this.missions = [];
    this.lastCombat = null;
    this.gameResult = null;
    this.isGameOver = false;

    this.showHeatmap = true;
    this.showEvalPoints = true;
    this.showSurveillanceRanges = true;
    this.showAttackRanges = true;
    this.showEdgeLabels = true;
    this.maxDanger = 30.0;

    // Viewport transform & interactive pan/zoom
    this.padLeft = 75;
    this.padRight = 75;
    this.padTop = 65;
    this.padBottom = 65;
    this.baseScale = 1.0;
    this.baseOffsetX = 0;
    this.baseOffsetY = 0;
    this.userZoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.scale = 1.0;
    this.offsetX = 0;
    this.offsetY = 0;

    // Interaction & hover state
    this.isDragging = false;
    this.dragStartX = 0;
    this.dragStartY = 0;
    this.hoverPos = null;
    this.hoverItem = null;

    this.resizeCanvas();
    this._bindInteractions();
    window.addEventListener("resize", () => {
      this.resizeCanvas();
      this.calculateTransform();
      this.render();
    });
  }

  _bindInteractions() {
    this.canvas.style.cursor = "grab";

    this.canvas.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const rect = this.canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        const zoomFactor = e.deltaY < 0 ? 1.12 : 0.89;
        const nextZoom = Math.min(5.0, Math.max(0.4, this.userZoom * zoomFactor));
        const ratio = nextZoom / this.userZoom;

        // Zoom anchored around cursor
        this.panX = mx - (mx - this.panX) * ratio;
        this.panY = my - (my - this.panY) * ratio;
        this.userZoom = nextZoom;

        this._applyCombinedTransform();
        this.render();
      },
      { passive: false }
    );

    this.canvas.addEventListener("mousedown", (e) => {
      this.isDragging = true;
      this.dragStartX = e.clientX;
      this.dragStartY = e.clientY;
      this.canvas.style.cursor = "grabbing";
    });

    window.addEventListener("mouseup", () => {
      if (this.isDragging) {
        this.isDragging = false;
        this.canvas.style.cursor = "grab";
      }
    });

    this.canvas.addEventListener("mousemove", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      if (this.isDragging) {
        this.panX += e.clientX - this.dragStartX;
        this.panY += e.clientY - this.dragStartY;
        this.dragStartX = e.clientX;
        this.dragStartY = e.clientY;
        this._applyCombinedTransform();
        this.render();
        return;
      }

      this.hoverPos = { x: mx, y: my };
      const hit = this._hitTest(mx, my);
      if (hit !== this.hoverItem) {
        this.hoverItem = hit;
        this.canvas.style.cursor = hit ? "pointer" : "grab";
      }
      this.render();
    });

    this.canvas.addEventListener("mouseleave", () => {
      this.hoverPos = null;
      this.hoverItem = null;
      this.render();
    });
  }

  resetView() {
    this.userZoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this._applyCombinedTransform();
    this.render();
  }

  resizeCanvas() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.max(1, rect.width) * dpr;
    this.canvas.height = Math.max(1, rect.height) * dpr;
    this.canvas.style.width = `${rect.width}px`;
    this.canvas.style.height = `${rect.height}px`;
    this.ctx.resetTransform();
    this.ctx.scale(dpr, dpr);
    this.width = rect.width;
    this.height = rect.height;
  }

  setData(scenarioData, mstResult = null, towerSelectionResult = null) {
    this.scenarioData = scenarioData;
    this.mstResult = mstResult;
    this.towerSelectionResult = towerSelectionResult;
    this.calculateTransform();
    this.render();
  }

  setSimulationData(hazards, convoyState = null) {
    if (hazards) {
      this.corridorHazards = hazards.corridor_hazards || hazards;
      if (hazards.max_avg_danger !== undefined) {
        this.maxDanger = Math.max(10.0, hazards.max_avg_danger);
      }
    }
    if (convoyState !== null) {
      this.convoyState = convoyState;
    }
    this.render();
  }

  setConvoyState(convoyState) {
    this.convoyState = convoyState;
    if (convoyState && convoyState.corridor_hazards) {
      this.corridorHazards = convoyState.corridor_hazards;
    }
    this.render();
  }

  setFullSimulationState(fullState) {
    if (!fullState) return;

    if (!this.scenarioData) {
      this.scenarioData = {
        scenario_name: "Simulación Activa",
        config: { beta_elevation: 0.1 },
        elevated_network: fullState.elevated_network,
        maze_network: fullState.maze_network,
      };
      this.calculateTransform();
    } else {
      if (fullState.elevated_network) {
        this.scenarioData.elevated_network = fullState.elevated_network;
      }
      if (fullState.maze_network) {
        this.scenarioData.maze_network = fullState.maze_network;
      }
    }

    if (fullState.corridor_hazards) {
      this.corridorHazards = fullState.corridor_hazards;
    }
    if (fullState.max_avg_danger !== undefined) {
      this.maxDanger = Math.max(10.0, fullState.max_avg_danger);
    }

    this.soldiers = fullState.soldiers || [];
    this.missions = fullState.missions || [];
    this.lastCombat = fullState.last_combat || null;
    this.gameResult = fullState.game_result || null;
    this.isGameOver = Boolean(fullState.is_game_over);

    const c = fullState.convoy;
    if (c) {
      const pathTaken = c.path_taken || [];
      const traversedEdges = [];
      for (let i = 0; i < pathTaken.length - 1; i++) {
        traversedEdges.push([pathTaken[i], pathTaken[i + 1]]);
      }
      if (c.current_edge && c.current_edge.length === 2) {
        traversedEdges.push([c.current_edge[0], c.current_edge[1]]);
      }

      this.convoyState = {
        current_node: c.current_node,
        previous_node: c.previous_node,
        target_node: c.target_node,
        current_edge: c.current_edge,
        x: c.x,
        y: c.y,
        hp: c.hp,
        max_hp: c.max_hp,
        is_finished: Boolean(fullState.is_game_over),
        escaped: Boolean(c.escaped),
        destroyed: Boolean(c.destroyed),
        game_result: fullState.game_result,
        projected_path: c.last_decision?.projected_path || [],
        decision: c.last_decision || null,
        history: {
          traversed_edges: traversedEdges,
        },
      };
    }

    this.render();
  }

  getHazardForCorridor(u, v) {
    if (!this.corridorHazards) return null;
    return this.corridorHazards[`${u}-${v}`] || this.corridorHazards[`${v}-${u}`] || null;
  }

  calculateTransform() {
    if (!this.scenarioData || !this.width || !this.height) return;

    const allNodes = [
      ...(this.scenarioData.elevated_network?.nodes || []),
      ...(this.scenarioData.maze_network?.nodes || []),
    ];

    if (allNodes.length === 0) return;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const node of allNodes) {
      if (node.x < minX) minX = node.x;
      if (node.x > maxX) maxX = node.x;
      if (node.y < minY) minY = node.y;
      if (node.y > maxY) maxY = node.y;
    }

    const worldWidth = Math.max(1, maxX - minX);
    const worldHeight = Math.max(1, maxY - minY);

    const availableWidth = Math.max(120, this.width - this.padLeft - this.padRight);
    const availableHeight = Math.max(120, this.height - this.padTop - this.padBottom);

    const scaleX = availableWidth / worldWidth;
    const scaleY = availableHeight / worldHeight;
    this.baseScale = Math.max(0.5, Math.min(scaleX, scaleY, 25.0));

    const scaledWidth = worldWidth * this.baseScale;
    const scaledHeight = worldHeight * this.baseScale;

    this.baseOffsetX = this.padLeft + (availableWidth - scaledWidth) / 2 - minX * this.baseScale;
    this.baseOffsetY = this.padTop + (availableHeight - scaledHeight) / 2 - minY * this.baseScale;

    this._applyCombinedTransform();
  }

  _applyCombinedTransform() {
    this.scale = this.baseScale * this.userZoom;
    this.offsetX = this.baseOffsetX * this.userZoom + this.panX;
    this.offsetY = this.baseOffsetY * this.userZoom + this.panY;
  }

  worldToScreen(x, y) {
    return {
      x: x * this.scale + this.offsetX,
      y: y * this.scale + this.offsetY,
    };
  }

  _drawPillLabel(text, x, y, opts = {}) {
    const {
      font = "bold 10px sans-serif",
      textColor = "#e6edf3",
      bgColor = "rgba(13, 17, 23, 0.88)",
      borderColor = "rgba(48, 54, 61, 0.9)",
      padX = 6,
      height = 17,
      radius = 4,
    } = opts;

    this.ctx.save();
    this.ctx.font = font;
    const w = this.ctx.measureText(text).width + padX * 2;
    const left = x - w / 2;
    const top = y - height / 2;

    this.ctx.fillStyle = bgColor;
    this.ctx.beginPath();
    if (typeof this.ctx.roundRect === "function") {
      this.ctx.roundRect(left, top, w, height, radius);
    } else {
      this.ctx.rect(left, top, w, height);
    }
    this.ctx.fill();

    if (borderColor) {
      this.ctx.strokeStyle = borderColor;
      this.ctx.lineWidth = 1;
      this.ctx.stroke();
    }

    this.ctx.fillStyle = textColor;
    this.ctx.textAlign = "center";
    this.ctx.textBaseline = "middle";
    this.ctx.fillText(text, x, y + 0.5);
    this.ctx.restore();
  }

  _hitTest(mx, my) {
    if (!this.scenarioData) return null;

    // 1. Check elevated nodes (top layer priority)
    for (const node of this.scenarioData.elevated_network?.nodes || []) {
      const p = this.worldToScreen(node.x, node.y);
      if (Math.hypot(p.x - mx, p.y - my) <= 16) {
        return { kind: "elevated_node", data: node };
      }
    }

    // 2. Check maze nodes
    for (const node of this.scenarioData.maze_network?.nodes || []) {
      const p = this.worldToScreen(node.x, node.y);
      if (Math.hypot(p.x - mx, p.y - my) <= 14) {
        return { kind: "maze_node", data: node };
      }
    }

    // 3. Check elevated edge midpoints
    const elevMap = new Map(
      (this.scenarioData.elevated_network?.nodes || []).map((n) => [n.id, n])
    );
    for (const edge of this.scenarioData.elevated_network?.edges || []) {
      const u = elevMap.get(edge.u);
      const v = elevMap.get(edge.v);
      if (!u || !v) continue;
      const p1 = this.worldToScreen(u.x, u.y);
      const p2 = this.worldToScreen(v.x, v.y);
      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;
      if (Math.hypot(midX - mx, midY - my) <= 18) {
        return { kind: "elevated_edge", data: edge };
      }
    }

    // 4. Check maze corridor midpoints
    const mazeMap = new Map(
      (this.scenarioData.maze_network?.nodes || []).map((n) => [n.id, n])
    );
    for (const corr of this.scenarioData.maze_network?.corridors || []) {
      const u = mazeMap.get(corr.u);
      const v = mazeMap.get(corr.v);
      if (!u || !v) continue;
      const p1 = this.worldToScreen(u.x, u.y);
      const p2 = this.worldToScreen(v.x, v.y);
      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;
      if (Math.hypot(midX - mx, midY - my) <= 18) {
        return {
          kind: "maze_corridor",
          data: corr,
          hazard: this.getHazardForCorridor(corr.u, corr.v),
        };
      }
    }

    return null;
  }

  render() {
    this.ctx.clearRect(0, 0, this.width, this.height);

    if (!this.scenarioData) {
      this.drawEmptyState();
      return;
    }

    this.drawBackgroundGrid();
    this.drawActiveTowerRadii();
    this.drawMazeNetwork();
    this.drawConvoyTrail();
    this.drawMazeNodes();
    this.drawElevatedNetwork();
    this.drawElevatedNodes();
    this.drawStationedSoldiers();
    this.drawTransportMissions();
    this.drawAntiBacktracking();
    this.drawConvoyToken();
    this.drawCombatEffects();
    this.drawHoverTooltip();
  }

  drawEmptyState() {
    this.ctx.fillStyle = "#8b949e";
    this.ctx.font = "16px sans-serif";
    this.ctx.textAlign = "center";
    this.ctx.fillText("No hay escenario cargado. Carga un archivo para comenzar.", this.width / 2, this.height / 2);
  }

  drawBackgroundGrid() {
    this.ctx.strokeStyle = "rgba(48, 54, 61, 0.25)";
    this.ctx.lineWidth = 1;
    const gridSize = 10 * this.scale;
    if (gridSize < 14) return;

    this.ctx.beginPath();
    for (let x = ((this.offsetX % gridSize) + gridSize) % gridSize; x < this.width; x += gridSize) {
      this.ctx.moveTo(x, 0);
      this.ctx.lineTo(x, this.height);
    }
    for (let y = ((this.offsetY % gridSize) + gridSize) % gridSize; y < this.height; y += gridSize) {
      this.ctx.moveTo(0, y);
      this.ctx.lineTo(this.width, y);
    }
    this.ctx.stroke();
  }

  drawMazeNetwork() {
    const corridors = this.scenarioData.maze_network?.corridors || [];
    const nodeMap = new Map(
      (this.scenarioData.maze_network?.nodes || []).map((n) => [n.id, n])
    );

    const watchedSet = new Set(this.towerSelectionResult?.watched_corridors || []);

    for (const corr of corridors) {
      const u = nodeMap.get(corr.u);
      const v = nodeMap.get(corr.v);
      if (!u || !v) continue;

      const p1 = this.worldToScreen(u.x, u.y);
      const p2 = this.worldToScreen(v.x, v.y);

      const isWatched = watchedSet.has(`${corr.u}-${corr.v}`) || watchedSet.has(`${corr.v}-${corr.u}`);
      const hazard = this.getHazardForCorridor(corr.u, corr.v);
      const avgDanger = hazard?.avg_danger || 0.0;

      let outerColor = isWatched ? "rgba(63, 185, 80, 0.25)" : "rgba(56, 64, 74, 0.45)";
      let coreColor = isWatched ? "#2ea043" : "#3a424d";
      let hasLethalGlow = false;

      if (this.showHeatmap && hazard && avgDanger > 0) {
        if (avgDanger <= 10) {
          outerColor = "rgba(210, 153, 34, 0.35)";
          coreColor = "#d29922";
        } else if (avgDanger <= 25) {
          outerColor = "rgba(240, 136, 62, 0.45)";
          coreColor = "#f0883e";
        } else {
          outerColor = "rgba(248, 81, 73, 0.55)";
          coreColor = "#f85149";
          hasLethalGlow = true;
        }
      }

      // Recessed ground road channel
      this.ctx.save();
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);
      this.ctx.lineWidth = 14;
      this.ctx.strokeStyle = outerColor;
      this.ctx.lineCap = "round";
      if (hasLethalGlow) {
        this.ctx.shadowColor = "#f85149";
        this.ctx.shadowBlur = 10;
      }
      this.ctx.stroke();
      this.ctx.shadowBlur = 0;

      // Inner dark asphalt lane
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);
      this.ctx.lineWidth = 6;
      this.ctx.strokeStyle = "#161b22";
      this.ctx.stroke();

      // Center guide line
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);
      this.ctx.lineWidth = 2;
      this.ctx.strokeStyle = coreColor;
      this.ctx.setLineDash([6, 5]);
      this.ctx.stroke();
      this.ctx.setLineDash([]);
      this.ctx.restore();

      // 3 sampling points (q_ini, q_mid, q_end)
      if (this.showEvalPoints && hazard) {
        for (const pt of [hazard.q_ini, hazard.q_mid, hazard.q_end]) {
          if (!pt || pt.x === undefined || pt.y === undefined) continue;
          const qScreen = this.worldToScreen(pt.x, pt.y);
          const dmg = pt.damage_rate || 0;
          if (dmg <= 0) continue; // Only dot actively threatened sampling points to avoid clutter

          this.ctx.beginPath();
          this.ctx.arc(qScreen.x, qScreen.y, 4, 0, Math.PI * 2);
          this.ctx.fillStyle = dmg <= 20 ? "#d29922" : "#f85149";
          this.ctx.fill();
          this.ctx.strokeStyle = "#ffffff";
          this.ctx.lineWidth = 1;
          this.ctx.stroke();
        }
      }

      if (this.showEdgeLabels) {
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const len = Math.hypot(dx, dy) || 1;
        // Slight perpendicular offset downward from road center
        const nx = (-dy / len) * 11;
        const ny = (dx / len) * 11;
        const labelX = (p1.x + p2.x) / 2 + nx;
        const labelY = (p1.y + p2.y) / 2 + ny;

        if (hazard && avgDanger > 0) {
          const art = hazard.has_artillery ? " 💥" : "";
          this._drawPillLabel(
            `w:${hazard.reactive_weight}s · D̄:${hazard.avg_danger}${art}`,
            labelX,
            labelY,
            {
              font: "bold 9px monospace",
              textColor: avgDanger > 25 ? "#ffa198" : "#ffdf5d",
              borderColor: avgDanger > 25 ? "rgba(248, 81, 73, 0.7)" : "rgba(210, 153, 34, 0.6)",
              height: 15,
            }
          );
        } else {
          const baseT = hazard ? hazard.base_time : (corr.base_time ?? (corr.length / corr.speed).toFixed(1));
          this._drawPillLabel(`${baseT}s`, labelX, labelY, {
            font: "9px monospace",
            textColor: isWatched ? "#7ee787" : "#8b949e",
            borderColor: isWatched ? "rgba(63, 185, 80, 0.5)" : "rgba(48, 54, 61, 0.7)",
            height: 14,
            padX: 4,
          });
        }
      }
    }
  }

  drawElevatedNetwork() {
    const edges = this.scenarioData.elevated_network?.edges || [];
    const nodeMap = new Map(
      (this.scenarioData.elevated_network?.nodes || []).map((n) => [n.id, n])
    );

    const mstEdgeSet = new Set();
    if (this.mstResult?.mst_edges) {
      for (const e of this.mstResult.mst_edges) {
        mstEdgeSet.add(`${Math.min(e.u, e.v)}-${Math.max(e.u, e.v)}`);
      }
    }

    for (const edge of edges) {
      const u = nodeMap.get(edge.u);
      const v = nodeMap.get(edge.v);
      if (!u || !v) continue;

      const p1 = this.worldToScreen(u.x, u.y);
      const p2 = this.worldToScreen(v.x, v.y);
      const edgeKey = `${Math.min(edge.u, edge.v)}-${Math.max(edge.u, edge.v)}`;
      const isMst = mstEdgeSet.has(edgeKey);
      const isFootOnly = edge.moto_time === null || edge.moto_time === undefined;

      this.ctx.save();
      // Drop shadow beneath elevated catwalk so G_E visibly floats above G_M
      this.ctx.shadowColor = "rgba(0, 0, 0, 0.75)";
      this.ctx.shadowBlur = 6;
      this.ctx.shadowOffsetY = 4;

      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);

      if (edge.is_bridge) {
        this.ctx.lineWidth = edge.is_destroyed ? 3.5 : 5;
        this.ctx.strokeStyle = edge.is_destroyed ? "#f85149" : (isMst ? "#58a6ff" : "#e3b341");
        this.ctx.setLineDash(edge.is_destroyed ? [4, 5] : [8, 4]);
        this.ctx.stroke();
        this.ctx.setLineDash([]);
      } else if (isMst) {
        this.ctx.shadowColor = "#58a6ff";
        this.ctx.shadowBlur = 12;
        this.ctx.shadowOffsetY = 0;
        this.ctx.lineWidth = 4.5;
        this.ctx.strokeStyle = "#58a6ff";
        this.ctx.stroke();
      } else if (isFootOnly) {
        this.ctx.lineWidth = 2.5;
        this.ctx.strokeStyle = "#2ea043";
        this.ctx.setLineDash([3, 4]);
        this.ctx.stroke();
        this.ctx.setLineDash([]);
      } else {
        this.ctx.lineWidth = 3;
        this.ctx.strokeStyle = "rgba(121, 192, 255, 0.65)";
        this.ctx.stroke();
      }
      this.ctx.restore();

      if (this.showEdgeLabels) {
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const len = Math.hypot(dx, dy) || 1;
        const nx = (dy / len) * 11;
        const ny = (-dx / len) * 11;
        const labelX = (p1.x + p2.x) / 2 + nx;
        const labelY = (p1.y + p2.y) / 2 + ny;

        if (edge.is_bridge) {
          const text = edge.is_destroyed
            ? (edge.is_reconstructing ? `🔧 ${edge.reconstruction_timer}s` : `💥 CAÍDO`)
            : `🌉 ${edge.current_resistance}/${edge.max_resistance}`;
          this._drawPillLabel(text, labelX, labelY, {
            font: "bold 9px monospace",
            textColor: edge.is_destroyed ? "#ffa198" : "#ffdf5d",
            borderColor: edge.is_destroyed ? "rgba(248, 81, 73, 0.8)" : "rgba(210, 153, 34, 0.7)",
            height: 15,
          });
        } else if (isFootOnly) {
          this._drawPillLabel(`🚶 ${edge.foot_time}s`, labelX, labelY, {
            font: "9px monospace",
            textColor: "#7ee787",
            borderColor: "rgba(63, 185, 80, 0.6)",
            height: 14,
            padX: 4,
          });
        } else if (isMst) {
          this._drawPillLabel(`🌲 ${edge.foot_time}s`, labelX, labelY, {
            font: "bold 9px monospace",
            textColor: "#a5d6ff",
            borderColor: "rgba(88, 166, 255, 0.7)",
            height: 14,
            padX: 4,
          });
        }
      }
    }
  }

  drawActiveTowerRadii() {
    const beta = this.scenarioData?.config?.beta_elevation ?? 0.1;

    if (this.showSurveillanceRanges && this.towerSelectionResult?.selected_towers) {
      for (const tower of this.towerSelectionResult.selected_towers) {
        const pos = this.worldToScreen(tower.x, tower.y);
        const radiusScreen = tower.surveillance_radius * this.scale;

        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.arc(pos.x, pos.y, radiusScreen, 0, Math.PI * 2);
        this.ctx.fillStyle = "rgba(63, 185, 80, 0.045)";
        this.ctx.fill();
        this.ctx.lineWidth = 1.25;
        this.ctx.strokeStyle = "rgba(63, 185, 80, 0.32)";
        this.ctx.setLineDash([5, 5]);
        this.ctx.stroke();
        this.ctx.setLineDash([]);
        this.ctx.restore();
      }
    }

    if (this.showAttackRanges && this.soldiers.length > 0) {
      const soldierMap = new Map(this.soldiers.map((s) => [s.id, s]));
      for (const node of this.scenarioData.elevated_network?.nodes || []) {
        if (!node.is_active_tower || node.type === "Base") continue;
        const stationed = node.stationed_soldiers || [];
        if (stationed.length === 0) continue;

        const pos = this.worldToScreen(node.x, node.y);
        for (const sId of stationed) {
          const s = soldierMap.get(sId);
          if (!s) continue;
          const stats = SOLDIER_BASE_STATS[s.type] || SOLDIER_BASE_STATS["Infantería"];
          const rEf = stats.baseRange * (1.0 + beta * Math.max(0, node.z || 0));
          const rScreen = rEf * this.scale;

          this.ctx.save();
          this.ctx.beginPath();
          this.ctx.arc(pos.x, pos.y, rScreen, 0, Math.PI * 2);
          this.ctx.fillStyle = "rgba(88, 166, 255, 0.06)";
          this.ctx.fill();
          this.ctx.lineWidth = 1.4;
          this.ctx.strokeStyle = stats.color;
          this.ctx.setLineDash([3, 3]);
          this.ctx.stroke();
          this.ctx.restore();
        }
      }
    }
  }

  drawMazeNodes() {
    for (const node of this.scenarioData.maze_network?.nodes || []) {
      const p = this.worldToScreen(node.x, node.y);

      this.ctx.save();
      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, node.is_entry || node.is_exit ? 10 : 6.5, 0, Math.PI * 2);

      if (node.is_entry) {
        this.ctx.fillStyle = "#238636";
        this.ctx.fill();
        this.ctx.strokeStyle = "#7ee787";
        this.ctx.lineWidth = 2.5;
        this.ctx.stroke();
        this.ctx.restore();
        this._drawPillLabel(`IN (${node.id})`, p.x, p.y + 20, {
          font: "bold 10px sans-serif",
          textColor: "#7ee787",
          borderColor: "#3fb950",
        });
      } else if (node.is_exit) {
        this.ctx.fillStyle = "#b62324";
        this.ctx.fill();
        this.ctx.strokeStyle = "#ffa198";
        this.ctx.lineWidth = 2.5;
        this.ctx.stroke();
        this.ctx.restore();
        this._drawPillLabel(`OUT (${node.id})`, p.x, p.y + 20, {
          font: "bold 10px sans-serif",
          textColor: "#ffa198",
          borderColor: "#f85149",
        });
      } else {
        this.ctx.fillStyle = "#21262d";
        this.ctx.fill();
        this.ctx.strokeStyle = "#8b949e";
        this.ctx.lineWidth = 1.5;
        this.ctx.stroke();
        this.ctx.restore();
        this._drawPillLabel(node.id, p.x, p.y + 15, {
          font: "9px monospace",
          textColor: "#8b949e",
          borderColor: "rgba(48, 54, 61, 0.7)",
          height: 14,
          padX: 4,
        });
      }
    }
  }

  drawElevatedNodes() {
    const activeTowerIds = new Set(
      (this.towerSelectionResult?.selected_towers || []).map((t) => t.tower_id)
    );
    const towerScoreMap = new Map(
      (this.towerSelectionResult?.selected_towers || []).map((t) => [t.tower_id, t.score])
    );

    for (const node of this.scenarioData.elevated_network?.nodes || []) {
      const p = this.worldToScreen(node.x, node.y);
      const isSelectedTower =
        activeTowerIds.has(node.id) || (node.type === "Candidato" && node.is_active_tower);

      this.ctx.save();
      this.ctx.shadowColor = "rgba(0, 0, 0, 0.7)";
      this.ctx.shadowBlur = 6;
      this.ctx.shadowOffsetY = 3;

      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, isSelectedTower ? 13 : 10, 0, Math.PI * 2);

      if (node.type === "Base") {
        this.ctx.fillStyle = "#238636";
        this.ctx.fill();
        this.ctx.strokeStyle = "#7ee787";
        this.ctx.lineWidth = 2.5;
        this.ctx.stroke();
        this.ctx.restore();
        this._drawPillLabel(`★ BASE`, p.x, p.y - 20, {
          font: "bold 10px sans-serif",
          textColor: "#7ee787",
          borderColor: "#3fb950",
        });
      } else if (node.type === "Helipuerto") {
        this.ctx.fillStyle = "#6e40c9";
        this.ctx.fill();
        this.ctx.strokeStyle = "#d2a8ff";
        this.ctx.lineWidth = 2.5;
        this.ctx.stroke();
        this.ctx.restore();
        this._drawPillLabel(`🚁 ${node.id}`, p.x, p.y - 20, {
          font: "bold 10px sans-serif",
          textColor: "#d2a8ff",
          borderColor: "#bc8cff",
        });
      } else if (node.type === "Candidato") {
        if (isSelectedTower) {
          this.ctx.fillStyle = "#d29922";
          this.ctx.fill();
          this.ctx.strokeStyle = "#f0883e";
          this.ctx.lineWidth = 3;
          this.ctx.stroke();
          this.ctx.restore();

          const occ = (node.stationed_soldiers || []).length;
          const res = node.reserved_slots || 0;
          const occLabel = res > 0 ? `${occ}+${res}/3` : `${occ}/3`;
          const scoreVal = towerScoreMap.get(node.id);
          const lbl = scoreVal !== undefined ? `🗼 ${node.id} [${occLabel}]` : `🗼 ${node.id} [${occLabel}]`;

          this._drawPillLabel(lbl, p.x, p.y + 22, {
            font: "bold 10px sans-serif",
            textColor: "#ffdf5d",
            borderColor: "#f0883e",
          });
        } else {
          this.ctx.fillStyle = "#161b22";
          this.ctx.fill();
          this.ctx.strokeStyle = "#d29922";
          this.ctx.lineWidth = 2;
          this.ctx.setLineDash([3, 3]);
          this.ctx.stroke();
          this.ctx.setLineDash([]);
          this.ctx.restore();
          this._drawPillLabel(node.id, p.x, p.y + 18, {
            font: "10px sans-serif",
            textColor: "#e3b341",
            borderColor: "rgba(210, 153, 34, 0.6)",
            height: 15,
          });
        }
      } else {
        this.ctx.fillStyle = "#1f6feb";
        this.ctx.fill();
        this.ctx.strokeStyle = "#79c0ff";
        this.ctx.lineWidth = 2;
        this.ctx.stroke();
        this.ctx.restore();
        this._drawPillLabel(node.id, p.x, p.y - 17, {
          font: "9px monospace",
          textColor: "#a5d6ff",
          borderColor: "rgba(88, 166, 255, 0.55)",
          height: 14,
          padX: 4,
        });
      }
    }
  }

  // Backward-compatible alias if any test calls drawNodes()
  drawNodes() {
    this.drawMazeNodes();
    this.drawElevatedNodes();
  }

  drawStationedSoldiers() {
    if (!this.soldiers || this.soldiers.length === 0) return;

    const soldierMap = new Map(this.soldiers.map((s) => [s.id, s]));
    const offsets = [
      { dx: -17, dy: -16 },
      { dx: 17, dy: -16 },
      { dx: 0, dy: -24 },
    ];

    for (const node of this.scenarioData.elevated_network?.nodes || []) {
      const stationed = node.stationed_soldiers || [];
      if (stationed.length === 0) continue;

      const center = this.worldToScreen(node.x, node.y);
      stationed.forEach((sId, idx) => {
        const s = soldierMap.get(sId);
        if (!s) return;
        const stats = SOLDIER_BASE_STATS[s.type] || SOLDIER_BASE_STATS["Infantería"];
        const off = offsets[idx % offsets.length];
        const sx = center.x + off.dx;
        const sy = center.y + off.dy;

        this.ctx.save();
        this.ctx.fillStyle = stats.color;
        this.ctx.strokeStyle = "#0d1117";
        this.ctx.lineWidth = 1.5;

        if (s.type === "Francotirador") {
          this.ctx.beginPath();
          this.ctx.moveTo(sx, sy - 7);
          this.ctx.lineTo(sx + 7, sy);
          this.ctx.lineTo(sx, sy + 7);
          this.ctx.lineTo(sx - 7, sy);
          this.ctx.closePath();
          this.ctx.fill();
          this.ctx.stroke();
        } else if (s.type === "Artillero") {
          this.ctx.fillRect(sx - 6, sy - 6, 12, 12);
          this.ctx.strokeRect(sx - 6, sy - 6, 12, 12);
        } else {
          this.ctx.beginPath();
          this.ctx.arc(sx, sy, 6, 0, Math.PI * 2);
          this.ctx.fill();
          this.ctx.stroke();
        }

        this.ctx.fillStyle = "#ffffff";
        this.ctx.font = "bold 8px sans-serif";
        this.ctx.textAlign = "center";
        this.ctx.textBaseline = "middle";
        this.ctx.fillText(stats.shortLabel, sx, sy);
        this.ctx.restore();
      });
    }
  }

  drawTransportMissions() {
    if (!this.missions || this.missions.length === 0) return;

    for (const m of this.missions) {
      if (m.is_completed) continue;

      const pos = this.worldToScreen(m.current_x || 0, m.current_y || 0);
      this.ctx.save();

      if (m.type === "Helicóptero") {
        if (Array.isArray(m.legs) && m.legs.length > 0) {
          this.ctx.beginPath();
          this.ctx.strokeStyle = "rgba(188, 140, 255, 0.75)";
          this.ctx.lineWidth = 2;
          this.ctx.setLineDash([5, 4]);
          for (const leg of m.legs) {
            const pFrom = this.worldToScreen(leg.from_pos[0], leg.from_pos[1]);
            const pTo = this.worldToScreen(leg.to_pos[0], leg.to_pos[1]);
            this.ctx.moveTo(pFrom.x, pFrom.y);
            this.ctx.lineTo(pTo.x, pTo.y);
          }
          this.ctx.stroke();
          this.ctx.setLineDash([]);
        }

        this.ctx.strokeStyle = "#d2a8ff";
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();
        this.ctx.moveTo(pos.x - 11, pos.y - 11);
        this.ctx.lineTo(pos.x + 11, pos.y + 11);
        this.ctx.moveTo(pos.x + 11, pos.y - 11);
        this.ctx.lineTo(pos.x - 11, pos.y + 11);
        this.ctx.stroke();

        this.ctx.beginPath();
        this.ctx.arc(pos.x, pos.y, 7.5, 0, Math.PI * 2);
        this.ctx.fillStyle = "#6e40c9";
        this.ctx.fill();
        this.ctx.strokeStyle = "#ffffff";
        this.ctx.lineWidth = 1.5;
        this.ctx.stroke();
        this.ctx.restore();

        this._drawPillLabel(`🚁 x${m.soldier_ids.length}`, pos.x, pos.y - 18, {
          font: "bold 9px monospace",
          textColor: "#d2a8ff",
          borderColor: "#bc8cff",
          height: 15,
        });
      } else {
        const isMoto = m.type === "Moto";
        this.ctx.beginPath();
        this.ctx.arc(pos.x, pos.y, 7.5, 0, Math.PI * 2);
        this.ctx.fillStyle = m.is_blocked ? "#f85149" : (isMoto ? "#f0883e" : "#3fb950");
        this.ctx.fill();
        this.ctx.strokeStyle = "#ffffff";
        this.ctx.lineWidth = 1.5;
        this.ctx.stroke();
        this.ctx.restore();

        const tag = m.is_blocked ? "⏸ BLOQ" : `${isMoto ? "🏍" : "🚶"}x${m.soldier_ids.length}`;
        this._drawPillLabel(tag, pos.x, pos.y - 16, {
          font: "bold 9px sans-serif",
          textColor: "#ffffff",
          borderColor: m.is_blocked ? "#f85149" : "#f0883e",
          height: 15,
        });
      }
    }
  }

  drawConvoyTrail() {
    if (!this.convoyState) return;

    const nodeMap = new Map(
      (this.scenarioData.maze_network?.nodes || []).map((n) => [n.id, n])
    );

    const traversedEdges = this.convoyState.history?.traversed_edges || [];
    if (traversedEdges.length > 0) {
      this.ctx.save();
      this.ctx.lineWidth = 4.5;
      this.ctx.strokeStyle = "#a371f7";
      this.ctx.lineCap = "round";
      this.ctx.lineJoin = "round";

      for (const edge of traversedEdges) {
        const u = nodeMap.get(edge[0]);
        const v = nodeMap.get(edge[1]);
        if (!u || !v) continue;

        const p1 = this.worldToScreen(u.x, u.y);
        const p2 = this.worldToScreen(v.x, v.y);

        this.ctx.beginPath();
        this.ctx.moveTo(p1.x, p1.y);
        this.ctx.lineTo(p2.x, p2.y);
        this.ctx.stroke();

        const arrowX = p1.x + (p2.x - p1.x) * 0.6;
        const arrowY = p1.y + (p2.y - p1.y) * 0.6;
        const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);

        this.ctx.fillStyle = "#d2a8ff";
        this.ctx.beginPath();
        this.ctx.moveTo(arrowX, arrowY);
        this.ctx.lineTo(arrowX - 8 * Math.cos(angle - Math.PI / 6), arrowY - 8 * Math.sin(angle - Math.PI / 6));
        this.ctx.lineTo(arrowX - 8 * Math.cos(angle + Math.PI / 6), arrowY - 8 * Math.sin(angle + Math.PI / 6));
        this.ctx.closePath();
        this.ctx.fill();
      }
      this.ctx.restore();
    }

    const projectedPath = this.convoyState.projected_path || [];
    if (projectedPath.length > 1) {
      this.ctx.save();
      this.ctx.lineWidth = 3;
      this.ctx.strokeStyle = "#58a6ff";
      this.ctx.setLineDash([7, 5]);
      this.ctx.shadowColor = "#58a6ff";
      this.ctx.shadowBlur = 6;

      this.ctx.beginPath();
      for (let i = 0; i < projectedPath.length - 1; i++) {
        const u = nodeMap.get(projectedPath[i]);
        const v = nodeMap.get(projectedPath[i + 1]);
        if (!u || !v) continue;
        const p1 = this.worldToScreen(u.x, u.y);
        const p2 = this.worldToScreen(v.x, v.y);
        this.ctx.moveTo(p1.x, p1.y);
        this.ctx.lineTo(p2.x, p2.y);
      }
      this.ctx.stroke();
      this.ctx.restore();
    }
  }

  _getConvoyScreenPos() {
    if (!this.convoyState) return null;
    if (this.convoyState.x !== undefined && this.convoyState.y !== undefined && this.convoyState.x !== null) {
      return this.worldToScreen(this.convoyState.x, this.convoyState.y);
    }
    if (!this.convoyState.current_node) return null;
    const node = (this.scenarioData.maze_network?.nodes || []).find(
      (n) => n.id === this.convoyState.current_node
    );
    return node ? this.worldToScreen(node.x, node.y) : null;
  }

  drawConvoyToken() {
    const p = this._getConvoyScreenPos();
    if (!p) return;

    this.ctx.save();

    this.ctx.beginPath();
    this.ctx.arc(p.x, p.y, 19, 0, Math.PI * 2);
    this.ctx.strokeStyle = "rgba(188, 140, 255, 0.65)";
    this.ctx.lineWidth = 2;
    this.ctx.stroke();

    this.ctx.beginPath();
    this.ctx.arc(p.x, p.y, 12.5, 0, Math.PI * 2);
    this.ctx.fillStyle = "#6e40c9";
    this.ctx.fill();
    this.ctx.strokeStyle = "#d2a8ff";
    this.ctx.lineWidth = 2.5;
    this.ctx.shadowColor = "#bc8cff";
    this.ctx.shadowBlur = 10;
    this.ctx.stroke();
    this.ctx.shadowBlur = 0;

    this.ctx.fillStyle = "#ffffff";
    this.ctx.font = "bold 11px sans-serif";
    this.ctx.textAlign = "center";
    this.ctx.textBaseline = "middle";
    this.ctx.fillText("C", p.x, p.y);

    const hp = this.convoyState.hp !== undefined ? this.convoyState.hp : (this.convoyState.convoy_status?.total_hp || 0);
    const maxHp = this.convoyState.max_hp !== undefined ? this.convoyState.max_hp : (this.convoyState.convoy_status?.max_total_hp || 350);
    const ratio = maxHp > 0 ? Math.max(0, Math.min(1, hp / maxHp)) : 0;

    const barW = 46;
    const barH = 6;
    const barX = p.x - barW / 2;
    const barY = p.y - 26;

    this.ctx.fillStyle = "#0d1117";
    this.ctx.fillRect(barX, barY, barW, barH);
    this.ctx.strokeStyle = "#30363d";
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(barX, barY, barW, barH);

    let hpColor = "#3fb950";
    if (ratio <= 0.25) hpColor = "#f85149";
    else if (ratio <= 0.5) hpColor = "#d29922";

    this.ctx.fillStyle = hpColor;
    this.ctx.fillRect(barX, barY, barW * ratio, barH);
    this.ctx.restore();

    this._drawPillLabel(`${Math.round(hp)}/${Math.round(maxHp)} HP`, p.x, barY - 10, {
      font: "bold 9px monospace",
      textColor: "#f0f6fc",
      borderColor: hpColor,
      height: 14,
      padX: 5,
    });

    if (this.convoyState.is_finished) {
      if (this.convoyState.game_result === "Victoria por eliminación" || this.convoyState.destroyed) {
        this._drawPillLabel("🏆 VICTORIA POR ELIMINACIÓN", p.x, p.y + 26, {
          font: "bold 11px sans-serif",
          textColor: "#7ee787",
          borderColor: "#3fb950",
          height: 20,
        });
      } else if (this.convoyState.game_result === "Victoria por resistencia") {
        this._drawPillLabel("🏆 VICTORIA POR RESISTENCIA", p.x, p.y + 26, {
          font: "bold 11px sans-serif",
          textColor: "#7ee787",
          borderColor: "#3fb950",
          height: 20,
        });
      } else if (this.convoyState.escaped) {
        this._drawPillLabel("💀 DERROTA (CONVOY ESCAPÓ)", p.x, p.y + 26, {
          font: "bold 11px sans-serif",
          textColor: "#ffa198",
          borderColor: "#f85149",
          height: 20,
        });
      }
    }
  }

  drawCombatEffects() {
    if (!this.lastCombat || !Array.isArray(this.lastCombat.attacks) || this.lastCombat.attacks.length === 0) {
      return;
    }

    const convoyPos = this._getConvoyScreenPos();
    if (!convoyPos) return;

    const nodeMap = new Map(
      (this.scenarioData.elevated_network?.nodes || []).map((n) => [n.id, n])
    );

    this.ctx.save();
    for (const atk of this.lastCombat.attacks) {
      const tower = nodeMap.get(atk.tower_id);
      if (!tower) continue;

      const tPos = this.worldToScreen(tower.x, tower.y);
      const stats = SOLDIER_BASE_STATS[atk.soldier_type] || SOLDIER_BASE_STATS["Infantería"];

      this.ctx.beginPath();
      this.ctx.moveTo(tPos.x, tPos.y);
      this.ctx.lineTo(convoyPos.x, convoyPos.y);
      this.ctx.strokeStyle = stats.color;
      this.ctx.lineWidth = atk.is_area ? 3 : 2;
      this.ctx.shadowColor = stats.color;
      this.ctx.shadowBlur = 10;
      this.ctx.stroke();
      this.ctx.shadowBlur = 0;

      if (atk.is_area) {
        this.ctx.beginPath();
        this.ctx.arc(convoyPos.x, convoyPos.y, 26, 0, Math.PI * 2);
        this.ctx.strokeStyle = "rgba(248, 81, 73, 0.85)";
        this.ctx.lineWidth = 2;
        this.ctx.stroke();
      }
    }
    this.ctx.restore();
  }

  drawAntiBacktracking() {
    if (!this.convoyState || !this.convoyState.decision) return;

    const decision = this.convoyState.decision;
    const nodeMap = new Map(
      (this.scenarioData.maze_network?.nodes || []).map((n) => [n.id, n])
    );

    this.ctx.save();

    if (decision.type === "ANTI_BACKTRACK_AVOIDED") {
      const discNodeId = decision.discarded_node;
      const prevNodeId = this.convoyState.previous_node || this.convoyState.current_node;
      const uNode = nodeMap.get(prevNodeId);
      const vNode = nodeMap.get(discNodeId);

      if (uNode && vNode) {
        const p1 = this.worldToScreen(uNode.x, uNode.y);
        const p2 = this.worldToScreen(vNode.x, vNode.y);

        this.ctx.beginPath();
        this.ctx.moveTo(p1.x, p1.y);
        this.ctx.lineTo(p2.x, p2.y);
        this.ctx.strokeStyle = "#f85149";
        this.ctx.lineWidth = 4;
        this.ctx.setLineDash([4, 4]);
        this.ctx.stroke();
        this.ctx.setLineDash([]);

        this._drawPillLabel("⛔ NO RETROCESO", (p1.x + p2.x) / 2, (p1.y + p2.y) / 2, {
          font: "bold 10px sans-serif",
          textColor: "#ffffff",
          bgColor: "rgba(248, 81, 73, 0.95)",
          borderColor: "#ffffff",
          height: 18,
        });
      }

      const chosenNodeId = decision.chosen_next_node;
      const origNode = nodeMap.get(prevNodeId);
      const chosenNode = nodeMap.get(chosenNodeId);

      if (origNode && chosenNode) {
        const p1 = this.worldToScreen(origNode.x, origNode.y);
        const p2 = this.worldToScreen(chosenNode.x, chosenNode.y);

        this.ctx.beginPath();
        this.ctx.moveTo(p1.x, p1.y);
        this.ctx.lineTo(p2.x, p2.y);
        this.ctx.strokeStyle = "#f0883e";
        this.ctx.lineWidth = 4.5;
        this.ctx.shadowColor = "#f0883e";
        this.ctx.shadowBlur = 12;
        this.ctx.stroke();
        this.ctx.shadowBlur = 0;

        this._drawPillLabel("✓ DESVÍO ÓPTIMO", (p1.x + p2.x) / 2, (p1.y + p2.y) / 2, {
          font: "bold 9px sans-serif",
          textColor: "#ffffff",
          bgColor: "rgba(240, 136, 62, 0.95)",
          borderColor: "#ffffff",
          height: 16,
        });
      }
    } else if (decision.type === "FORCED_DEAD_END_BACKTRACK") {
      const currNode = nodeMap.get(this.convoyState.current_node);
      if (currNode) {
        const p = this.worldToScreen(currNode.x, currNode.y);
        this._drawPillLabel("⚠️ CALLEJÓN SIN SALIDA (Retroceso Forzado)", p.x, p.y + 32, {
          font: "bold 10px sans-serif",
          textColor: "#ffffff",
          bgColor: "rgba(210, 153, 34, 0.95)",
          borderColor: "#ffffff",
          height: 20,
        });
      }
    }

    this.ctx.restore();
  }

  drawHoverTooltip() {
    if (!this.hoverItem || !this.hoverPos) return;

    const lines = [];
    const item = this.hoverItem;

    if (item.kind === "elevated_node") {
      const n = item.data;
      lines.push(`Elevado: ${n.id} (${n.type})`);
      lines.push(`Posición: (${n.x}, ${n.y}) | Altura z=${n.z}`);
      if (n.type === "Candidato") {
        lines.push(`Vigilancia R_V: ${n.surveillance_radius} | Activa: ${n.is_active_tower ? "Sí" : "No"}`);
        lines.push(`Ocupación: ${(n.stationed_soldiers || []).length} apostados, ${n.reserved_slots || 0} en camino (máx 3)`);
      }
    } else if (item.kind === "maze_node") {
      const n = item.data;
      const role = n.is_entry ? "ENTRADA" : n.is_exit ? "SALIDA" : "Intersección";
      lines.push(`Laberinto: ${n.id} (${role})`);
      lines.push(`Coordenadas: (${n.x}, ${n.y})`);
    } else if (item.kind === "elevated_edge") {
      const e = item.data;
      lines.push(`Conexión G_E: ${e.u} ↔ ${e.v}`);
      lines.push(`A pie: ${e.foot_time !== null ? e.foot_time + "s" : "No permitido"} | Moto: ${e.moto_time !== null ? e.moto_time + "s" : "No permitido"}`);
      if (e.is_bridge) {
        lines.push(`Puente: ${e.current_resistance}/${e.max_resistance} | Operarios: ${e.repair_personnel}`);
        if (e.is_destroyed) {
          lines.push(`Estado: CAÍDO (resta ${e.reconstruction_timer}s)`);
        }
      }
    } else if (item.kind === "maze_corridor") {
      const c = item.data;
      const h = item.hazard;
      lines.push(`Corredor G_M: ${c.u} ↔ ${c.v}`);
      lines.push(`Long: ${c.length} | Vel: ${c.speed} | t(e): ${c.base_time}s`);
      if (h) {
        lines.push(`Peligro D̄(e): ${h.avg_danger} | Daño pot P(e): ${h.danger_potential}`);
        lines.push(`Peso reactivo w(e): ${h.reactive_weight}s`);
        lines.push(`Puntos: ini=${h.q_ini.damage_rate}, mid=${h.q_mid.damage_rate}, fin=${h.q_end.damage_rate}`);
      }
    }

    if (lines.length === 0) return;

    this.ctx.save();
    this.ctx.font = "11px monospace";
    let maxW = 0;
    for (const ln of lines) {
      maxW = Math.max(maxW, this.ctx.measureText(ln).width);
    }

    const boxW = maxW + 18;
    const lineH = 16;
    const boxH = lines.length * lineH + 12;

    let tx = this.hoverPos.x + 14;
    let ty = this.hoverPos.y + 14;
    if (tx + boxW > this.width - 10) tx = this.hoverPos.x - boxW - 14;
    if (ty + boxH > this.height - 10) ty = this.hoverPos.y - boxH - 14;

    this.ctx.fillStyle = "rgba(13, 17, 23, 0.94)";
    this.ctx.strokeStyle = "#58a6ff";
    this.ctx.lineWidth = 1;
    this.ctx.beginPath();
    if (typeof this.ctx.roundRect === "function") {
      this.ctx.roundRect(tx, ty, boxW, boxH, 6);
    } else {
      this.ctx.rect(tx, ty, boxW, boxH);
    }
    this.ctx.fill();
    this.ctx.stroke();

    this.ctx.textAlign = "left";
    this.ctx.textBaseline = "top";
    lines.forEach((ln, idx) => {
      this.ctx.fillStyle = idx === 0 ? "#79c0ff" : "#e6edf3";
      this.ctx.font = idx === 0 ? "bold 11px monospace" : "10.5px monospace";
      this.ctx.fillText(ln, tx + 9, ty + 7 + idx * lineH);
    });
    this.ctx.restore();
  }
}

window.Renderer2D = Renderer2D;
