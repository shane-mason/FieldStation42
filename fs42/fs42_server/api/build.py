import threading
import uuid
from fastapi import APIRouter, Request
from fs42.station_manager import StationManager
from fs42.catalog_api import CatalogAPI
from fs42.liquid_manager import LiquidManager
from fs42.liquid_schedule import LiquidSchedule
from fs42.catalog import ShowCatalog

router = APIRouter(prefix="/build", tags=["build"])

# Global dicts and locks for task tracking
rebuild_tasks = {}
rebuild_tasks_lock = threading.Lock()
add_time_tasks = {}
add_time_tasks_lock = threading.Lock()

@router.post("/catalog/{network_name}")
async def rebuild_catalog(network_name: str, request: Request):
    task_id = str(uuid.uuid4())
    with rebuild_tasks_lock:
        rebuild_tasks[task_id] = {"status": "starting", "log": ""}

    def rebuild_worker():
        try:
            with rebuild_tasks_lock:
                rebuild_tasks[task_id]["status"] = "running"
                rebuild_tasks[task_id]["log"] += f"Starting catalog rebuild for {network_name}\n"

            to_rebuild = []
            if not network_name or network_name == "all":
                to_rebuild = StationManager().stations
            else:
                to_rebuild = [StationManager().station_by_name(network_name)]

            for station in to_rebuild:
                if station["_has_schedule"]:
                    with rebuild_tasks_lock:
                        rebuild_tasks[task_id]["log"] += f"Deleting schedule for {station['network_name']}\n"
                        LiquidManager().reset_schedule(station, False)
                    with rebuild_tasks_lock:
                        rebuild_tasks[task_id]["log"] += f"Deleted schedule {station['network_name']} - rebuilding catalog now.\n"
                if station["_has_catalog"]:
                    CatalogAPI.delete_catalog(station)
                    ShowCatalog(station, rebuild_catalog=True)
                    with rebuild_tasks_lock:
                        rebuild_tasks[task_id]["log"] += f"Rebuilt catalog for {station['network_name']}\n"

            with rebuild_tasks_lock:
                rebuild_tasks[task_id]["status"] = "done"
                rebuild_tasks[task_id]["log"] += "Catalog rebuild complete.\n"
                rebuild_tasks[task_id]["log"] += "Reloading data and state.\n"
                command_queue = request.app.state.player_command_queue
                if command_queue:
                    command_queue.put({"command": "reload_data"})
                else:
                    LiquidManager().reload_schedules()
            
        except Exception as e:
            with rebuild_tasks_lock:
                rebuild_tasks[task_id]["status"] = "error"
                rebuild_tasks[task_id]["log"] += f"Error: {e}\n"

    thread = threading.Thread(target=rebuild_worker, daemon=True)
    thread.start()
    return {"task_id": task_id}

@router.get("/catalog/status/{task_id}")
async def rebuild_catalog_status(task_id: str):
    with rebuild_tasks_lock:
        task = rebuild_tasks.get(task_id)
        if not task:
            return {"error": "Task ID not found."}
        return {"status": task["status"], "log": task["log"]}

@router.post("/schedule/add_time/{amount}/{network_name}")
async def add_time_to_schedule(amount: str, network_name: str, request: Request):
    task_id = str(uuid.uuid4())
    with add_time_tasks_lock:
        add_time_tasks[task_id] = {"status": "starting", "log": ""}

    def add_time_worker():
        try:
            with add_time_tasks_lock:
                add_time_tasks[task_id]["status"] = "running"

            # Determine which stations to process
            to_process = []
            if not network_name or network_name == "all":
                to_process = StationManager().stations
            else:
                to_process = [StationManager().station_by_name(network_name)]

            for station in to_process:
                if station["_has_schedule"]:
                    with add_time_tasks_lock:
                        add_time_tasks[task_id]["log"] += f"Adding {amount} to schedule for {station['network_name']}\n"
                    liquid = LiquidSchedule(station)
                    liquid.add_amount(amount)

            with add_time_tasks_lock:
                add_time_tasks[task_id]["status"] = "done"
                add_time_tasks[task_id]["log"] += "Add time to schedule complete.\n"
                add_time_tasks[task_id]["log"] += "Reloading data and state.\n"
                command_queue = request.app.state.player_command_queue
                if command_queue:
                    command_queue.put({"command": "reload_data"})
                else:
                    LiquidManager().reload_schedules()
        except Exception as e:
            with add_time_tasks_lock:
                add_time_tasks[task_id]["status"] = "error"
                add_time_tasks[task_id]["log"] += f"Error: {e}\n"

    thread = threading.Thread(target=add_time_worker, daemon=True)
    thread.start()
    return {"task_id": task_id}

@router.get("/schedule/add_time/status/{task_id}")
async def add_time_to_schedule_status(task_id: str):
    with add_time_tasks_lock:
        task = add_time_tasks.get(task_id)
        if not task:
            return {"error": "Task ID not found."}
        return {"status": task["status"], "log": task["log"]}

@router.post("/schedule/reset/{network_name}")
async def rebuild_schedule(network_name: str, request: Request):
    task_id = str(uuid.uuid4())
    with rebuild_tasks_lock:
        rebuild_tasks[task_id] = {"status": "starting", "log": ""}

    def rebuild_schedule_worker():
        try:
            with rebuild_tasks_lock:
                rebuild_tasks[task_id]["status"] = "running"
                rebuild_tasks[task_id]["log"] += f"Starting schedule rebuild for {network_name}\n"

            to_rebuild = []
            if not network_name or network_name == "all":
                to_rebuild = StationManager().stations
            else:
                to_rebuild = [StationManager().station_by_name(network_name)]

            for station in to_rebuild:
                if station["_has_schedule"]:
                    LiquidManager().reset_schedule(station, True)
                    with rebuild_tasks_lock:
                        rebuild_tasks[task_id]["log"] += f"Rebuilt schedule for {station['network_name']}\n"

            with rebuild_tasks_lock:
                rebuild_tasks[task_id]["status"] = "done"
                rebuild_tasks[task_id]["log"] += "Schedule rebuild complete.\n"
                rebuild_tasks[task_id]["log"] += "Reloading data and state.\n"
                command_queue = request.app.state.player_command_queue
                if command_queue:
                    command_queue.put({"command": "reload_data"})
                else:
                    LiquidManager().reload_schedules()
        except Exception as e:
            with rebuild_tasks_lock:
                rebuild_tasks[task_id]["status"] = "error"
                rebuild_tasks[task_id]["log"] += f"Error: {e}\n"

    thread = threading.Thread(target=rebuild_schedule_worker, daemon=True)
    thread.start()
    return {"task_id": task_id}

@router.get("/schedule/reset/status/{task_id}")
async def rebuild_schedule_status(task_id: str):
    with rebuild_tasks_lock:
        task = rebuild_tasks.get(task_id)
        if not task:
            return {"error": "Task ID not found."}
        return {"status": task["status"], "log": task["log"]}
