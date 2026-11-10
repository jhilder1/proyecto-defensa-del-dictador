"""Service handling MST calculations and greedy tower selection."""

from typing import Dict, Any, Optional
from app.services.scenario_service import ScenarioService
from app.core.algorithms import kruskal_mst, select_towers_greedy


class PlanningService:
    """Orchestrates defense planning calculations."""

    def __init__(self, scenario_service: Optional[ScenarioService] = None):
        self.scenario_service = scenario_service or ScenarioService.get_instance()

    def calculate_mst(self) -> Dict[str, Any]:
        """Calculates Kruskal MST on the Base connected component."""
        base_node = self.scenario_service.elevated_graph.get_base_node()
        if not base_node:
            raise ValueError("No Base node found in Elevated Network.")

        mst_result = kruskal_mst(
            self.scenario_service.elevated_graph,
            base_node_id=base_node.id,
        )

        # Store in scenario service
        self.scenario_service.mst_result = {
            "base_node_id": mst_result["base_node_id"],
            "base_component": mst_result["base_component"],
            "mst_edges": mst_result["mst_edges"],
            "tree_distances": mst_result["tree_distances"],
            "total_cost": mst_result["total_cost"],
            "steps": mst_result["steps"],
        }

        return self.scenario_service.mst_result

    def select_towers(self, k_towers: int = 3, d0_normalization: Optional[float] = None) -> Dict[str, Any]:
        """Runs greedy tower selection algorithm."""
        # Ensure MST is calculated first
        if not self.scenario_service.mst_result:
            self.calculate_mst()

        mst_res = self.scenario_service.mst_result
        tree_distances = mst_res["tree_distances"]

        d0 = d0_normalization
        if d0 is None:
            d0 = self.scenario_service.simulation_state.d0_normalization

        selection_result = select_towers_greedy(
            elevated_graph=self.scenario_service.elevated_graph,
            maze_graph=self.scenario_service.maze_graph,
            tree_distances=tree_distances,
            k_towers=k_towers,
            d0_normalization=d0,
        )

        self.scenario_service.tower_selection_result = selection_result
        return selection_result

