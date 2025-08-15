from fastapi import APIRouter
from datetime import datetime
from fs42.station_manager import StationManager
from fs42.liquid_api import LiquidAPI

router = APIRouter(prefix="/schedules", tags=["schedules"])

@router.get("/search_all")
async def search_all_schedules(query: str = None):
    if not query:
        # If no query, get all blocks from all stations
        station_manager = StationManager()
        all_results = []
        
        for station in station_manager.stations:
            if station.get("_has_schedule", False):
                try:
                    schedule_blocks = LiquidAPI.get_blocks(station)
                    if schedule_blocks:
                        all_results.append({
                            "network_name": station["network_name"],
                            "schedule_blocks": schedule_blocks
                        })
                except Exception as e:
                    all_results.append({
                        "network_name": station["network_name"],
                        "error": str(e),
                        "schedule_blocks": []
                    })
        
        return {"query": query, "results": all_results}
    else:
        # Search across all stations at once
        try:
            search_results = LiquidAPI.search_all_blocks(query)
            all_results = []
            
            for station_name, blocks in search_results.items():
                if blocks:
                    all_results.append({
                        "network_name": station_name,
                        "schedule_blocks": blocks
                    })
            
            return {"query": query, "results": all_results}
        except Exception as e:
            return {"query": query, "error": str(e), "results": []}

@router.get("/search/{network_name}")
async def search_schedule(network_name: str, query: str = None):
    conf = StationManager().station_by_name(network_name)
    if query:
        schedule_blocks = LiquidAPI.search_blocks(conf, query)
    else:
        schedule_blocks = LiquidAPI.get_blocks(conf)

    return {"network_name": network_name, "query": query, "schedule_blocks": schedule_blocks}

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
