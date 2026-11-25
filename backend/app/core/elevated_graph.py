"""Elevated Graph (G_E) for human defense forces."""

from typing import Dict, List, Optional, Set, Tuple, Any
from app.core.graph import BaseGraph
from app.domain.node import ElevatedNode, ElevatedNodeType
from app.domain.edge import ElevatedEdge


class ElevatedGraph(BaseGraph):
    """Network of elevated pathways, candidate towers, base, heliport and bridges."""

    def __init__(self):
        super().__init__(directed=False)
        self.elevated_nodes: Dict[str, ElevatedNode] = {}
        self.elevated_edges: Dict[Tuple[str, str], ElevatedEdge] = {}

    def add_elevated_node(
        self,
        node_id: str,
        x: float,
        y: float,
        z: float = 0.0,
        node_type: ElevatedNodeType = ElevatedNodeType.TRANSITO,
        surveillance_radius: float = 20.0,
    ) -> ElevatedNode:
        """Adds or updates an elevated node."""
        node = ElevatedNode(
            node_id=node_id,
            x=x,
            y=y,
            z=z,
            node_type=node_type,
            surveillance_radius=surveillance_radius,
        )
        self.elevated_nodes[node.id] = node
        self.add_node(
            node.id,
            x=node.x,
            y=node.y,
            z=node.z,
            type=node.node_type.value,
            surveillance_radius=node.surveillance_radius,
        )
        return node

    def add_elevated_edge(
        self,
        u: str,
        v: str,
        foot_time: float,
        moto_time: float,
        is_bridge: bool = False,
        max_resistance: int = 3,
        reconstruction_duration: float = 30.0,
    ) -> ElevatedEdge:
        """Adds an undirected elevated pathway or bridge."""
        edge = ElevatedEdge(
            u=u,
            v=v,
            foot_time=foot_time,
            moto_time=moto_time,
            is_bridge=is_bridge,
            max_resistance=max_resistance,
            reconstruction_duration=reconstruction_duration,
        )
        key = edge.edge_key
        self.elevated_edges[key] = edge
        self.add_edge(
            edge.u,
            edge.v,
            foot_time=edge.foot_time,
            moto_time=edge.moto_time,
            is_bridge=edge.is_bridge,
            max_resistance=edge.max_resistance,
            current_resistance=edge.current_resistance,
            is_destroyed=edge.is_destroyed,
            edge_obj=edge,
        )
        return edge

    def get_elevated_node(self, node_id: str) -> Optional[ElevatedNode]:
        return self.elevated_nodes.get(str(node_id))

    def get_elevated_edge(self, u: str, v: str) -> Optional[ElevatedEdge]:
        key = (min(str(u), str(v)), max(str(u), str(v)))
        return self.elevated_edges.get(key)

    def get_base_node(self) -> Optional[ElevatedNode]:
        for node in self.elevated_nodes.values():
            if node.node_type == ElevatedNodeType.BASE:
                return node
        return None

    def get_heliport_node(self) -> Optional[ElevatedNode]:
        for node in self.elevated_nodes.values():
            if node.node_type == ElevatedNodeType.HELIPUERTO:
                return node
        return None

    def get_candidate_nodes(self) -> List[ElevatedNode]:
        return [
            node for node in self.elevated_nodes.values()
            if node.node_type == ElevatedNodeType.CANDIDATO
        ]

    def get_active_towers(self) -> List[ElevatedNode]:
        return [
            node for node in self.elevated_nodes.values()
            if node.is_active_tower
        ]

    def get_bridges(self) -> List[ElevatedEdge]:
        return [edge for edge in self.elevated_edges.values() if edge.is_bridge]

    def _sync_bridge_adj(self, edge: ElevatedEdge) -> None:
        """Synchronizes bridge resistance and destroyed flags in adjacency dicts."""
        if self.has_edge(edge.u, edge.v):
            self.adj[edge.u][edge.v]["is_destroyed"] = edge.is_destroyed
            self.adj[edge.u][edge.v]["current_resistance"] = edge.current_resistance
            self.adj[edge.v][edge.u]["is_destroyed"] = edge.is_destroyed
            self.adj[edge.v][edge.u]["current_resistance"] = edge.current_resistance

    def record_motorcycle_bridge_crossing(self, u: str, v: str) -> bool:
        """Records a completed motorcycle crossing on bridge (u, v).

        Decrements resistance by 1, updates adjacency, and returns True if collapsed.
        """
        edge = self.get_elevated_edge(u, v)
        if not edge or not edge.is_bridge:
            return False
        collapsed = edge.on_motorcycle_cross_complete()
        self._sync_bridge_adj(edge)
        return collapsed

    def reset_bridges(self) -> None:
        """Restores all bridges to maximum resistance and clears reconstruction timers."""
        for edge in self.get_bridges():
            edge.current_resistance = edge.max_resistance
            edge.is_destroyed = False
            edge.reconstruction_timer = 0.0
            self._sync_bridge_adj(edge)

    def reset_tower_occupancies(self) -> None:
        """Clears stationed soldiers and reserved slots on all elevated nodes."""
        for node in self.elevated_nodes.values():
            node.stationed_soldiers.clear()
            node.reserved_slots = 0

    def update_reconstruction_timers(self, delta_time: float) -> List[str]:
        """Advances bridge reconstruction timers.
        
        Returns a list of edge descriptions that finished rebuilding in this tick.
        """
        rebuilt = []
        for edge in self.get_bridges():
            if edge.is_destroyed and edge.update_reconstruction(delta_time):
                self._sync_bridge_adj(edge)
                rebuilt.append(f"{edge.u}-{edge.v}")
        return rebuilt

