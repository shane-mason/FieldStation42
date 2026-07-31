import threading
import traceback
import uuid
from fastapi import APIRouter, Request, HTTPException
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
quick_tasks = {}
quick_tasks_lock = threading.Lock()
operation_lock = threading.Lock()


def _begin_operation():
    if not operation_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="Another catalog or schedule operation is already running.",
        )


def _select_stations(network_name):
    selected = (
        StationManager().stations
        if not network_name or network_name == "all"
        else [StationManager().station_by_name(network_name)]
    )
    if not selected or any(station is None for station in selected):
        raise HTTPException(status_code=404, detail="Station not found.")
    return selected


@router.post("/quick/{action}/{network_name}")
async def quick_action(action: str, network_name: str, request: Request):
    actions = {
        "rebuild",
        "rebuild_skip_chapters",
        "rebuild_and_week",
        "reset_and_week",
        "add_day",
        "add_week",
        "add_month",
    }
    if action not in actions:
        raise HTTPException(status_code=422, detail="Unknown quick action.")
    selected = _select_stations(network_name)
    _begin_operation()
    task_id = str(uuid.uuid4())
    with quick_tasks_lock:
        quick_tasks[task_id] = {"status": "starting", "log": ""}

    def log(message):
        with quick_tasks_lock:
            quick_tasks[task_id]["log"] += message + "\n"

    def worker():
        try:
            with quick_tasks_lock:
                quick_tasks[task_id]["status"] = "running"
            ShowCatalog.clear_fluid_cache()
            for station in selected:
                name = station["network_name"]
                if action.startswith("rebuild"):
                    log(f"Resetting schedule for {name}; catalog IDs will change.")
                    if station.get("_has_schedule"):
                        LiquidManager().reset_schedule(station)
                    if station.get("_has_catalog"):
                        log(f"Rebuilding catalog for {name}.")
                        CatalogAPI.delete_catalog(station)
                        ShowCatalog(
                            station,
                            rebuild_catalog=True,
                            skip_chapter_scan=action == "rebuild_skip_chapters",
                        )
                if action == "reset_and_week":
                    log(f"Resetting schedule for {name}.")
                    LiquidManager().reset_schedule(station)
                amount = {
                    "rebuild_and_week": "week",
                    "reset_and_week": "week",
                    "add_day": "day",
                    "add_week": "week",
                    "add_month": "month",
                }.get(action)
                should_generate = action in {"rebuild_and_week", "reset_and_week"}
                if amount and (should_generate or station.get("_has_schedule")):
                    log(f"Adding one {amount} to {name}.")
                    LiquidSchedule(station).add_amount(amount)
            LiquidManager().reload_schedules()
            command_queue = request.app.state.player_command_queue
            if command_queue:
                command_queue.put({"command": "reload_data"})
            with quick_tasks_lock:
                quick_tasks[task_id]["status"] = "done"
            log("Operation complete.")
        except Exception as exc:
            with quick_tasks_lock:
                quick_tasks[task_id]["status"] = "error"
                quick_tasks[task_id]["log"] += (
                    f"Error: {exc}\n\n{traceback.format_exc()}\n"
                )
        finally:
            operation_lock.release()

    try:
        threading.Thread(target=worker, daemon=True).start()
    except Exception:
        operation_lock.release()
        raise
    return {"task_id": task_id}


@router.get("/quick/status/{task_id}")
async def quick_action_status(task_id: str):
    with quick_tasks_lock:
        task = quick_tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task ID not found.")
        return dict(task)

@router.post("/catalog/{network_name}")
async def rebuild_catalog(
    network_name: str,
    request: Request,
    reset_schedule: bool = False,
    skip_chapter_scan: bool = False,
):
    selected = _select_stations(network_name)
    if any(station.get("_has_schedule") for station in selected) and not reset_schedule:
        raise HTTPException(
            status_code=409,
            detail=(
                "Rebuilding this catalog invalidates its schedule. Retry with "
                "reset_schedule=true after warning the user."
            ),
        )
    _begin_operation()
    task_id = str(uuid.uuid4())
    with rebuild_tasks_lock:
        rebuild_tasks[task_id] = {"status": "starting", "log": ""}

    def rebuild_worker():
        # Clear the fluid file cache dedup set so scan_file_cache runs fresh
        # for each unique content_dir in this rebuild pass.  Without this, a
        # second rebuild request in the same server process would silently skip
        # all directory scans, missing any files added since the first request.
        ShowCatalog.clear_fluid_cache()
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
                        LiquidManager().reset_schedule(station)
                    with rebuild_tasks_lock:
                        rebuild_tasks[task_id]["log"] += f"Deleted schedule {station['network_name']} - rebuilding catalog now.\n"
                if station["_has_catalog"]:
                    CatalogAPI.delete_catalog(station)
                    ShowCatalog(
                        station,
                        rebuild_catalog=True,
                        skip_chapter_scan=skip_chapter_scan,
                    )
                    with rebuild_tasks_lock:
                        rebuild_tasks[task_id]["log"] += f"Rebuilt catalog for {station['network_name']}\n"

            with rebuild_tasks_lock:
                rebuild_tasks[task_id]["status"] = "done"
                rebuild_tasks[task_id]["log"] += "Catalog rebuild complete.\n"
                rebuild_tasks[task_id]["log"] += "Reloading data and state.\n"
                command_queue = request.app.state.player_command_queue
                if command_queue:
                    command_queue.put({"command": "reload_data"})
                #else:
                LiquidManager().reload_schedules()
            
        except Exception as e:
            with rebuild_tasks_lock:
                rebuild_tasks[task_id]["status"] = "error"
                rebuild_tasks[task_id]["log"] += f"Error: {e}\n\nDetailed Error Message:\n{traceback.format_exc()}"
        finally:
            operation_lock.release()

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
    if amount not in {"day", "week", "month"}:
        raise HTTPException(status_code=422, detail="Amount must be day, week, or month.")
    _begin_operation()
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

                LiquidManager().reload_schedules()
        except Exception as e:
            with add_time_tasks_lock:
                add_time_tasks[task_id]["status"] = "error"
                add_time_tasks[task_id]["log"] += f"Error: {e}\n\nDetailed Error Message:\n{traceback.format_exc()}"
        finally:
            operation_lock.release()

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
    _begin_operation()
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
                    LiquidManager().reset_schedule(station)
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
                rebuild_tasks[task_id]["log"] += f"Error: {e}\n\nDetailed Error Message:\n{traceback.format_exc()}"
        finally:
            operation_lock.release()

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
