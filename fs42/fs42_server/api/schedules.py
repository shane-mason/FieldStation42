from fastapi import APIRouter
from datetime import datetime
from fs42.station_manager import StationManager
from fs42.liquid_api import LiquidAPI

router = APIRouter(prefix="/schedules", tags=["schedules"])

@router.get("/{network_name}")
async def get_schedule(network_name: str, start: str = None, end: str = None):
    conf = StationManager().station_by_name(network_name)
    sdt = None
    edt = None
    if start and end:
        try:
            sdt = datetime.fromisoformat(start)
            edt = datetime.fromisoformat(end)
        except ValueError:
            return {"error": "Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS) for start and end."}

    schedule_blocks = LiquidAPI.get_blocks(conf, sdt, edt)
    return {"network_name": network_name, "schedule_blocks": schedule_blocks}
