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
        foot_time: Optional[float],
        moto_time: Optional[float],
        is_bridge: bool = False,
        max_resistance: int = 3,
        reconstruction_duration: float = 30.0,
        repair_personnel: int = 2,
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
            repair_personnel=repair_personnel,
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
            edge.assigned_personnel = 0
            self._sync_bridge_adj(edge)

    def reset_tower_occupancies(self) -> None:
        """Clears stationed soldiers and reserved slots on all elevated nodes."""
        for node in self.elevated_nodes.values():
            node.stationed_soldiers.clear()
            node.reserved_slots = 0

    def update_reconstruction_timers(
        self,
        delta_time: float,
        simulation_state: Optional[Any] = None,
    ) -> List[str]:
        """Advances bridge reconstruction timers, optionally enforcing repair personnel limits.

        Returns a list of edge descriptions that finished rebuilding in this tick.
        """
        rebuilt = []
        destroyed_bridges = sorted(
            [e for e in self.get_bridges() if e.is_destroyed],
            key=lambda e: e.edge_key,
        )

        if simulation_state is None:
            for edge in destroyed_bridges:
                if edge.update_reconstruction(delta_time):
                    self._sync_bridge_adj(edge)
                    rebuilt.append(f"{edge.u}-{edge.v}")
            return rebuilt

        # 1. Assign available repair personnel to waiting destroyed bridges
        for edge in destroyed_bridges:
            if edge.assigned_personnel == 0 and simulation_state.available_repair_personnel >= edge.repair_personnel:
                edge.assigned_personnel = edge.repair_personnel
                simulation_state.available_repair_personnel -= edge.repair_personnel
                simulation_state.add_event(
                    "BRIDGE_REPAIR_STARTED",
                    f"Personal asignado ({edge.repair_personnel} operarios) para reconstruir puente {edge.u}-{edge.v}.",
                    {"edge": f"{edge.u}-{edge.v}", "personnel": edge.repair_personnel},
                )

        # 2. Advance timers only for bridges with assigned personnel
        for edge in destroyed_bridges:
            if edge.assigned_personnel >= edge.repair_personnel:
                if edge.update_reconstruction(delta_time):
                    simulation_state.available_repair_personnel = min(
                        simulation_state.total_repair_personnel,
                        simulation_state.available_repair_personnel + edge.assigned_personnel,
                    )
                    edge.assigned_personnel = 0
                    self._sync_bridge_adj(edge)
                    rebuilt.append(f"{edge.u}-{edge.v}")
        return rebuilt

