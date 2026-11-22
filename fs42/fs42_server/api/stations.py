from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from fs42.station_manager import StationManager
from fs42.station_io import StationIO
from fs42.liquid_manager import LiquidManager

router = APIRouter(prefix="/stations", tags=["stations"])

# Pydantic Models
class StationConfigRequest(BaseModel):
    station_conf: Dict[str, Any] = Field(
        ...,
        description="Station configuration object containing network_name, channel_number, and other settings"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "station_conf": {
                    "network_name": "MyChannel",
                    "channel_number": 42,
                    "network_type": "standard",
                    "schedule_increment": 30
                }
            }
        }

class StationConfigResponse(BaseModel):
    success: bool
    message: str
    network_name: Optional[str] = None
    channel_number: Optional[int] = None
    file_path: Optional[str] = None

class StationListResponse(BaseModel):
    count: int
    stations: List[Dict[str, Any]]

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    details: Optional[str] = None

# Endpoints

@router.get("", response_model=StationListResponse)
async def list_stations():
    station_io = StationIO()
    raw_stations = station_io.list_raw_station_configs()

    skipped_by_name = {
        entry["network_name"]: entry["error"]
        for entry in StationManager().skipped_stations
        if entry["network_name"]
    }

    for raw in raw_stations:
        station_conf = raw.get("station_conf")
        if not isinstance(station_conf, dict):
            continue
        reason = skipped_by_name.get(station_conf.get("network_name"))
        if reason:
            station_conf["_draft"] = True
            station_conf["_draft_reason"] = reason

    return {
        "count": len(raw_stations),
        "stations": raw_stations
    }

@router.get("/{network_name}")
async def get_station_config(network_name: str):

    station_io = StationIO()
    success, raw_data, error_msg = station_io.read_raw_station_config(network_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_msg
        )

    return {"network_name": network_name, "station_config": raw_data}

@router.post("", response_model=StationConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_station(config: StationConfigRequest):

    station_manager = StationManager()

    # Extract network_name for checking
    if "network_name" not in config.station_conf:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="network_name is required in station_conf"
        )

    network_name = config.station_conf["network_name"]

    if StationIO().find_config_by_network_name(network_name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Station '{network_name}' already exists. Use PUT to update."
        )

    # Write the configuration (StationManager handles validation and file I/O via StationIO)
    success, message, file_path = station_manager.write_station_config(
        network_name,
        config.model_dump(),
        is_update=False
    )

    if success:
        LiquidManager().reload_schedules()

    if not success:
        # Determine if it's a validation error or conflict
        if "already used" in message or "already exists" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )

    return {
        "success": True,
        "message": message,
        "network_name": network_name,
        "channel_number": config.station_conf.get("channel_number"),
        "file_path": file_path
    }

@router.put("/{network_name}", response_model=StationConfigResponse)
async def update_station(network_name: str, config: StationConfigRequest):
    station_manager = StationManager()

    if StationIO().find_config_by_network_name(network_name) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{network_name}' not found"
        )

    # Write the configuration (update mode, StationManager handles validation and file I/O via StationIO)
    success, message, file_path = station_manager.write_station_config(
        network_name,
        config.model_dump(),
        is_update=True
    )

    if success:
        LiquidManager().reload_schedules()

    if not success:
        # Determine if it's a validation error or conflict
        if "already used" in message or "already exists" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )

    new_network_name = config.station_conf.get("network_name", network_name)

    return {
        "success": True,
        "message": message,
        "network_name": new_network_name,
        "channel_number": config.station_conf.get("channel_number"),
        "file_path": file_path
    }

@router.delete("/{network_name}", response_model=StationConfigResponse)
async def delete_station(network_name: str):

    station_manager = StationManager()

    if StationIO().find_config_by_network_name(network_name) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{network_name}' not found"
        )

    # Delete the configuration (StationManager handles file deletion via StationIO)
    success, message = station_manager.delete_station_config(network_name)

    if success:
        LiquidManager().reload_schedules()

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message
        )

    return {
        "success": True,
        "message": message,
        "network_name": network_name
    }
