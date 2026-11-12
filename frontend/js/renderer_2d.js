/**
 * 2D Canvas renderer for Elevated Network (G_E) and Maze Network (G_M).
 * Incorporates Stage 3 Corridor Hazard Heatmap, 3 Sampling Points (q_ini, q_mid, q_end),
 * Reactive Convoy Navigation Trail, and Anti-Backtracking Markers.
 */

class Renderer2D {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.scenarioData = null;
    this.mstResult = null;
    this.towerSelectionResult = null;

    // Stage 3 Simulation & Reactive Navigation State
    this.corridorHazards = null;
    this.convoyState = null;
    this.showHeatmap = true;
    this.showEvalPoints = true;
    this.maxDanger = 30.0;

    // Viewport transform params
    this.padding = 60;
    this.scale = 1.0;
    this.offsetX = 0;
    this.offsetY = 0;

    this.resizeCanvas();
    window.addEventListener("resize", () => {
      this.resizeCanvas();
      this.render();
    });
  }

  resizeCanvas() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
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

  getHazardForCorridor(u, v) {
    if (!this.corridorHazards) return null;
    return this.corridorHazards[`${u}-${v}`] || this.corridorHazards[`${v}-${u}`] || null;
  }

  calculateTransform() {
    if (!this.scenarioData) return;

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

    const availableWidth = this.width - this.padding * 2;
    const availableHeight = this.height - this.padding * 2;

    const scaleX = availableWidth / worldWidth;
    const scaleY = availableHeight / worldHeight;
    this.scale = Math.min(scaleX, scaleY, 1.8);

    const scaledWidth = worldWidth * this.scale;
    const scaledHeight = worldHeight * this.scale;

    this.offsetX = (this.width - scaledWidth) / 2 - minX * this.scale;
    this.offsetY = (this.height - scaledHeight) / 2 - minY * this.scale;
  }

  worldToScreen(x, y) {
    return {
      x: x * this.scale + this.offsetX,
      y: y * this.scale + this.offsetY,
    };
  }

  render() {
    this.ctx.clearRect(0, 0, this.width, this.height);

    if (!this.scenarioData) {
      this.drawEmptyState();
      return;
    }

    this.drawBackgroundGrid();
    this.drawMazeNetwork();
    this.drawElevatedNetwork();
    this.drawActiveTowerRadii();
    this.drawConvoyTrail();
    this.drawNodes();
    this.drawAntiBacktracking();
    this.drawConvoyToken();
  }

  drawEmptyState() {
    this.ctx.fillStyle = "#8b949e";
    this.ctx.font = "16px sans-serif";
    this.ctx.textAlign = "center";
    this.ctx.fillText("No hay escenario cargado. Carga un archivo para comenzar.", this.width / 2, this.height / 2);
  }

  drawBackgroundGrid() {
    this.ctx.strokeStyle = "rgba(48, 54, 61, 0.35)";
    this.ctx.lineWidth = 1;
    const gridSize = 40 * this.scale;

    this.ctx.beginPath();
    for (let x = this.offsetX % gridSize; x < this.width; x += gridSize) {
      this.ctx.moveTo(x, 0);
      this.ctx.lineTo(x, this.height);
    }
    for (let y = this.offsetY % gridSize; y < this.height; y += gridSize) {
      this.ctx.moveTo(0, y);
      this.ctx.lineTo(this.width, y);
    }
    this.ctx.stroke();
  }

  drawMazeNetwork() {
    const corridors = this.scenarioData.maze_network?.corridors || [];
    const nodeMap = new Map();
    for (const n of this.scenarioData.maze_network?.nodes || []) {
      nodeMap.set(n.id, n);
    }

    const watchedSet = new Set(this.towerSelectionResult?.watched_corridors || []);

    // Draw corridors
    for (const corr of corridors) {
      const u = nodeMap.get(corr.u);
      const v = nodeMap.get(corr.v);
      if (!u || !v) continue;

      const p1 = this.worldToScreen(u.x, u.y);
      const p2 = this.worldToScreen(v.x, v.y);

      const keyCanonical1 = `${corr.u}-${corr.v}`;
      const keyCanonical2 = `${corr.v}-${corr.u}`;
      const isWatched = watchedSet.has(keyCanonical1) || watchedSet.has(keyCanonical2);

      const hazard = this.getHazardForCorridor(corr.u, corr.v);

      // Determine color ramp styling based on reactive danger
      let baseStroke = isWatched ? "rgba(63, 185, 80, 0.35)" : "rgba(110, 118, 129, 0.4)";
      let innerStroke = isWatched ? "#3fb950" : "#484f58";
      let hasLethalGlow = false;
      const avgDanger = hazard?.avg_danger || 0.0;

      if (this.showHeatmap && hazard) {
        if (avgDanger <= 0) {
          baseStroke = isWatched ? "rgba(63, 185, 80, 0.35)" : "rgba(110, 118, 129, 0.4)";
          innerStroke = isWatched ? "#3fb950" : "#484f58";
        } else if (avgDanger <= 10) {
          baseStroke = "rgba(210, 153, 34, 0.45)";
          innerStroke = "#d29922";
        } else if (avgDanger <= 25) {
          baseStroke = "rgba(240, 136, 62, 0.55)";
          innerStroke = "#f0883e";
        } else {
          baseStroke = "rgba(248, 81, 73, 0.75)";
          innerStroke = "#f85149";
          hasLethalGlow = true;
        }
      }

      // Corridor base track
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);
      this.ctx.lineWidth = isWatched ? 10 : 8;
      this.ctx.strokeStyle = baseStroke;
      this.ctx.lineCap = "round";
      if (hasLethalGlow) {
        this.ctx.shadowColor = "#f85149";
        this.ctx.shadowBlur = 8;
      }
      this.ctx.stroke();
      if (hasLethalGlow) {
        this.ctx.shadowBlur = 0;
      }

      // Inner corridor line
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);
      this.ctx.lineWidth = 3.5;
      this.ctx.strokeStyle = innerStroke;
      this.ctx.stroke();

      // Draw the 3 key sampling points (q_ini, q_mid, q_end)
      if (this.showEvalPoints && hazard) {
        const evalPoints = [
          { pt: hazard.q_ini, name: "q_ini" },
          { pt: hazard.q_mid, name: "q_mid" },
          { pt: hazard.q_end, name: "q_end" },
        ];

        for (const ep of evalPoints) {
          if (!ep.pt || ep.pt.x === undefined || ep.pt.y === undefined) continue;
          const qScreen = this.worldToScreen(ep.pt.x, ep.pt.y);
          const dmg = ep.pt.damage_rate || 0;

          this.ctx.beginPath();
          this.ctx.arc(qScreen.x, qScreen.y, 3.5, 0, Math.PI * 2);

          if (dmg === 0) {
            this.ctx.fillStyle = "rgba(63, 185, 80, 0.7)";
            this.ctx.fill();
            this.ctx.strokeStyle = "#2ea043";
            this.ctx.lineWidth = 1;
            this.ctx.stroke();
          } else if (dmg <= 20) {
            this.ctx.fillStyle = "#d29922";
            this.ctx.fill();
            this.ctx.strokeStyle = "#ffffff";
            this.ctx.lineWidth = 1;
            this.ctx.stroke();
          } else {
            this.ctx.fillStyle = "#f85149";
            this.ctx.shadowColor = "#f85149";
            this.ctx.shadowBlur = 4;
            this.ctx.fill();
            this.ctx.shadowBlur = 0;
            this.ctx.strokeStyle = "#ffffff";
            this.ctx.lineWidth = 1;
            this.ctx.stroke();
          }
        }
      }

      // Corridor midpoint label
      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;
      this.ctx.textAlign = "center";

      if (hazard) {
        this.ctx.font = "bold 10px monospace";
        this.ctx.fillStyle = avgDanger > 25 ? "#ffa198" : (avgDanger > 0 ? "#ffdf5d" : (isWatched ? "#7ee787" : "#8b949e"));
        let label = `w:${hazard.reactive_weight}s [D̄:${hazard.avg_danger} | t:${hazard.base_time}s]`;
        if (hazard.has_artillery) {
          label += ` 💥[ART]`;
        }
        this.ctx.fillText(label, midX, midY - 6);
      } else {
        this.ctx.fillStyle = isWatched ? "#7ee787" : "#8b949e";
        this.ctx.font = "10px monospace";
        this.ctx.fillText(`L:${corr.length} (v:${corr.speed})`, midX, midY - 6);
      }
    }
  }

  drawElevatedNetwork() {
    const edges = this.scenarioData.elevated_network?.edges || [];
    const nodeMap = new Map();
    for (const n of this.scenarioData.elevated_network?.nodes || []) {
      nodeMap.set(n.id, n);
    }

    // Set of canonical MST edge keys
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

      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);

      if (isMst) {
        // Glowing MST edge
        this.ctx.lineWidth = 5;
        this.ctx.strokeStyle = "#58a6ff";
        this.ctx.setLineDash([]);
        this.ctx.shadowColor = "#58a6ff";
        this.ctx.shadowBlur = 10;
        this.ctx.stroke();
        this.ctx.shadowBlur = 0; // reset
      } else if (edge.is_bridge) {
        // Bridge representation
        this.ctx.lineWidth = 4;
        this.ctx.strokeStyle = edge.is_destroyed ? "#f85149" : "#d29922";
        this.ctx.setLineDash([6, 4]);
        this.ctx.stroke();
        this.ctx.setLineDash([]);
      } else {
        // Standard elevated walkway
        this.ctx.lineWidth = 2.5;
        this.ctx.strokeStyle = "rgba(88, 166, 255, 0.4)";
        this.ctx.setLineDash([]);
        this.ctx.stroke();
      }

      // Edge info label
      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;
      this.ctx.fillStyle = isMst ? "#a5d6ff" : (edge.is_bridge ? "#e3b341" : "#8b949e");
      this.ctx.font = isMst ? "bold 11px monospace" : "10px monospace";
      this.ctx.textAlign = "center";

      let label = `t:${edge.foot_time}s`;
      if (edge.is_bridge) {
        label += ` [Puente: ${edge.current_resistance}/${edge.max_resistance}]`;
      }
      this.ctx.fillText(label, midX, midY + 12);
    }
  }

  drawActiveTowerRadii() {
    if (!this.towerSelectionResult?.selected_towers) return;

    for (const tower of this.towerSelectionResult.selected_towers) {
      const pos = this.worldToScreen(tower.x, tower.y);
      const radiusScreen = tower.surveillance_radius * this.scale;

      // Surveillance area (R_V)
      this.ctx.beginPath();
      this.ctx.arc(pos.x, pos.y, radiusScreen, 0, Math.PI * 2);
      this.ctx.fillStyle = "rgba(63, 185, 80, 0.08)";
      this.ctx.fill();
      this.ctx.lineWidth = 1.5;
      this.ctx.strokeStyle = "rgba(63, 185, 80, 0.4)";
      this.ctx.setLineDash([4, 4]);
      this.ctx.stroke();
      this.ctx.setLineDash([]);

      // Label with S(p) score
      this.ctx.fillStyle = "#f0883e";
      this.ctx.font = "bold 11px sans-serif";
      this.ctx.textAlign = "center";
      this.ctx.fillText(`S(p)=${tower.score}`, pos.x, pos.y - 20);
    }
  }

  drawNodes() {
    // 1. Draw Maze Nodes
    for (const node of this.scenarioData.maze_network?.nodes || []) {
      const p = this.worldToScreen(node.x, node.y);
      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, 8, 0, Math.PI * 2);

      if (node.is_entry) {
        this.ctx.fillStyle = "#3fb950";
        this.ctx.fill();
        this.ctx.strokeStyle = "#fff";
        this.ctx.lineWidth = 2;
        this.ctx.stroke();

        this.ctx.fillStyle = "#3fb950";
        this.ctx.font = "bold 12px sans-serif";
        this.ctx.fillText(`ENTRADA [${node.id}]`, p.x, p.y + 22);
      } else if (node.is_exit) {
        this.ctx.fillStyle = "#f85149";
        this.ctx.fill();
        this.ctx.strokeStyle = "#fff";
        this.ctx.lineWidth = 2;
        this.ctx.stroke();

        this.ctx.fillStyle = "#f85149";
        this.ctx.font = "bold 12px sans-serif";
        this.ctx.fillText(`SALIDA [${node.id}]`, p.x, p.y + 22);
      } else {
        this.ctx.fillStyle = "#21262d";
        this.ctx.fill();
        this.ctx.strokeStyle = "#8b949e";
        this.ctx.lineWidth = 1.5;
        this.ctx.stroke();

        this.ctx.fillStyle = "#8b949e";
        this.ctx.font = "10px sans-serif";
        this.ctx.fillText(node.id, p.x, p.y + 18);
      }
    }

    // 2. Draw Elevated Nodes
    const activeTowerIds = new Set(
      (this.towerSelectionResult?.selected_towers || []).map(t => t.tower_id)
    );

    for (const node of this.scenarioData.elevated_network?.nodes || []) {
      const p = this.worldToScreen(node.x, node.y);
      const isSelectedTower = activeTowerIds.has(node.id);

      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, isSelectedTower ? 11 : 9, 0, Math.PI * 2);

      if (node.type === "Base") {
        this.ctx.fillStyle = "#238636";
        this.ctx.fill();
        this.ctx.strokeStyle = "#7ee787";
        this.ctx.lineWidth = 2.5;
        this.ctx.stroke();

        this.ctx.fillStyle = "#7ee787";
        this.ctx.font = "bold 12px sans-serif";
        this.ctx.fillText(`★ BASE (${node.id})`, p.x, p.y - 14);
      } else if (node.type === "Helipuerto") {
        this.ctx.fillStyle = "#6e40c9";
        this.ctx.fill();
        this.ctx.strokeStyle = "#bc8cff";
        this.ctx.lineWidth = 2;
        this.ctx.stroke();

        this.ctx.fillStyle = "#bc8cff";
        this.ctx.font = "bold 11px sans-serif";
        this.ctx.fillText(`[H] ${node.id}`, p.x, p.y - 14);
      } else if (node.type === "Candidato") {
        if (isSelectedTower) {
          this.ctx.fillStyle = "#d29922";
          this.ctx.fill();
          this.ctx.strokeStyle = "#f0883e";
          this.ctx.lineWidth = 3;
          this.ctx.stroke();

          this.ctx.fillStyle = "#f0883e";
          this.ctx.font = "bold 11px sans-serif";
          this.ctx.fillText(`Torre Activa: ${node.id} (z:${node.z})`, p.x, p.y + 24);
        } else {
          this.ctx.fillStyle = "#21262d";
          this.ctx.fill();
          this.ctx.strokeStyle = "#d29922";
          this.ctx.lineWidth = 2;
          this.ctx.setLineDash([3, 3]);
          this.ctx.stroke();
          this.ctx.setLineDash([]);

          this.ctx.fillStyle = "#d29922";
          this.ctx.font = "11px sans-serif";
          this.ctx.fillText(`Candidato: ${node.id}`, p.x, p.y + 20);
        }
      } else {
        // Transito
        this.ctx.fillStyle = "#1f6feb";
        this.ctx.fill();
        this.ctx.strokeStyle = "#58a6ff";
        this.ctx.lineWidth = 1.5;
        this.ctx.stroke();

        this.ctx.fillStyle = "#8b949e";
        this.ctx.font = "10px sans-serif";
        this.ctx.fillText(node.id, p.x, p.y + 18);
      }
    }
  }

  // ==========================================
  // Stage 3: Convoy Trail, Dijkstra Projection & Decisions
  // ==========================================

  drawConvoyTrail() {
    if (!this.convoyState) return;

    const nodeMap = new Map();
    for (const n of this.scenarioData.maze_network?.nodes || []) {
      nodeMap.set(n.id, n);
    }

    // 1. Draw Traversed Historical Trail (Neon Violet)
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

        // Direction arrow along trail
        const arrowX = p1.x + (p2.x - p1.x) * 0.6;
        const arrowY = p1.y + (p2.y - p1.y) * 0.6;
        const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);

        this.ctx.fillStyle = "#d2a8ff";
        this.ctx.beginPath();
        this.ctx.moveTo(arrowX, arrowY);
        this.ctx.lineTo(
          arrowX - 8 * Math.cos(angle - Math.PI / 6),
          arrowY - 8 * Math.sin(angle - Math.PI / 6)
        );
        this.ctx.lineTo(
          arrowX - 8 * Math.cos(angle + Math.PI / 6),
          arrowY - 8 * Math.sin(angle + Math.PI / 6)
        );
        this.ctx.closePath();
        this.ctx.fill();
      }
      this.ctx.restore();
    }

    // 2. Draw Projected Dijkstra Path to Target (Cyan Dashed Line)
    const projectedPath = this.convoyState.projected_path || [];
    if (projectedPath.length > 1) {
      this.ctx.save();
      this.ctx.lineWidth = 3;
      this.ctx.strokeStyle = "#58a6ff";
      this.ctx.setLineDash([6, 4]);
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

  drawConvoyToken() {
    if (!this.convoyState || !this.convoyState.current_node) return;

    const nodeMap = new Map();
    for (const n of this.scenarioData.maze_network?.nodes || []) {
      nodeMap.set(n.id, n);
    }

    const currNode = nodeMap.get(this.convoyState.current_node);
    if (!currNode) return;

    const p = this.worldToScreen(currNode.x, currNode.y);

    this.ctx.save();

    // 1. Outer radar pulse ring
    this.ctx.beginPath();
    this.ctx.arc(p.x, p.y, 20, 0, Math.PI * 2);
    this.ctx.strokeStyle = "rgba(188, 140, 255, 0.7)";
    this.ctx.lineWidth = 2;
    this.ctx.stroke();

    // 2. Armored convoy body
    this.ctx.beginPath();
    this.ctx.arc(p.x, p.y, 13, 0, Math.PI * 2);
    this.ctx.fillStyle = "#6e40c9";
    this.ctx.fill();
    this.ctx.strokeStyle = "#d2a8ff";
    this.ctx.lineWidth = 2.5;
    this.ctx.shadowColor = "#bc8cff";
    this.ctx.shadowBlur = 8;
    this.ctx.stroke();
    this.ctx.shadowBlur = 0;

    // 3. Convoy glyph
    this.ctx.fillStyle = "#ffffff";
    this.ctx.font = "bold 11px sans-serif";
    this.ctx.textAlign = "center";
    this.ctx.textBaseline = "middle";
    this.ctx.fillText("C", p.x, p.y);

    // 4. Floating Real-time HP Bar
    const hp = this.convoyState.hp !== undefined ? this.convoyState.hp : (this.convoyState.convoy_status?.total_hp || 0);
    const maxHp = this.convoyState.max_hp !== undefined ? this.convoyState.max_hp : (this.convoyState.convoy_status?.max_total_hp || 350);
    const ratio = maxHp > 0 ? Math.max(0, Math.min(1, hp / maxHp)) : 0;

    const barW = 38;
    const barH = 5;
    const barX = p.x - barW / 2;
    const barY = p.y - 25;

    // Bar background
    this.ctx.fillStyle = "#161b22";
    this.ctx.fillRect(barX, barY, barW, barH);
    this.ctx.strokeStyle = "#30363d";
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(barX, barY, barW, barH);

    // Bar fill
    let hpColor = "#3fb950";
    if (ratio <= 0.25) hpColor = "#f85149";
    else if (ratio <= 0.5) hpColor = "#d29922";

    this.ctx.fillStyle = hpColor;
    this.ctx.fillRect(barX, barY, barW * ratio, barH);

    // HP Text
    this.ctx.fillStyle = "#e6edf3";
    this.ctx.font = "bold 9px monospace";
    this.ctx.textAlign = "center";
    this.ctx.textBaseline = "bottom";
    this.ctx.fillText(`${Math.round(hp)}/${Math.round(maxHp)} HP`, p.x, barY - 2);

    // Outcome banner if finished
    if (this.convoyState.is_finished) {
      if (this.convoyState.escaped) {
        this.ctx.fillStyle = "#3fb950";
        this.ctx.font = "bold 12px sans-serif";
        this.ctx.textBaseline = "top";
        this.ctx.fillText("🎉 CONVOY ESCAPÓ", p.x, p.y + 18);
      } else if (this.convoyState.destroyed) {
        this.ctx.fillStyle = "#f85149";
        this.ctx.font = "bold 12px sans-serif";
        this.ctx.textBaseline = "top";
        this.ctx.fillText("💥 CONVOY DESTRUIDO", p.x, p.y + 18);
      }
    }

    this.ctx.restore();
  }

  drawAntiBacktracking() {
    if (!this.convoyState || !this.convoyState.decision) return;

    const decision = this.convoyState.decision;
    const nodeMap = new Map();
    for (const n of this.scenarioData.maze_network?.nodes || []) {
      nodeMap.set(n.id, n);
    }

    this.ctx.save();

    if (decision.type === "ANTI_BACKTRACK_AVOIDED") {
      // 1. Rejected reverse edge with prominent prohibition marker
      const discNodeId = decision.discarded_node;
      const prevNodeId = this.convoyState.previous_node || this.convoyState.current_node;

      const uNode = nodeMap.get(prevNodeId);
      const vNode = nodeMap.get(discNodeId);

      if (uNode && vNode) {
        const p1 = this.worldToScreen(uNode.x, uNode.y);
        const p2 = this.worldToScreen(vNode.x, vNode.y);

        // Dashed red line on discarded edge
        this.ctx.beginPath();
        this.ctx.moveTo(p1.x, p1.y);
        this.ctx.lineTo(p2.x, p2.y);
        this.ctx.strokeStyle = "#f85149";
        this.ctx.lineWidth = 4;
        this.ctx.setLineDash([4, 4]);
        this.ctx.stroke();
        this.ctx.setLineDash([]);

        // Prohibition badge at midpoint
        const midX = (p1.x + p2.x) / 2;
        const midY = (p1.y + p2.y) / 2;

        const badgeText = "⛔ NO RETROCESO";
        this.ctx.font = "bold 10px sans-serif";
        const textMetrics = this.ctx.measureText(badgeText);
        const badgeW = textMetrics.width + 12;
        const badgeH = 18;

        this.ctx.fillStyle = "rgba(248, 81, 73, 0.95)";
        this.ctx.beginPath();
        if (typeof this.ctx.roundRect === "function") {
          this.ctx.roundRect(midX - badgeW / 2, midY - badgeH / 2, badgeW, badgeH, 4);
        } else {
          this.ctx.rect(midX - badgeW / 2, midY - badgeH / 2, badgeW, badgeH);
        }
        this.ctx.fill();
        this.ctx.strokeStyle = "#ffffff";
        this.ctx.lineWidth = 1;
        this.ctx.stroke();

        this.ctx.fillStyle = "#ffffff";
        this.ctx.textAlign = "center";
        this.ctx.textBaseline = "middle";
        this.ctx.fillText(badgeText, midX, midY);
      }

      // 2. Highlight chosen alternative forward edge
      const chosenNodeId = decision.chosen_next_node;
      const originNodeId = this.convoyState.previous_node || this.convoyState.current_node;
      const origNode = nodeMap.get(originNodeId);
      const chosenNode = nodeMap.get(chosenNodeId);

      if (origNode && chosenNode) {
        const p1 = this.worldToScreen(origNode.x, origNode.y);
        const p2 = this.worldToScreen(chosenNode.x, chosenNode.y);

        // Glowing golden/orange line
        this.ctx.beginPath();
        this.ctx.moveTo(p1.x, p1.y);
        this.ctx.lineTo(p2.x, p2.y);
        this.ctx.strokeStyle = "#f0883e";
        this.ctx.lineWidth = 4.5;
        this.ctx.shadowColor = "#f0883e";
        this.ctx.shadowBlur = 12;
        this.ctx.stroke();
        this.ctx.shadowBlur = 0;

        // Badge at alternative edge midpoint
        const altMidX = (p1.x + p2.x) / 2;
        const altMidY = (p1.y + p2.y) / 2;

        const altBadgeText = "✓ DESVÍO ÓPTIMO";
        this.ctx.font = "bold 9px sans-serif";
        const altMetrics = this.ctx.measureText(altBadgeText);
        const altW = altMetrics.width + 10;
        const altH = 16;

        this.ctx.fillStyle = "rgba(240, 136, 62, 0.95)";
        this.ctx.beginPath();
        if (typeof this.ctx.roundRect === "function") {
          this.ctx.roundRect(altMidX - altW / 2, altMidY - altH / 2, altW, altH, 3);
        } else {
          this.ctx.rect(altMidX - altW / 2, altMidY - altH / 2, altW, altH);
        }
        this.ctx.fill();
        this.ctx.strokeStyle = "#ffffff";
        this.ctx.lineWidth = 1;
        this.ctx.stroke();

        this.ctx.fillStyle = "#ffffff";
        this.ctx.textAlign = "center";
        this.ctx.textBaseline = "middle";
        this.ctx.fillText(altBadgeText, altMidX, altMidY);
      }
    } else if (decision.type === "FORCED_DEAD_END_BACKTRACK") {
      // Amber notification on current node indicating forced dead-end backtrack
      const currNodeId = this.convoyState.current_node;
      const currNode = nodeMap.get(currNodeId);
      if (currNode) {
        const p = this.worldToScreen(currNode.x, currNode.y);
        const alertText = "⚠️ CALLEJÓN SIN SALIDA (Retroceso Forzado)";
        this.ctx.font = "bold 10px sans-serif";
        const m = this.ctx.measureText(alertText);
        const w = m.width + 14;
        const h = 20;

        this.ctx.fillStyle = "rgba(210, 153, 34, 0.95)";
        this.ctx.beginPath();
        if (typeof this.ctx.roundRect === "function") {
          this.ctx.roundRect(p.x - w / 2, p.y + 22, w, h, 4);
        } else {
          this.ctx.rect(p.x - w / 2, p.y + 22, w, h);
        }
        this.ctx.fill();
        this.ctx.strokeStyle = "#ffffff";
        this.ctx.lineWidth = 1;
        this.ctx.stroke();

        this.ctx.fillStyle = "#ffffff";
        this.ctx.textAlign = "center";
        this.ctx.textBaseline = "middle";
        this.ctx.fillText(alertText, p.x, p.y + 32);
      }
    }

    this.ctx.restore();
  }
}

window.Renderer2D = Renderer2D;
