"""FastAPI main application entrypoint."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.controllers.scenario_controller import router as scenario_router
from app.api.controllers.planning_controller import router as planning_router
from app.services.scenario_service import ScenarioService

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")


def load_default_scenario_if_available():
    default_scenario_path = os.path.join(BASE_DIR, "data", "scenario_1_basic.json")
    if os.path.exists(default_scenario_path):
        service = ScenarioService.get_instance()
        service.load_from_file(default_scenario_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_default_scenario_if_available()
    yield


app = FastAPI(
    title="Simulación de Defensa Estratégica",
    description="Backend para la defensa estratégica contra el General P. Tardo",
    version="1.0.0",
    lifespan=lifespan,
)

# Initialize on import as well so default scenario is immediately ready
load_default_scenario_if_available()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(scenario_router)
app.include_router(planning_router)

# Mount frontend
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_index():
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        return FileResponse(index_path)
