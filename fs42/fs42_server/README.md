# FieldStation42 Server Reference

This document describes the REST API endpoints provided by the FieldStation42 server (`fs42_server.py`). All endpoints return JSON responses. Example URLs assume the server is running on `http://localhost:4242`.

The endpoints are broken into two main themes: buildtime and playtime.
- Buildtime: these are the functions available in station_42.py and are generally system administration functions you use to set your system up.
- Playtime: these are functions that you would use when the system is already running.

General server configurations are available in `main_config.json`, with the defaults shown below:

```json
"server_host": "0.0.0.0",
"server_port": 4242
```

To start the server for build-time usage, start station_42 like this:

```python
python3 station_42.py --server
```

This will start the API and the web console, you can access it by visiting http://localhost:4242 in your browser.

## Endpoints - Buildtime

This section describes the endpoints that are currently implemented in the Buildtime. Endpoints planned for the future are described at the end of this document.

### Console: Root
- **GET /**
  - Returns the main web UI (`index.html`).
  - **Response:**
    - HTML file

### API: Station Summary
- **GET /summary/**
  - Returns a summary of all stations, including catalog and schedule info.
  - **Example:**
    - `http://localhost:4242/summary/`
  - **Response Type:**
    - Object with key `summary_data` containing a list of station summary objects.
  - **Example Response:**
    ```json
    {
      "summary_data": [
        {
          "network_name": "PublicDomain",
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
    
    
### API: Station List
- **GET /summary/stations**
  - Returns a list of all station network names.
  - **Example:**
    - `http://localhost:4242/summary/stations`
  - **Response Type:**
    - Object with key `network_names` containing a list of strings.
  - **Example Response:**
    ```json
    { "network_names": ["PublicDomain", "PBS"] }
    ```

### API: Schedule Summaries
- **GET /summary/schedules**
  - Returns schedule summaries for all stations.
  - **Example:**
    - `http://localhost:4242/summary/schedules`
  - **Response Type:**
    - Object with key `schedule_summaries` containing a list of schedule summary objects.
  - **Example Response:**
    ```json
    { "schedule_summaries": [ { "network_name": "PublicDomain", "start": "2025-07-13T00:00:00", "end": "2025-07-14T00:00:00" } ] }
    ```

- **GET /summary/schedules/{network_name}**
  - Returns schedule summary for a specific station.
  - **Example:**
    - `http://localhost:4242/summary/schedules/PublicDomain`
  - **Response Type:**
    - Object with key `schedule_summary` containing a schedule summary object.
  - **Example Response:**
    ```json
    { "schedule_summary": { "network_name": "PublicDomain", "start": "2025-07-13T00:00:00", "end": "2025-07-14T00:00:00" } }
    ```

### API: Catalog Summaries
- **GET /summary/catalogs**
  - Returns catalog entry counts for all stations.
  - **Example:**
    - `http://localhost:4242/summary/catalogs`
  - **Response Type:**
    - Object with key `catalog_summaries` containing a list of catalog summary objects.
  - **Example Response:**
    ```json
    { "catalog_summaries": [ { "network_name": "PublicDomain", "entry_count": 42 } ] }
    ```

### API: Station Config
- **GET /stations/{network_name}**
  - Returns configuration for a specific station.
  - **Example:**
    - `http://localhost:4242/stations/PublicDomain`
  - **Response Type:**
    - Object with keys `network_name` and `station_config` (station config is a nested object).
  - **Example Response:**
    ```json
    { "network_name": "PublicDomain", "station_config": { "network_name": "PublicDomain", "_has_schedule": true, ... } }
    ```

### 7. Catalog Entries
- **GET /catalogs/{network_name}**
  - Returns all catalog entries for a station.
  - **Example:**
    - `http://localhost:4242/catalogs/PublicDomain`
  - **Response Type:**
    - Object with keys `network_name` and `catalog_entries` (list of catalog entry objects).
  - **Example Response:**
    ```json
    { "network_name": "PublicDomain", "catalog_entries": [ { "path": "catalog/public_domain/quickstop/Designfo1956_512kb.mp4", "title": "Designfo1956_512kb", "duration": 556.79, ... } ] }
    ```

- **GET /catalogs/search/{network_name}?query=foo**
  - Search catalog entries for a station by query string.
  - **Example:**
    - `http://localhost:4242/catalogs/search/PublicDomain?query=foo`
  - **Response Type:**
    - Object with keys `network_name`, `query`, and `catalog_entries` (list of catalog entry objects).
  - **Example Response:**
    ```json
    { "network_name": "PublicDomain", "query": "foo", "catalog_entries": [ { "path": "catalog/public_domain/quickstop/Designfo1956_512kb.mp4", "title": "Designfo1956_512kb", "duration": 556.79, ... } ] }
    ```

### API: Schedule Blocks
- **GET /schedules/{network_name}?start=YYYY-MM-DDTHH:MM:SS&end=YYYY-MM-DDTHH:MM:SS**
  - Returns schedule blocks for a station, optionally filtered by start/end ISO datetime.
  - **Example:**
    - `http://localhost:4242/schedules/PublicDomain?start=2025-07-13T00:00:00&end=2025-07-14T00:00:00`
  - **Response Type:**
    - Object with keys `network_name` and `schedule_blocks` (list of schedule block objects).
  - **Example Response:**
    ```json
    {
      "network_name": "PublicDomain",
      "schedule_blocks": [
        {
          "content": [ { "path": "catalog/public_domain/quickstop/Designfo1956_512kb.mp4", "title": "Designfo1956_512kb", "duration": 556.79, ... } ],
          "start_time": "2025-07-13T00:00:00",
          "end_time": "2025-07-13T00:30:00",
          "title": "quickstop",
          "plan": [ { "path": "catalog/public_domain/quickstop/Designfo1956_512kb.mp4", "skip": 0, "duration": 556.79, ... } ],
          "break_strategy": "standard",
          "break_info": { "start_bump": null, "end_bump": null, "bump_dir": "bump", "commercial_dir": "commercial" }
        }
      ]
    }
    ```

## Notes
- All endpoints return JSON.
- Date/time parameters should be in ISO format: `YYYY-MM-DDTHH:MM:SS`.
- Catalog and schedule data structures may contain nested objects and lists.
- For more details, see the source code in `fs42_server.py` and related modules.

## Next Up - Build-Time Actions
The following endpoints are planned to be implemented in the buildtime API.

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
- Will display supplied text on the OSD based - positioning based on OSD configuration - along with an audio file if specified.

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

## Consolidating Interfaces
The OSD and WebRemote will be exposed under this API moving forward.
