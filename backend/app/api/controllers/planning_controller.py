"""Controller for planning endpoints (MST and greedy tower selection)."""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from app.services.planning_service import PlanningService
from app.schemas.scenario_schema import SelectTowersRequest

router = APIRouter(prefix="/api/planning", tags=["Planning"])


@router.post("/calculate-mst")
def calculate_mst() -> Dict[str, Any]:
    """Calculates Kruskal's MST on G_E base connected component."""
    try:
        service = PlanningService()
        return service.calculate_mst()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/select-towers")
def select_towers(req: SelectTowersRequest) -> Dict[str, Any]:
    """Executes the greedy tower selection algorithm."""
    try:
        service = PlanningService()
        return service.select_towers(
            k_towers=req.k_towers,
            d0_normalization=req.d0_normalization,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

