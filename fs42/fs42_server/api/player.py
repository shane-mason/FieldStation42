from fastapi import APIRouter, Request, HTTPException
import json
import subprocess
import shutil
import re
import platform
from fs42.station_manager import StationManager

router = APIRouter(prefix="/player", tags=["player"])



@router.get("/info")
async def get_info():
    """Get system information including CPU temp, memory usage, and CPU usage"""
    info = {}
    
    # Get CPU temperature
    temp_info = await _get_cpu_temperature()
    info.update(temp_info)
    
    # Get memory information
    memory_info = await _get_memory_info()
    info.update(memory_info)
    
    # Get CPU usage
    cpu_info = await _get_cpu_info()
    info.update(cpu_info)
    
    # Get system information
    try:
        info["system"] = {
            "platform": platform.system(),
            "architecture": platform.machine(),
            "hostname": platform.node()
        }
    except Exception:
        info["system"] = {"error": "unavailable"}
    
    return info


async def _get_cpu_temperature():
    """Get CPU temperature using various methods depending on the system"""
    
    # Method 1: Raspberry Pi vcgencmd (original method)
    if shutil.which("vcgencmd"):
        try:
            result = subprocess.check_output(["vcgencmd", "measure_temp"], text=True)
            # output in form: temp=49.4'C
            temp_c = float(result.split("=")[1].split("'")[0])
            temp_f = round((temp_c * 1.8) + 32)
            return {
                "temperature_c": round(temp_c, 1),
                "temperature_f": temp_f,
                "temp_source": "vcgencmd"
            }
        except Exception:
            pass
    
    # Method 2: Linux thermal zones (most modern Linux systems)
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_millicelsius = int(f.read().strip())
            temp_c = temp_millicelsius / 1000.0
            temp_f = round((temp_c * 1.8) + 32)
            return {
                "temperature_c": round(temp_c, 1),
                "temperature_f": temp_f,
                "temp_source": "thermal_zone"
            }
    except Exception:
        pass
    
    # Method 3: Using lm-sensors (if available)
    if shutil.which("sensors"):
        try:
            result = subprocess.check_output(["sensors"], text=True)
            # Look for CPU temperature in sensors output
            for line in result.split('\n'):
                if 'Core 0' in line or 'CPU' in line or 'temp1' in line:
                    match = re.search(r'([+-]?\d+\.?\d*)\s*°C', line)
                    if match:
                        temp_c = float(match.group(1))
                        temp_f = round((temp_c * 1.8) + 32)
                        return {
                            "temperature_c": round(temp_c, 1),
                            "temperature_f": temp_f,
                            "temp_source": "sensors"
                        }
        except Exception:
            pass
    
    return {"temperature": "unavailable"}


async def _get_memory_info():
    """Get memory information from /proc/meminfo"""
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read()
        
        # Parse meminfo
        mem_total = 0
        mem_available = 0
        mem_free = 0
        
        for line in meminfo.split('\n'):
            if 'MemTotal:' in line:
                mem_total = int(line.split()[1]) * 1024  # Convert from KB to bytes
            elif 'MemAvailable:' in line:
                mem_available = int(line.split()[1]) * 1024
            elif 'MemFree:' in line:
                mem_free = int(line.split()[1]) * 1024
        
        # Use MemAvailable if available, otherwise fall back to MemFree
        available = mem_available if mem_available > 0 else mem_free
        used = mem_total - available
        used_percent = round((used / mem_total) * 100, 1) if mem_total > 0 else 0
        
        return {
            "memory": {
                "total_gb": round(mem_total / (1024**3), 1),
                "available_gb": round(available / (1024**3), 1),
                "used_gb": round(used / (1024**3), 1),
                "used_percent": used_percent
            }
        }
    except Exception:
        return {"memory": {"error": "unavailable"}}


async def _get_cpu_info():
    """Get CPU usage information"""
    try:
        # Get CPU count
        cpu_count = 0
        try:
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
            cpu_count = cpuinfo.count("processor")
        except Exception:
            cpu_count = 1
        
        # Get load average (simpler than trying to calculate CPU percentage)
        try:
            with open("/proc/loadavg", "r") as f:
                loadavg = f.read().strip().split()
            load_1min = float(loadavg[0])
            load_5min = float(loadavg[1])
            load_15min = float(loadavg[2])
            
            # Convert load to rough percentage (load/cores * 100)
            load_percent = round((load_1min / cpu_count) * 100, 1) if cpu_count > 0 else 0
            
            return {
                "cpu": {
                    "cores": cpu_count,
                    "load_1min": load_1min,
                    "load_5min": load_5min,
                    "load_15min": load_15min,
                    "load_percent": load_percent
                }
            }
        except Exception:
            return {
                "cpu": {
                    "cores": cpu_count,
                    "load": "unavailable"
                }
            }
    except Exception:
        return {"cpu": {"error": "unavailable"}}

@router.get("/status")
async def get_player_status():
    status_socket = StationManager().server_conf["status_socket"]
    if status_socket:
        try:
            with open(status_socket, "r") as f:
                status_str = f.read().strip()
            return json.loads(status_str)
        except FileNotFoundError:
            return {"error": "Status socket file not found."}
    else:
        return {"error": "Status socket is not configured."}


@router.get("/status/queue_connected")
async def get_connected(request: Request):
    command_queue = request.app.state.player_command_queue
    if command_queue:
        return {"queue_connected": True}
    else:
        return {"queue_connected": False}

@router.get("/channels/{channel}")
async def player_channel(channel: str):
    command = {"command": "direct", "channel": -1}
    if channel.isnumeric():
        command["channel"] = int(channel)
    elif channel == "up":
        command["command"] = "up"
    elif channel == "down":
        command["command"] = "down"
    else:
        return {"error": "Invalid channel command. Use a number, 'up', or 'down'."}

    cs = StationManager().server_conf["channel_socket"]
    with open(cs, "w") as f:
        f.write(json.dumps(command))
    return {"command": command}


@router.post("/channels/guide")
async def show_guide(request:Request):
    command_queue = request.app.state.player_command_queue
    command_queue.put({"command": "guide"})
    return {"status" : "ok"}

@router.get("/commands/stop")
@router.post("/commands/stop")
async def player_stop(request: Request):
    command_queue = request.app.state.player_command_queue
    command_queue.put({"command": "exit"})
    return {"status": "stopped"}

@router.post("/ticker")
async def show_ticker(request: Request):
    data = await request.json()
    command_queue = request.app.state.player_command_queue
    command_queue.put({
        "command": "ticker", 
        "message": data.get("message", ""), 
        "header": data.get("header", "FS42"), 
        "style": data.get("style", "fieldstation"), 
        "iterations": data.get("iterations", 2)
    })
    return {"status": "success"}

@router.get("/volume/up")
@router.post("/volume/up")
async def volume_up():
    """Increase volume by 5%"""
    return await _control_volume("up")


@router.get("/volume/down")
@router.post("/volume/down")
async def volume_down():
    """Decrease volume by 5%"""
    return await _control_volume("down")


@router.get("/volume/mute")
@router.post("/volume/mute")
async def volume_mute():
    """Toggle mute on/off"""
    return await _control_volume("mute")


async def _control_volume(action: str):
    """Control volume using the most appropriate Linux audio system"""
    
    # Check what audio systems are available
    amixer_available = shutil.which("amixer") is not None
    pactl_available = shutil.which("pactl") is not None
    wpctl_available = shutil.which("wpctl") is not None
    
    # Try different audio systems in order of preference
    # For WSL, prefer PulseAudio over ALSA since ALSA usually fails
    if pactl_available:
        try:
            return await _volume_pulseaudio(action)
        except Exception as e:
            print(f"pactl failed: {e}")
            
    if amixer_available:
        try:
            return await _volume_amixer(action)
        except Exception as e:
            print(f"amixer failed (expected in WSL): {e}")
            
    if wpctl_available:
        try:
            return await _volume_wireplumber(action)
        except Exception as e:
            print(f"wpctl failed: {e}")
    
    raise HTTPException(status_code=500, detail=f"No supported audio system found or all failed. Available: amixer={amixer_available}, pactl={pactl_available}, wpctl={wpctl_available}")


async def _volume_amixer(action: str):
    """Control volume using ALSA amixer (most common on Raspberry Pi)"""
    try:
        if action == "up":
            cmd = ["amixer", "sset", "Master", "5%+"]
            message = "Volume increased by 5%"
        elif action == "down":
            cmd = ["amixer", "sset", "Master", "5%-"]
            message = "Volume decreased by 5%"
        elif action == "mute":
            cmd = ["amixer", "sset", "Master", "toggle"]
            message = "Mute toggled"
        else:
            raise ValueError(f"Invalid action: {action}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Try to extract volume level from amixer output
        volume_level = _extract_amixer_volume(result.stdout)
        return {"action": action, "method": "amixer", "status": "success", "message": message, "volume": volume_level}
        
    except subprocess.CalledProcessError:
        # If Master doesn't work, try PCM
        try:
            cmd[2] = "PCM"  # Replace "Master" with "PCM"
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            volume_level = _extract_amixer_volume(result.stdout)
            return {"action": action, "method": "amixer", "status": "success", "message": f"{message} (PCM)", "volume": volume_level}
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"ALSA amixer failed: {e.stderr}")


async def _volume_pulseaudio(action: str):
    """Control volume using PulseAudio pactl"""
    try:
        if action == "up":
            cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"]
            message = "Volume increased by 5%"
        elif action == "down":
            cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"]
            message = "Volume decreased by 5%"
        elif action == "mute":
            cmd = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"]
            message = "Mute toggled"
        else:
            raise ValueError(f"Invalid action: {action}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Get current volume and mute status after the change
        if action == "mute":
            volume_level = await _get_pulseaudio_mute_status()
        else:
            volume_level = await _get_pulseaudio_volume()
            
        return {"action": action, "method": "pulseaudio", "status": "success", "message": message, "volume": volume_level}
        
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"PulseAudio pactl failed: {e.stderr}")


async def _volume_wireplumber(action: str):
    """Control volume using WirePlumber wpctl (newer PipeWire systems)"""
    try:
        if action == "up":
            cmd = ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0.05+"]
            message = "Volume increased by 5%"
        elif action == "down":
            cmd = ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0.05-"]
            message = "Volume decreased by 5%"
        elif action == "mute":
            cmd = ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]
            message = "Mute toggled"
        else:
            raise ValueError(f"Invalid action: {action}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"action": action, "method": "wireplumber", "status": "success", "message": message, "volume": "unknown"}
        
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"WirePlumber wpctl failed: {e.stderr}")


def _extract_amixer_volume(output: str) -> str:
    """Extract volume percentage from amixer output"""
    try:
        # Look for pattern like [75%] in the amixer output
        match = re.search(r'\[(\d+)%\]', output)
        if match:
            return f"{match.group(1)}%"
        return "unknown"
    except:
        return "unknown"


async def _get_pulseaudio_volume() -> str:
    """Get current volume from PulseAudio"""
    try:
        result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, check=True
        )
        
        # PulseAudio output looks like: Volume: front-left: 65536 /  100% / 0.00 dB,   front-right: 65536 /  100% / 0.00 dB
        match = re.search(r'(\d+)%', result.stdout)
        if match:
            return f"{match.group(1)}%"
        return "unknown"
    except:
        return "unknown"


async def _get_pulseaudio_mute_status() -> str:
    """Get current mute status and volume from PulseAudio"""
    try:
        # Check mute status
        mute_result = subprocess.run(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
            capture_output=True, text=True, check=True
        )
        
        # Get volume
        volume_result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, check=True
        )
        
        # Parse mute status - output is like "Mute: yes" or "Mute: no"
        is_muted = "yes" in mute_result.stdout.lower()
        
        # Parse volume
        volume_match = re.search(r'(\d+)%', volume_result.stdout)
        volume = volume_match.group(1) if volume_match else "??"
        
        if is_muted:
            return f"MUTED ({volume}%)"
        else:
            return f"{volume}%"
            
    except:
        return "MUTE"