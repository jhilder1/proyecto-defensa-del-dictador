"""Controller for Stage 4 logistics endpoints (purchases, ground and air dispatches)."""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from app.schemas.action_schema import (
    BuySoldierRequest,
    DispatchGroundRequest,
    DispatchAirRequest,
)
from app.services.logistics_service import LogisticsService

router = APIRouter(prefix="/api/logistics", tags=["Logistics"])


@router.post("/buy-soldier")
def buy_soldier(req: BuySoldierRequest) -> Dict[str, Any]:
    """Purchases defense soldiers and places them at Base."""
    try:
        service = LogisticsService.get_instance()
        return service.buy_soldier(
            soldier_type=req.soldier_type,
            quantity=req.quantity,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/dispatch-ground")
def dispatch_ground(req: DispatchGroundRequest) -> Dict[str, Any]:
    """Dispatches 1 soldier on foot or 1-2 soldiers by motorcycle."""
    try:
        service = LogisticsService.get_instance()
        return service.dispatch_ground(
            transport_type=req.transport_type,
            soldier_ids=req.soldier_ids,
            destination_id=req.destination_id,
            origin_id=req.origin_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/dispatch-air")
def dispatch_air(req: DispatchAirRequest) -> Dict[str, Any]:
    """Dispatches up to 4 soldiers via helicopter with surplus redistribution."""
    try:
        service = LogisticsService.get_instance()
        return service.dispatch_air(
            soldier_ids=req.soldier_ids,
            destination_id=req.destination_id,
            origin_id=req.origin_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/state")
def get_logistics_state() -> Dict[str, Any]:
    """Returns budget, soldiers, active missions, bridges, and tower occupancies."""
    try:
        service = LogisticsService.get_instance()
        return service.get_logistics_state()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
