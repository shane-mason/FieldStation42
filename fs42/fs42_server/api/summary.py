from fastapi import APIRouter
from fs42.station_manager import StationManager
from fs42.catalog_api import CatalogAPI
from fs42.liquid_manager import LiquidManager

router = APIRouter(prefix="/summary", tags=["summary"])

@router.get("/")
async def get_summary():
    summaries = []
    for station in StationManager().stations:
        if station["_has_schedule"]:
            sched_summary = LiquidManager().get_summary_json(network_name=station["network_name"])
        else:
            sched_summary = {"network_name": station["network_name"], "start": 0, "end": 0}
        summary = {
            "network_name": station["network_name"],
            "channel_number": station["channel_number"],
            "_has_schedule": station["_has_schedule"],
            "hidden": station.get("hidden", False),
            "catalog_summary": CatalogAPI.get_summary(station),
            "schedule_summary": sched_summary,
        }
        summaries.append(summary)
    return {"summary_data": summaries}

@router.get("/stations")
async def get_stations():
    station_ids = [station["network_name"] for station in StationManager().stations]
    return {"network_names": station_ids}

@router.get("/schedules")
async def get_schedule_summaries():
    summaries = LiquidManager().get_summary_json()
    return {"schedule_summaries": summaries}

@router.get("/schedules/{network_name}")
async def get_schedule_summary(network_name: str):
    station = StationManager().station_by_name(network_name)
    if station["_has_schedule"]:
        summary = LiquidManager().get_summary_json(network_name=network_name)
        return {"schedule_summary": summary}
    else:
        return {"error": f"No schedule found for network {network_name}"}

@router.get("/catalogs")
async def get_catalog_summary():
    summaries = []
    for station in StationManager().stations:
        catalog_entries = CatalogAPI.get_entries(station)
        summary = {"network_name": station["network_name"], "entry_count": len(catalog_entries)}
        summaries.append(summary)
    return {"catalog_summaries": summaries}
