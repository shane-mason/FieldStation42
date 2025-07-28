from fastapi import APIRouter
from .summary import router as summary_router
from .catalogs import router as catalogs_router
from .schedules import router as schedules_router
from .player import router as player_router
from .build import router as build_router
from .themes import router as themes_router
from .stations import router as stations_router

# Create a list of all routers to be included
routers = [
    summary_router,
    catalogs_router,
    schedules_router,
    player_router,
    build_router,
    themes_router,
    stations_router,
]
