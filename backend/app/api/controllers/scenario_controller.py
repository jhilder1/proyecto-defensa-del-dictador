"""Controller for scenario endpoints."""

from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Dict, Any, Optional
import json
import os
from app.services.scenario_service import ScenarioService
from app.schemas.scenario_schema import ScenarioDataSchema

router = APIRouter(prefix="/api/scenario", tags=["Scenario"])


@router.get("/current")
def get_current_scenario() -> Dict[str, Any]:
    """Returns the current state and structure of the loaded scenario."""
    service = ScenarioService.get_instance()
    return service.get_summary()


@router.post("/load")
def load_scenario(scenario_data: ScenarioDataSchema) -> Dict[str, Any]:
    """Loads a scenario directly from JSON payload."""
    try:
        service = ScenarioService.get_instance()
        data = scenario_data.model_dump()
        return service.load_from_dict(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/load-default")
def load_default_scenario(scenario_file: Optional[str] = "scenario_1_basic.json") -> Dict[str, Any]:
    """Loads a pre-packaged default scenario from the backend data directory."""
    try:
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        clean_filename = os.path.basename(scenario_file or "scenario_1_basic.json")
        data_path = os.path.join(backend_dir, "data", clean_filename)
        if not os.path.exists(data_path):
            raise HTTPException(status_code=404, detail=f"Scenario file '{clean_filename}' not found in data directory")
        service = ScenarioService.get_instance()
        return service.load_from_file(data_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload")
async def upload_scenario_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Uploads a custom scenario JSON file."""
    try:
        contents = await file.read()
        data = json.loads(contents.decode("utf-8"))
        service = ScenarioService.get_instance()
        return service.load_from_dict(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing uploaded file: {str(e)}")

