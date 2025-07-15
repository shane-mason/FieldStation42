# FieldStation42 Server Reference

This document describes the REST API endpoints provided by the FieldStation42 server (`fs42_server.py`). All endpoints return JSON responses. Example URLs assume the server is running on `http://localhost:4242`.

The endpoints are broken into two main themes: buildtime and playtime.
- Buildtime: these are the functions available in station_42.py and are generally system administration functions you use to set your system up.
- Playtime: these are functions that you would use when the system is already running.

General server configurations are available in `main_config.json`:

```json
"server_host": "0.0.0.0",
"server_port": 4242
```

## Endpoints - Buildtime

### 1. Root
- **GET /**
  - Returns the main web UI (`index.html`).

### 2. Station Summary
- **GET /summary/**
  - Returns a summary of all stations, including catalog and schedule info.
  - **Example:**
    - `http://localhost:8080/summary/`
  - **Response:**
    ```json
    {
      "summary_data": [
        {
          "network_name": "PublicDomain",
          "catalog_summary": { ... },
          "schedule_summary": { ... }
        },
        ...
      ]
    }
    ```

### 3. Station List
- **GET /summary/stations**
  - Returns a list of all station network names.
  - **Example:**
    - `http://localhost:8080/summary/stations`
  - **Response:**
    ```json
    { "network_names": ["PublicDomain", "PBS", ...] }
    ```

### 4. Schedule Summaries
- **GET /summary/schedules**
  - Returns schedule summaries for all stations.
  - **Example:**
    - `http://localhost:8080/summary/schedules`
  - **Response:**
    ```json
    { "schedule_summaries": [ ... ] }
    ```

- **GET /summary/schedules/{network_name}**
  - Returns schedule summary for a specific station.
  - **Example:**
    - `http://localhost:8080/summary/schedules/PublicDomain`
  - **Response:**
    ```json
    { "schedule_summary": { ... } }
    ```

### 5. Catalog Summaries
- **GET /summary/catalogs**
  - Returns catalog entry counts for all stations.
  - **Example:**
    - `http://localhost:8080/summary/catalogs`
  - **Response:**
    ```json
    { "catalog_summaries": [ { "network_name": "PublicDomain", "entry_count": 42 }, ... ] }
    ```

### 6. Station Config
- **GET /stations/{network_name}**
  - Returns configuration for a specific station.
  - **Example:**
    - `http://localhost:8080/stations/PublicDomain`
  - **Response:**
    ```json
    { "network_name": "PublicDomain", "station_config": { ... } }
    ```

### 7. Catalog Entries
- **GET /catalogs/{network_name}**
  - Returns all catalog entries for a station.
  - **Example:**
    - `http://localhost:8080/catalogs/PublicDomain`
  - **Response:**
    ```json
    { "network_name": "PublicDomain", "catalog_entries": [ ... ] }
    ```

- **GET /catalogs/search/{network_name}?query=foo**
  - Search catalog entries for a station by query string.
  - **Example:**
    - `http://localhost:8080/catalogs/search/PublicDomain?query=foo`
  - **Response:**
    ```json
    { "network_name": "PublicDomain", "query": "foo", "catalog_entries": [ ... ] }
    ```

### 8. Schedule Blocks
- **GET /schedules/{network_name}?start=YYYY-MM-DDTHH:MM:SS&end=YYYY-MM-DDTHH:MM:SS**
  - Returns schedule blocks for a station, optionally filtered by start/end ISO datetime.
  - **Example:**
    - `http://localhost:8080/schedules/PublicDomain?start=2025-07-13T00:00:00&end=2025-07-14T00:00:00`
  - **Response:**
    ```json
    { "network_name": "PublicDomain", "schedule_blocks": [ ... ] }
    ```

## Notes
- All endpoints return JSON.
- Date/time parameters should be in ISO format: `YYYY-MM-DDTHH:MM:SS`.
- Catalog and schedule data structures may contain nested objects and lists.
- For more details, see the source code in `fs42_server.py` and related modules.

## Next Up - Build-Time Actions
The following endpoints are planned to be implemented in the buildtime API

### (Re)Build Catalog
- Will rebuild the catalog for specified or all channels

### (Re)Build Schedule
- Will add the specified time period to the schedule

### (Re)Build Sequences
- Will build or rebuild sequences

### (Re)Build Breakpoints
- Will build or rebuild breakpoints

## Next Up - Play-Time Actions
The following endpoints are planned to be implemented in the playtime API

### OSD Display Text
- Will display supplied text on the OSD based - positioning based on OSD configuration.

### Play Status
- Same as the current play_status.socket

### Channel Command
- Same as current channel.socket, only through web API

### Volume Command
- Change the system volume

### Halt Command
- Safely halt the system - (sudo halt)

### Shutdown FS42
- Safely close all FS42 apps, but leave the device powered on

