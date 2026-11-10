/**
 * 2D Canvas renderer for Elevated Network (G_E) and Maze Network (G_M).
 */

class Renderer2D {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.scenarioData = null;
    this.mstResult = null;
    this.towerSelectionResult = null;

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
    this.drawNodes();
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

      // Corridor base track
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);
      this.ctx.lineWidth = isWatched ? 10 : 7;
      this.ctx.strokeStyle = isWatched ? "rgba(63, 185, 80, 0.35)" : "rgba(110, 118, 129, 0.4)";
      this.ctx.lineCap = "round";
      this.ctx.stroke();

      // Inner corridor line
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);
      this.ctx.lineWidth = 3;
      this.ctx.strokeStyle = isWatched ? "#3fb950" : "#484f58";
      this.ctx.stroke();

      // Corridor midpoint label
      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;
      this.ctx.fillStyle = isWatched ? "#7ee787" : "#8b949e";
      this.ctx.font = "10px monospace";
      this.ctx.textAlign = "center";
      this.ctx.fillText(`L:${corr.length} (v:${corr.speed})`, midX, midY - 6);
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
}

window.Renderer2D = Renderer2D;

