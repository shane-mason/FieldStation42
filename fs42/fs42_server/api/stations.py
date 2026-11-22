import glob
import json
import os
import shutil
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

class StationOrderRequest(BaseModel):
    network_names: List[str] = Field(..., min_length=1)

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

@router.post("/reorder")
async def reorder_stations(order: StationOrderRequest):
    station_io = StationIO()
    configs_by_name = {}
    for file_path in glob.glob(os.path.join(station_io.confs_dir, "*.json")):
        if os.path.normpath(file_path) == os.path.normpath(station_io.main_config_path):
            continue
        try:
            with open(file_path) as fp:
                config = json.load(fp)
        except (OSError, json.JSONDecodeError):
            continue
        station_conf = config.get("station_conf") if isinstance(config, dict) else None
        if not isinstance(station_conf, dict):
            continue
        name = station_conf.get("network_name")
        channel_number = station_conf.get("channel_number")
        if (
            isinstance(name, str)
            and name
            and isinstance(channel_number, int)
            and not isinstance(channel_number, bool)
        ):
            if name in configs_by_name:
                raise HTTPException(status_code=409, detail=f"Duplicate station name '{name}' in station configs.")
            configs_by_name[name] = {
                "path": file_path,
                "config": config,
                "channel_number": channel_number,
            }

    requested_names = order.network_names
    if len(requested_names) != len(set(requested_names)):
        raise HTTPException(status_code=400, detail="Each station must appear only once in the channel order.")
    if set(requested_names) != set(configs_by_name):
        raise HTTPException(
            status_code=409,
            detail="The station list changed. Reload the page and try reordering again.",
        )

    channel_slots = sorted(entry["channel_number"] for entry in configs_by_name.values())
    if len(channel_slots) != len(set(channel_slots)):
        raise HTTPException(
            status_code=409,
            detail="Several stations already share a channel number. Resolve the duplicate numbers before reordering.",
        )
    assignments = dict(zip(requested_names, channel_slots))
    if all(configs_by_name[name]["channel_number"] == channel for name, channel in assignments.items()):
        return {
            "success": True,
            "message": "Channel order is unchanged.",
            "stations": [{"network_name": name, "channel_number": channel} for name, channel in assignments.items()],
        }

    staged = []
    try:
        for name in requested_names:
            entry = configs_by_name[name]
            if entry["channel_number"] == assignments[name]:
                continue
            path = entry["path"]
            with open(path, "rb") as fp:
                original = fp.read()
            shutil.copy2(path, path + ".bak")
            temp_path = path + ".reorder.tmp"
            staged.append({"path": path, "temp_path": temp_path, "original": original, "written": False})
            entry["config"]["station_conf"]["channel_number"] = assignments[name]
            with open(temp_path, "w", encoding="utf-8") as fp:
                json.dump(entry["config"], fp, indent=2)
                fp.write("\n")

        for entry in staged:
            os.replace(entry["temp_path"], entry["path"])
            entry["written"] = True
    except Exception as exc:
        for entry in staged:
            try:
                if entry["written"]:
                    rollback_path = entry["path"] + ".reorder.rollback"
                    with open(rollback_path, "wb") as fp:
                        fp.write(entry["original"])
                    os.replace(rollback_path, entry["path"])
                if os.path.exists(entry["temp_path"]):
                    os.remove(entry["temp_path"])
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=f"Could not save channel order: {exc}") from exc

    StationManager()._reload_stations()
    LiquidManager().reload_schedules()
    return {
        "success": True,
        "message": "Channel order saved.",
        "stations": [{"network_name": name, "channel_number": channel} for name, channel in assignments.items()],
    }

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
