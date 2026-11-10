"""Maze Graph (G_M) for the enemy convoy navigation."""

from typing import Dict, List, Optional, Tuple, Any
import math
from app.core.graph import BaseGraph
from app.domain.node import MazeNode
from app.domain.edge import MazeEdge


class MazeGraph(BaseGraph):
    """Network of maze corridors for convoy navigation."""

    def __init__(self, directed: bool = False):
        # Maze can allow bidirectional movement or directed movement.
        super().__init__(directed=directed)
        self.maze_nodes: Dict[str, MazeNode] = {}
        self.maze_edges: Dict[Tuple[str, str], MazeEdge] = {}

    def add_maze_node(
        self,
        node_id: str,
        x: float,
        y: float,
        is_entry: bool = False,
        is_exit: bool = False,
    ) -> MazeNode:
        """Adds or updates a maze intersection node."""
        node = MazeNode(
            node_id=node_id,
            x=x,
            y=y,
            is_entry=is_entry,
            is_exit=is_exit,
        )
        self.maze_nodes[node.id] = node
        self.add_node(
            node.id,
            x=node.x,
            y=node.y,
            is_entry=node.is_entry,
            is_exit=node.is_exit,
        )
        return node

    def add_corridor(
        self,
        u: str,
        v: str,
        length: Optional[float] = None,
        speed: float = 1.0,
    ) -> MazeEdge:
        """Adds a maze corridor.
        
        If length is not provided, it is computed as the Euclidean distance
        between nodes u and v.
        """
        u = str(u)
        v = str(v)
        if length is None:
            node_u = self.maze_nodes.get(u)
            node_v = self.maze_nodes.get(v)
            if node_u and node_v:
                length = math.hypot(node_u.x - node_v.x, node_u.y - node_v.y)
            else:
                length = 1.0

        edge = MazeEdge(u=u, v=v, length=length, speed=speed)
        key = edge.edge_key
        self.maze_edges[key] = edge

        self.add_edge(
            u,
            v,
            length=edge.length,
            speed=edge.speed,
            base_time=edge.base_time,
            reactive_weight=edge.reactive_weight,
            edge_obj=edge,
        )
        return edge

    def get_maze_node(self, node_id: str) -> Optional[MazeNode]:
        return self.maze_nodes.get(str(node_id))

    def get_corridor(self, u: str, v: str) -> Optional[MazeEdge]:
        key = (min(str(u), str(v)), max(str(u), str(v)))
        return self.maze_edges.get(key)

    def get_entry_nodes(self) -> List[MazeNode]:
        return [node for node in self.maze_nodes.values() if node.is_entry]

    def get_exit_nodes(self) -> List[MazeNode]:
        return [node for node in self.maze_nodes.values() if node.is_exit]

    def get_corridor_points(self, u: str, v: str) -> Optional[Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]]:
        """Returns the 3 key points of corridor e=(u, v): (q_ini, q_mid, q_end)."""
        node_u = self.get_maze_node(u)
        node_v = self.get_maze_node(v)
        if not node_u or not node_v:
            return None

        q_ini = (node_u.x, node_u.y)
        q_end = (node_v.x, node_v.y)
        q_mid = ((node_u.x + node_v.x) / 2.0, (node_u.y + node_v.y) / 2.0)
        return (q_ini, q_mid, q_end)

