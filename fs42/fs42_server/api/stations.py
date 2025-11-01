from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from fs42.station_manager import StationManager

router = APIRouter(prefix="/stations", tags=["stations"])

# Pydantic Models
class StationConfigRequest(BaseModel):
    """Request model for creating/updating station configurations."""
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

    station_manager = StationManager()
    stations = station_manager.stations

    return {
        "count": len(stations),
        "stations": stations
    }

@router.get("/{network_name}")
async def get_station_config(network_name: str):

    station_manager = StationManager()
    station = station_manager.station_by_name(network_name)

    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{network_name}' not found"
        )

    return {"network_name": network_name, "station_config": station}

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

    # Check if station already exists
    if station_manager.station_by_name(network_name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Station '{network_name}' already exists. Use PUT to update."
        )

    # Write the configuration
    success, message, file_path = station_manager.write_station_config(
        network_name,
        config.model_dump(),
        is_update=False
    )

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

    # Check if station exists
    if station_manager.station_by_name(network_name) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{network_name}' not found"
        )

    # Write the configuration (update mode)
    success, message, file_path = station_manager.write_station_config(
        network_name,
        config.model_dump(),
        is_update=True
    )

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

    # Check if station exists
    if station_manager.station_by_name(network_name) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{network_name}' not found"
        )

    # Delete the configuration
    success, message = station_manager.delete_station_config(network_name)

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
