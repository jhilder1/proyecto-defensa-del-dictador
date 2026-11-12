"""Graph algorithms implemented from scratch without external graph libraries."""

import math
from typing import Dict, List, Set, Tuple, Optional, Any
from app.core.dsu import DisjointSetUnion
from app.core.priority_queue import PriorityQueue
from app.core.elevated_graph import ElevatedGraph
from app.core.maze_graph import MazeGraph
from app.domain.edge import ElevatedEdge, MazeEdge
from app.domain.node import ElevatedNode, ElevatedNodeType


def calculate_euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculates 2D Euclidean distance between two points."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def kruskal_mst(
    elevated_graph: ElevatedGraph,
    base_node_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Computes Minimum Spanning Tree (MST) on the Base's connected component of G_E.
    
    Uses edge foot_time as weight.
    Applies deterministic lexicographical tie-breaking for equal edge weights.
    
    Returns:
        Dict containing:
            - mst_edges: List of dicts representing the selected edges.
            - tree_distances: Dict[node_id, float] with D_T(B, p) measured along T_E.
            - total_cost: Total foot_time of T_E.
            - reachable_nodes: Set of node IDs in the MST component.
            - steps: Step-by-step history of edge evaluations.
    """
    if base_node_id is None:
        base_node = elevated_graph.get_base_node()
        if not base_node:
            raise ValueError("ElevatedGraph does not contain a Base node.")
        base_node_id = base_node.id
    else:
        base_node_id = str(base_node_id)
        if not elevated_graph.has_node(base_node_id):
            raise ValueError(f"Base node '{base_node_id}' not found in ElevatedGraph.")

    # 1. Identify the connected component containing base_node_id
    components = elevated_graph.get_connected_components()
    base_component: Set[str] = set()
    for comp in components:
        if base_node_id in comp:
            base_component = comp
            break

    if not base_component:
        base_component = {base_node_id}

    # 2. Collect edges belonging entirely to the base component
    candidate_edges: List[Tuple[float, str, str, ElevatedEdge]] = []
    all_edges = elevated_graph.elevated_edges.values()

    for edge in all_edges:
        if edge.u in base_component and edge.v in base_component:
            # Deterministic edge representation: min_id, max_id
            u_min = min(edge.u, edge.v)
            v_max = max(edge.u, edge.v)
            candidate_edges.append((edge.foot_time, u_min, v_max, edge))

    # Sort edges: weight ASC, then u_min ASC, then v_max ASC (lexicographical tie-breaking)
    candidate_edges.sort(key=lambda item: (item[0], item[1], item[2]))

    # 3. Kruskal's algorithm using custom DisjointSetUnion
    dsu = DisjointSetUnion[str](list(base_component))
    mst_edges: List[ElevatedEdge] = []
    steps: List[Dict[str, Any]] = []
    total_cost = 0.0

    target_edge_count = len(base_component) - 1

    for weight, u, v, edge in candidate_edges:
        if len(mst_edges) >= target_edge_count and target_edge_count > 0:
            steps.append({
                "u": u,
                "v": v,
                "weight": weight,
                "action": "skipped_mst_complete",
                "reason": "MST already fully connected",
            })
            continue

        if dsu.union(u, v):
            mst_edges.append(edge)
            total_cost += weight
            steps.append({
                "u": u,
                "v": v,
                "weight": weight,
                "action": "added",
                "reason": "Connects two disjoint components",
            })
        else:
            steps.append({
                "u": u,
                "v": v,
                "weight": weight,
                "action": "rejected",
                "reason": "Creates cycle",
            })

    # 4. Build MST tree adjacency to compute tree distances D_T(B, p)
    tree_adj: Dict[str, List[Tuple[str, float]]] = {node: [] for node in base_component}
    for edge in mst_edges:
        tree_adj[edge.u].append((edge.v, edge.foot_time))
        tree_adj[edge.v].append((edge.u, edge.foot_time))

    # BFS/DFS on tree to find exact tree distance from Base
    tree_distances: Dict[str, float] = {base_node_id: 0.0}
    queue: List[str] = [base_node_id]
    visited: Set[str] = {base_node_id}

    while queue:
        curr = queue.pop(0)
        curr_dist = tree_distances[curr]
        for nbr, edge_weight in tree_adj.get(curr, []):
            if nbr not in visited:
                visited.add(nbr)
                tree_distances[nbr] = curr_dist + edge_weight
                queue.append(nbr)

    return {
        "base_node_id": base_node_id,
        "base_component": sorted(list(base_component)),
        "mst_edges": [e.to_dict() for e in mst_edges],
        "mst_edge_objects": mst_edges,
        "tree_distances": tree_distances,
        "total_cost": round(total_cost, 2),
        "steps": steps,
    }


def select_towers_greedy(
    elevated_graph: ElevatedGraph,
    maze_graph: MazeGraph,
    tree_distances: Dict[str, float],
    k_towers: int,
    d0_normalization: float = 50.0,
) -> Dict[str, Any]:
    """Selects up to K defensive towers using the greedy formula:
    
    S(p) = C(p) / (1 + D_T(B, p) / D_0)
    
    where C(p) is the length of corridors not yet watched that candidate p covers.
    A corridor e in G_M is covered if dist(p, q_mid) <= R_V(p).
    
    Stop criteria:
        - Exactly K towers selected, OR
        - No candidate provides new coverage (C(p) == 0).
        
    Tie-breaking:
        1. Higher S(p)
        2. Lower D_T(B, p)
        3. Lexicographical candidate ID
    """
    d0 = max(0.001, float(d0_normalization))
    k = max(0, int(k_towers))

    # 1. Identify valid candidates (must be in G_E and reachable from Base in MST)
    candidates = [
        node for node in elevated_graph.get_candidate_nodes()
        if node.id in tree_distances
    ]

    # 2. Extract corridors and precalculate midpoints
    corridor_keys: Set[Tuple[str, str]] = set()
    corridor_data: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for edge in maze_graph.maze_edges.values():
        key = edge.edge_key
        corridor_keys.add(key)
        points = maze_graph.get_corridor_points(edge.u, edge.v)
        if points:
            q_ini, q_mid, q_end = points
        else:
            q_mid = (0.0, 0.0)
        corridor_data[key] = {
            "u": edge.u,
            "v": edge.v,
            "length": edge.length,
            "q_mid": q_mid,
        }

    # Track unwatched corridors and coverage history
    unwatched_corridors = set(corridor_keys)
    selected_towers: List[Dict[str, Any]] = []
    selection_history: List[Dict[str, Any]] = []
    tower_coverage_map: Dict[str, List[Tuple[str, str]]] = {}

    # Reset active status of candidates before selection
    for cand in elevated_graph.get_candidate_nodes():
        cand.is_active_tower = False

    available_candidates = {cand.id: cand for cand in candidates}

    for iteration in range(1, k + 1):
        if not available_candidates or not unwatched_corridors:
            break

        best_cand: Optional[ElevatedNode] = None
        best_score = -1.0
        best_c = 0.0
        best_dist = float("inf")
        best_new_corridors: List[Tuple[str, str]] = []

        # Evaluate all available candidates
        candidate_evaluations = []

        for cand_id in sorted(available_candidates.keys()):
            cand = available_candidates[cand_id]
            p_pos = (cand.x, cand.y)
            rv = cand.surveillance_radius
            d_t = tree_distances.get(cand_id, float("inf"))

            # Calculate C(p): length of unwatched corridors with dist(p, q_mid) <= R_V
            covered_in_this_eval: List[Tuple[str, str]] = []
            c_p = 0.0

            for c_key in sorted(unwatched_corridors):
                q_mid = corridor_data[c_key]["q_mid"]
                dist_to_mid = calculate_euclidean_distance(p_pos, q_mid)
                if dist_to_mid <= rv + 1e-9:
                    covered_in_this_eval.append(c_key)
                    c_p += corridor_data[c_key]["length"]

            # Compute S(p)
            score = 0.0
            if c_p > 0:
                score = c_p / (1.0 + (d_t / d0))

            candidate_evaluations.append({
                "candidate_id": cand_id,
                "score": round(score, 4),
                "unwatched_coverage_length": round(c_p, 2),
                "tree_distance": round(d_t, 2),
                "covered_corridors_count": len(covered_in_this_eval),
            })

            # Compare against best candidate:
            # 1. Higher score S(p)
            # 2. Lower distance D_T(B, p)
            # 3. Lexicographical ID
            is_better = False
            if score > best_score + 1e-9:
                is_better = True
            elif abs(score - best_score) <= 1e-9:
                if d_t < best_dist - 1e-9:
                    is_better = True
                elif abs(d_t - best_dist) <= 1e-9:
                    if best_cand is None or cand_id < best_cand.id:
                        is_better = True

            if is_better:
                best_cand = cand
                best_score = score
                best_c = c_p
                best_dist = d_t
                best_new_corridors = covered_in_this_eval

        # Stop criterion: no candidate provides any new coverage
        if best_cand is None or best_c <= 0:
            break

        # Select the best candidate
        best_cand.is_active_tower = True
        del available_candidates[best_cand.id]

        # Mark corridors as watched
        for c_key in best_new_corridors:
            unwatched_corridors.remove(c_key)

        tower_coverage_map[best_cand.id] = best_new_corridors

        selected_towers.append({
            "tower_id": best_cand.id,
            "x": best_cand.x,
            "y": best_cand.y,
            "z": best_cand.z,
            "surveillance_radius": best_cand.surveillance_radius,
            "score": round(best_score, 4),
            "unwatched_coverage_length": round(best_c, 2),
            "tree_distance": round(best_dist, 2),
            "covered_corridors": [f"{u}-{v}" for u, v in best_new_corridors],
        })

        selection_history.append({
            "iteration": iteration,
            "selected_tower_id": best_cand.id,
            "score": round(best_score, 4),
            "new_corridors_covered": len(best_new_corridors),
            "unwatched_remaining": len(unwatched_corridors),
            "evaluations": candidate_evaluations,
        })

    # Total covered corridors
    all_watched = corridor_keys - unwatched_corridors
    total_covered_length = sum(corridor_data[k]["length"] for k in all_watched)
    total_maze_length = sum(corridor_data[k]["length"] for k in corridor_keys)

    return {
        "k_requested": k,
        "towers_selected_count": len(selected_towers),
        "selected_towers": selected_towers,
        "history": selection_history,
        "watched_corridors": [f"{u}-{v}" for u, v in sorted(all_watched)],
        "unwatched_corridors": [f"{u}-{v}" for u, v in sorted(unwatched_corridors)],
        "coverage_percentage": round(
            (total_covered_length / total_maze_length * 100.0) if total_maze_length > 0 else 0.0, 2
        ),
    }


def dijkstra_reactive(
    graph: MazeGraph,
    start_node: str,
    target_node: str,
    forbidden_edge: Optional[Tuple[str, str]] = None,
    forbidden_first_step: Optional[str] = None,
) -> Optional[Tuple[float, List[str]]]:
    """Computes the shortest path on MazeGraph (G_M) using reactive weights w(e).
    
    Uses custom PriorityQueue (Min-Heap).
    Deterministic tie-breaking:
        1. Elements in queue are tuples (dist, node_id, parent_id).
        2. Neighbors are iterated in sorted lexicographical order.
        3. If two paths to node v have equal distance (within 1e-9), deterministically
           prefer the candidate parent u with smaller lexicographical ID (u < parent[v]).
           
    Parameters:
        graph: MazeGraph instance with nodes and reactive corridor weights.
        start_node: Starting node ID in G_M.
        target_node: Destination node ID in G_M.
        forbidden_edge: Optional edge (u, v) forbidden from traversal.
        forbidden_first_step: Optional neighbor node ID forbidden as immediate first step.
        
    Returns:
        Tuple of (total_reactive_cost, path_list) if target is reachable, else None.
    """
    start_node = str(start_node)
    target_node = str(target_node)

    if not graph.has_node(start_node) or not graph.has_node(target_node):
        return None

    if start_node == target_node:
        return (0.0, [start_node])

    # Normalize forbidden edge
    f_u: Optional[str] = None
    f_v: Optional[str] = None
    if forbidden_edge is not None:
        f_u = str(forbidden_edge[0])
        f_v = str(forbidden_edge[1])

    dist: Dict[str, float] = {node: float("inf") for node in graph.nodes}
    parent: Dict[str, Optional[str]] = {node: None for node in graph.nodes}

    dist[start_node] = 0.0

    pq = PriorityQueue[Tuple[float, str, str]]()
    pq.push((0.0, start_node, ""))

    while not pq.is_empty():
        d, u, p = pq.pop()

        if d > dist[u] + 1e-9:
            continue

        if u == target_node:
            break

        for v in sorted(graph.neighbors(u)):
            # Check forbidden edge constraint
            if f_u is not None and f_v is not None:
                if (u == f_u and v == f_v) or (u == f_v and v == f_u):
                    continue

            # Check forbidden first step constraint
            if forbidden_first_step is not None and u == start_node and v == str(forbidden_first_step):
                continue

            # Extract reactive weight
            corridor = graph.get_corridor(u, v)
            if corridor is not None:
                w = corridor.reactive_weight
            else:
                edge_data = graph.get_edge_data(u, v) or {}
                w = float(edge_data.get("reactive_weight", edge_data.get("base_time", edge_data.get("length", 1.0))))

            new_dist = d + w

            if new_dist < dist[v] - 1e-9:
                dist[v] = new_dist
                parent[v] = u
                pq.push((new_dist, v, u))
            elif abs(new_dist - dist[v]) <= 1e-9:
                if parent[v] is None or u < parent[v]:
                    parent[v] = u
                    pq.push((new_dist, v, u))

    if dist[target_node] == float("inf"):
        return None

    # Reconstruct path from target to start
    path: List[str] = []
    curr: Optional[str] = target_node
    visited_nodes: Set[str] = set()

    while curr is not None:
        path.append(curr)
        if curr == start_node:
            break
        if curr in visited_nodes:
            # Cycle detected during reconstruction; abort
            return None
        visited_nodes.add(curr)
        curr = parent.get(curr)

    path.reverse()

    if not path or path[0] != start_node:
        return None

    return (dist[target_node], path)


# Re-export hazard calculation functions for algorithm-level consumers
from app.services.hazard_service import calculate_point_damage, calculate_corridor_hazard



