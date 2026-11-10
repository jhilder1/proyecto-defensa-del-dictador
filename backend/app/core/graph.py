"""Base generic graph structure implemented with native Python data structures."""

from typing import Dict, List, Set, Any, Optional, Iterator, Tuple


class BaseGraph:
    """Generic graph using adjacency dictionary representation.
    
    Adjacency structure:
    adj[u][v] = edge_data (dict or object)
    """

    def __init__(self, directed: bool = False):
        self.directed: bool = directed
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.adj: Dict[str, Dict[str, Any]] = {}

    def add_node(self, node_id: str, **attributes: Any) -> None:
        """Adds a node with arbitrary attributes if it does not already exist."""
        node_id = str(node_id)
        if node_id not in self.nodes:
            self.nodes[node_id] = attributes
            self.adj[node_id] = {}
        else:
            self.nodes[node_id].update(attributes)

    def has_node(self, node_id: str) -> bool:
        return str(node_id) in self.nodes

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.nodes.get(str(node_id))

    def add_edge(self, u: str, v: str, **attributes: Any) -> None:
        """Adds an edge between u and v with edge attributes.
        
        If vertices do not exist, they are automatically added.
        If undirected, the edge is added in both directions u->v and v->u.
        """
        u = str(u)
        v = str(v)
        if not self.has_node(u):
            self.add_node(u)
        if not self.has_node(v):
            self.add_node(v)

        self.adj[u][v] = attributes
        if not self.directed:
            self.adj[v][u] = attributes

    def has_edge(self, u: str, v: str) -> bool:
        u = str(u)
        v = str(v)
        return u in self.adj and v in self.adj[u]

    def get_edge_data(self, u: str, v: str) -> Optional[Dict[str, Any]]:
        u = str(u)
        v = str(v)
        return self.adj.get(u, {}).get(v)

    def neighbors(self, node_id: str) -> List[str]:
        """Returns sorted list of neighbor IDs for deterministic traversal."""
        node_id = str(node_id)
        if node_id not in self.adj:
            return []
        return sorted(list(self.adj[node_id].keys()))

    def degree(self, node_id: str) -> int:
        node_id = str(node_id)
        return len(self.adj.get(node_id, {}))

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        total = sum(len(neighbors) for neighbors in self.adj.values())
        return total if self.directed else total // 2

    def get_all_edges(self) -> List[Tuple[str, str, Dict[str, Any]]]:
        """Returns a list of all edges (u, v, data).
        
        For undirected graphs, each edge is returned once with u <= v lexicographically.
        """
        edges = []
        visited_pairs: Set[Tuple[str, str]] = set()

        for u in sorted(self.adj.keys()):
            for v in sorted(self.adj[u].keys()):
                canonical = (u, v) if self.directed else (min(u, v), max(u, v))
                if canonical not in visited_pairs:
                    visited_pairs.add(canonical)
                    edges.append((canonical[0], canonical[1], self.adj[u][v]))
        return edges

    def get_connected_components(self) -> List[Set[str]]:
        """Finds all connected components using Breadth-First Search (BFS)."""
        visited: Set[str] = set()
        components: List[Set[str]] = []

        for node in sorted(self.nodes.keys()):
            if node not in visited:
                comp: Set[str] = set()
                queue: List[str] = [node]
                visited.add(node)
                while queue:
                    curr = queue.pop(0)
                    comp.add(curr)
                    for nbr in self.neighbors(curr):
                        if nbr not in visited:
                            visited.add(nbr)
                            queue.append(nbr)
                components.append(comp)

        return components

