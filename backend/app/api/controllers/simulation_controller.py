"""Controller for Etapa 3 simulation endpoints: corridor hazards and reactive convoy navigation."""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from app.services.hazard_service import HazardService
from app.services.simulation_service import SimulationService
from app.schemas.simulation_schema import (
    CalculateHazardsRequest,
    ConvoyStepRequest,
    ConvoyRunRequest,
    ConvoyResetRequest,
)

router = APIRouter(prefix="/api/simulation", tags=["Simulation"])


@router.post("/calculate-hazards")
def calculate_hazards(
    payload: Optional[CalculateHazardsRequest] = Body(default=None),
    alpha: Optional[float] = Query(default=None),
) -> Dict[str, Any]:
    """Calculates corridor hazard rates D_bar(e), potential damage P(e), and reactive weights w(e)."""
    try:
        alpha_val = alpha
        if alpha_val is None and payload is not None and payload.alpha_danger is not None:
            alpha_val = payload.alpha_danger

        hazard_service = HazardService.get_instance()
        return hazard_service.evaluate_all_corridors(alpha=alpha_val)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convoy/step")
def convoy_step(
    payload: Optional[ConvoyStepRequest] = Body(default=None),
    alpha: Optional[float] = Query(default=None),
) -> Dict[str, Any]:
    """Advances the convoy one intersection step applying the Anti-Backtracking rule."""
    try:
        alpha_val = alpha
        if alpha_val is None and payload is not None and payload.alpha_danger is not None:
            alpha_val = payload.alpha_danger

        simulation_service = SimulationService.get_instance()
        return simulation_service.step(alpha_danger=alpha_val)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convoy/run")
def convoy_run(
    payload: Optional[ConvoyRunRequest] = Body(default=None),
    alpha: Optional[float] = Query(default=None),
    max_steps: Optional[int] = Query(default=None),
) -> Dict[str, Any]:
    """Runs the convoy navigation simulation until it reaches exit, gets destroyed, or hits max steps."""
    try:
        alpha_val = alpha
        steps_val = max_steps or 100
        if payload is not None:
            if alpha_val is None and payload.alpha_danger is not None:
                alpha_val = payload.alpha_danger
            if max_steps is None and payload.max_steps is not None:
                steps_val = payload.max_steps

        simulation_service = SimulationService.get_instance()
        return simulation_service.run(alpha_danger=alpha_val, max_steps=steps_val)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convoy/reset")
def convoy_reset(
    payload: Optional[ConvoyResetRequest] = Body(default=None),
    alpha: Optional[float] = Query(default=None),
) -> Dict[str, Any]:
    """Resets the convoy to the entry node and restores machine health."""
    try:
        alpha_val = alpha
        if alpha_val is None and payload is not None and payload.alpha_danger is not None:
            alpha_val = payload.alpha_danger

        simulation_service = SimulationService.get_instance()
        return simulation_service.reset(alpha_danger=alpha_val)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/convoy/status")
def convoy_status() -> Dict[str, Any]:
    """Returns the current state and telemetry of the convoy."""
    try:
        simulation_service = SimulationService.get_instance()
        return {
            "current_node": simulation_service.current_node,
            "previous_node": simulation_service.previous_node,
            "target_node": simulation_service.target_node,
            "hp": round(simulation_service.get_total_hp(), 2),
            "max_hp": round(simulation_service.get_max_hp(), 2),
            "step_index": simulation_service.step_index,
            "is_finished": simulation_service.is_finished,
            "escaped": simulation_service.escaped,
            "destroyed": simulation_service.destroyed,
            "backtracks_prevented": simulation_service.backtrack_count,
            "path_taken": list(simulation_service.visited_nodes),
            "convoy_status": simulation_service.get_convoy_status(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
