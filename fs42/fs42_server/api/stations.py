from fastapi import APIRouter
from fs42.station_manager import StationManager

router = APIRouter(prefix="/stations", tags=["stations"])

@router.get("/{network_name}")
async def get_station_config(network_name: str):
    return {"network_name": network_name, "station_config": StationManager().station_by_name(network_name)}
