# 📡 FieldStation42 Server API Guide

Welcome to the FieldStation42 Server API! This is your one-stop guide to understanding and using the comprehensive REST API that powers your broadcasting station. Whether you're setting up your system or controlling live playback, this API has got you covered.

## 🚀 Quick Start

First things first - let's get your server running!

### Starting the Server

```bash
python3 station_42.py --server
```

This starts both the API server and web console. Visit **http://localhost:4242** to access the beautiful web interface!

### Default Configuration

Your server runs with these defaults (configurable in `main_config.json`):
```json
{
  "server_host": "0.0.0.0",
  "server_port": 4242
}
```

## 🎯 API Overview

The FieldStation42 API is organized around two main concepts:

- **🔧 Build-Time APIs**: System administration, configuration, and content management
- **📺 Play-Time APIs**: Live player control, monitoring, and viewer interaction

All endpoints return JSON responses and follow RESTful conventions.

---

## 🔧 Build-Time APIs

*For setting up your station, managing content, and system administration*

### 🏠 Web Console

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Main web console interface |
| `GET` | `/remote` | Remote control interface |

### 📊 Station Summary & Overview

#### Get Complete Station Summary
```http
GET /summary/
```
Returns comprehensive overview of all stations including catalog and schedule info.

**Response Example:**
```json
{
  "summary_data": [
    {
      "network_name": "PublicDomain",
      "channel_number": 1,
      "catalog_summary": {
        "entry_count": 42,
        "total_duration": 12345.67
      },
      "schedule_summary": {
        "network_name": "PublicDomain",
        "start": "2025-07-13T00:00:00",
        "end": "2025-07-14T00:00:00"
      }
    }
  ]
}
```

#### List All Stations
```http
GET /summary/stations
```
Get a simple list of all station network names.

**Response:**
```json
{
  "network_names": ["PublicDomain", "PBS", "ClassicMovies"]
}
```

### 📅 Schedule Management

#### Get Schedule Summaries
```http
GET /summary/schedules
```
Returns schedule summaries for all stations.

```http
GET /summary/schedules/{network_name}
```
Get schedule summary for a specific station.

#### Get Detailed Schedule Blocks
```http
GET /schedules/{network_name}?start=YYYY-MM-DDTHH:MM:SS&end=YYYY-MM-DDTHH:MM:SS
```

Retrieve detailed schedule blocks with optional time filtering.

**Example:** `GET /schedules/PublicDomain?start=2025-07-13T00:00:00&end=2025-07-14T00:00:00`

**Response:**
```json
{
  "network_name": "PublicDomain",
  "schedule_blocks": [
    {
      "content": [...],
      "start_time": "2025-07-13T00:00:00",
      "end_time": "2025-07-13T00:30:00",
      "title": "quickstop",
      "plan": [...],
      "break_strategy": "standard",
      "break_info": {...}
    }
  ]
}
```

### 📚 Catalog Management

#### Get All Catalog Entries
```http
GET /catalogs/{network_name}
```

#### Search Catalog
```http
GET /catalogs/search/{network_name}?query=search_term
```

#### Get Catalog Summaries
```http
GET /summary/catalogs
```
Returns entry counts for all station catalogs.

### ⚙️ Station Configuration

#### Get Station Config
```http
GET /stations/{network_name}
```
Returns complete configuration for a specific station.

### 🎨 Themes & Styling

#### Get Available Themes
```http
GET /about/themes
```
Lists all available CSS themes for the web interface.

### 🛠️ Build Operations

*Asynchronous operations that return task IDs for status tracking*

#### Rebuild Catalog
```http
POST /build/catalog/{network_name}
```
Rebuilds catalog for specified station (use "all" for all stations).

**Returns:** `{"task_id": "uuid-string"}`

**Check Status:**
```http
GET /build/catalog/status/{task_id}
```

#### Reset Schedule
```http
POST /build/schedule/reset/{network_name}
```
Completely rebuilds schedule for specified station.

**Check Status:**
```http
GET /build/schedule/reset/status/{task_id}
```

#### Add Time to Schedule
```http
POST /build/schedule/add_time/{amount}
```
Adds specified time period to all station schedules (e.g., "1d", "12h", "30m").

**Check Status:**
```http
GET /build/schedule/add_time/status/{task_id}
```

---

## 📺 Play-Time APIs

*For controlling live playback and monitoring your broadcast*

### 🎮 Player Control

#### Channel Control
```http
GET /player/channels/{channel}
```
Change channel. Use a number, "up", or "down".

**Examples:**
- `/player/channels/5` - Switch to channel 5
- `/player/channels/up` - Channel up
- `/player/channels/down` - Channel down

#### Show Program Guide
```http
POST /player/channels/guide
```
Display the on-screen program guide.

#### Stop Player
```http
GET /player/commands/stop
POST /player/commands/stop
```
Gracefully stop the player.

### 🔊 Volume Control

| Endpoint | Description |
|----------|-------------|
| `GET/POST /player/volume/up` | Increase volume by 5% |
| `GET/POST /player/volume/down` | Decrease volume by 5% |
| `GET/POST /player/volume/mute` | Toggle mute on/off |

**Response Example:**
```json
{
  "action": "up",
  "method": "pulseaudio",
  "status": "success",
  "message": "Volume increased by 5%",
  "volume": "75%"
}
```

### 📡 System Monitoring

#### Player Status
```http
GET /player/status
```
Get current player status and program information.

#### System Information
```http
GET /player/info
```
Comprehensive system information including CPU temperature, memory usage, and load averages.

**Response Example:**
```json
{
  "temperature_c": 49.4,
  "temperature_f": 121,
  "temp_source": "vcgencmd",
  "memory": {
    "total_gb": 8.0,
    "available_gb": 6.2,
    "used_gb": 1.8,
    "used_percent": 22.5
  },
  "cpu": {
    "cores": 4,
    "load_1min": 0.15,
    "load_5min": 0.18,
    "load_15min": 0.22,
    "load_percent": 3.8
  },
  "system": {
    "platform": "Linux",
    "architecture": "aarch64",
    "hostname": "fieldstation42"
  }
}
```

#### Connection Status
```http
GET /player/status/queue_connected
```
Check if the player command queue is connected.

---

## 🎯 Pro Tips for Developers

### 📅 Date Format
Always use ISO format for date/time parameters: `YYYY-MM-DDTHH:MM:SS`

### 🔄 Asynchronous Operations
Build operations return task IDs. Always check status endpoints to monitor progress:

```javascript
// Start rebuild
const response = await fetch('/build/catalog/PublicDomain', {method: 'POST'});
const {task_id} = await response.json();

// Monitor progress
const checkStatus = async () => {
  const status = await fetch(`/build/catalog/status/${task_id}`);
  const {status: taskStatus, log} = await status.json();
  
  if (taskStatus === 'done') {
    console.log('Rebuild complete!');
  } else if (taskStatus === 'error') {
    console.error('Rebuild failed:', log);
  } else {
    setTimeout(checkStatus, 1000); // Check again in 1 second
  }
};
```

### 🎵 Volume Control
The API automatically detects and uses the best available audio system:
1. **PulseAudio** (pactl) - Most Linux desktops
2. **ALSA** (amixer) - Raspberry Pi and embedded systems  
3. **WirePlumber** (wpctl) - Modern PipeWire systems

### 🔍 Error Handling
All endpoints return detailed error messages. Always check the response:

```javascript
const response = await fetch('/schedules/NonExistentStation');
if (!response.ok) {
  const error = await response.json();
  console.error('API Error:', error.detail);
}
```

### 🌐 Cross-Origin Requests
The server supports CORS for web development. You can make requests from any origin during development.

---

## 🚀 Example Workflows

### Setting Up a New Station

1. **Check current stations:** `GET /summary/stations`
2. **Build catalog:** `POST /build/catalog/MyNewStation`
3. **Monitor progress:** `GET /build/catalog/status/{task_id}`
4. **Build schedule:** `POST /build/schedule/reset/MyNewStation`
5. **Verify setup:** `GET /summary/`

### Monitoring Live Broadcast

1. **Check player status:** `GET /player/status`
2. **Monitor system health:** `GET /player/info`  
3. **Control playback:** `GET /player/channels/up`
4. **Adjust volume:** `POST /player/volume/up`

### Searching and Managing Content

1. **Search catalog:** `GET /catalogs/search/PublicDomain?query=comedy`
2. **Get schedule:** `GET /schedules/PublicDomain`
3. **Add more content time:** `POST /build/schedule/add_time/1d`

---

## 🔮 Coming Soon

We're constantly improving FieldStation42! Here's what's on the roadmap:

### Build-Time Enhancements
- **Sequence Builder**: `/build/sequences/{network_name}`
- **Breakpoint Manager**: `/build/breakpoints/{network_name}`
- **Bulk Operations**: Multi-station management tools

### Play-Time Features  
- **OSD Control**: `/player/osd/display` - Custom on-screen messages
- **Advanced Commands**: System halt, safe shutdown, restart operations
- **WebSocket Endpoints**: Real-time status updates and live controls

---

## 📞 Need Help?

- **Web Console**: Visit http://localhost:4242 for the graphical interface
- **API Docs**: This document (you're reading it!)
- **Source Code**: Check `fs42_server.py` and the `api/` directory for implementation details

Remember: FieldStation42 is designed to be fun and easy to use. If something seems complicated, we probably need to make it simpler! 🎉

---

*Happy Broadcasting! 📡✨*