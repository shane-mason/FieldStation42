# Station Configuration API

This document describes the REST API endpoints for managing FieldStation42 station configurations.

## Overview

The Station Configuration API provides full CRUD (Create, Read, Update, Delete) operations for managing station configurations via HTTP endpoints. All endpoints are available under the `/stations` prefix.

## Requirements

The Station API requires the `jsonschema` library for configuration validation. If not installed, you will receive an error message with installation instructions.

To install:
```bash
pip install jsonschema
```

Or use the project installer to pick up all dependencies:
```bash
pip install -r install/requirements.txt
```

## Base URL

```
http://localhost:4242/stations
```

## Endpoints

### List All Stations

Get a list of all station configurations.

**Endpoint:** `GET /stations`

**Response:**
```json
{
  "count": 3,
  "stations": [
    {
      "network_name": "Guide",
      "channel_number": 0,
      "network_type": "guide",
      ...
    },
    ...
  ]
}
```

**Example:**
```bash
curl http://localhost:4242/stations
```

---

### Get Single Station

Get a specific station configuration by network name.

**Endpoint:** `GET /stations/{network_name}`

**Parameters:**
- `network_name` (path) - The name of the network/station

**Response:**
```json
{
  "network_name": "MyChannel",
  "station_config": {
    "network_name": "MyChannel",
    "channel_number": 5,
    "network_type": "standard",
    ...
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Station does not exist

**Example:**
```bash
curl http://localhost:4242/stations/MyChannel
```

---

### Create New Station

Create a new station configuration.

**Endpoint:** `POST /stations`

**Request Body:**
```json
{
  "station_conf": {
    "network_name": "NewChannel",
    "channel_number": 42,
    "network_type": "standard",
    "schedule_increment": 30
  }
}
```

**Required Fields:**
- `network_name` - Display name of the network/channel
- `channel_number` - Channel number for tuning

**Response:**
```json
{
  "success": true,
  "message": "Station configuration saved successfully",
  "network_name": "NewChannel",
  "channel_number": 42,
  "file_path": "confs/newchannel.json"
}
```

**Status Codes:**
- `201 Created` - Station created successfully
- `400 Bad Request` - Validation error (missing required fields, invalid schema)
- `409 Conflict` - Station already exists, or channel number/network name in use

**Validation Rules:**
- Network name must be unique across all stations
- Channel number must be unique across all stations
- Configuration must match the [station config schema](../fs42/station_config_schema.json)

**Example:**
```bash
curl -X POST http://localhost:4242/stations \
  -H "Content-Type: application/json" \
  -d '{
    "station_conf": {
      "network_name": "Test Channel",
      "channel_number": 99,
      "network_type": "web",
      "web_url": "http://localhost:4242/test.html"
    }
  }'
```

---

### Update Existing Station

Update an existing station configuration.

**Endpoint:** `PUT /stations/{network_name}`

**Parameters:**
- `network_name` (path) - The current name of the network/station to update

**Request Body:**
```json
{
  "station_conf": {
    "network_name": "NewChannel",
    "channel_number": 43,
    "network_type": "standard",
    "schedule_increment": 60
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Station configuration saved successfully",
  "network_name": "NewChannel",
  "channel_number": 43,
  "file_path": "confs/newchannel.json"
}
```

**Status Codes:**
- `200 OK` - Station updated successfully
- `400 Bad Request` - Validation error
- `404 Not Found` - Station does not exist
- `409 Conflict` - Channel number or network name conflict with another station

**Notes:**
- You can rename a station by changing the `network_name` in the request body
- When renaming, the old configuration file is deleted and a new one is created
- The station is automatically excluded from uniqueness checks (can keep its own channel/name)

**Example:**
```bash
curl -X PUT http://localhost:4242/stations/NewChannel \
  -H "Content-Type: application/json" \
  -d '{
    "station_conf": {
      "network_name": "Updated Channel",
      "channel_number": 43,
      "network_type": "standard"
    }
  }'
```

---

### Delete Station

Delete a station configuration.

**Endpoint:** `DELETE /stations/{network_name}`

**Parameters:**
- `network_name` (path) - The name of the network/station to delete

**Response:**
```json
{
  "success": true,
  "message": "Station 'MyChannel' deleted successfully",
  "network_name": "MyChannel"
}
```

**Status Codes:**
- `200 OK` - Station deleted successfully
- `404 Not Found` - Station does not exist
- `500 Internal Server Error` - Deletion failed

**Notes:**
- A backup file (`.bak`) is created before deletion
- The station configuration is immediately removed from the system (auto-reload)

**Example:**
```bash
curl -X DELETE http://localhost:4242/stations/MyChannel
```

---

## File Management

### Configuration Files

- **Location:** `confs/` directory
- **Naming:** Network names are normalized to lowercase with special characters replaced by underscores
  - Example: `"My Channel 42"` → `confs/my_channel_42.json`
- **Format:** JSON files with `station_conf` wrapper object

### Backups

- Backup files are automatically created before updates and deletions
- Backup extension: `.bak`
- Only one backup is kept (overwrites previous backup)

### Auto-Reload

After any write (create/update) or delete operation, all station configurations are automatically reloaded. This means:
- Changes take effect immediately
- No server restart required
- All stations are re-validated and re-indexed

## Validation

All station configurations are validated against:

1. **JSON Schema** - Defined in [station_config_schema.json](../fs42/station_config_schema.json)
2. **Required Fields:**
   - `network_name` (string)
   - `channel_number` (integer)
3. **Uniqueness Constraints:**
   - Channel numbers must be unique
   - Network names must be unique
4. **File References** - Missing media files generate warnings but don't block creation

## Error Responses

Error responses follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common Errors

**400 Bad Request - Missing Required Field:**
```json
{
  "detail": "Validation failed: 'channel_number' is required"
}
```

**409 Conflict - Duplicate Channel:**
```json
{
  "detail": "Channel number 42 is already used by station 'ExistingChannel'"
}
```

**409 Conflict - Station Already Exists:**
```json
{
  "detail": "Station 'MyChannel' already exists. Use PUT to update."
}
```

**404 Not Found:**
```json
{
  "detail": "Station 'NonExistent' not found"
}
```

## Configuration Schema

For complete details on all available configuration options, see:
- [Station Configuration Reference](STATION_CONFIG_README.md)
- [JSON Schema](../fs42/station_config_schema.json)

## Examples

### Minimal Web Channel

```json
{
  "station_conf": {
    "network_name": "Diagnostics",
    "channel_number": 99,
    "network_type": "web",
    "web_url": "http://localhost:4242/diagnostics.html"
  }
}
```

### Standard Channel with Schedule

```json
{
  "station_conf": {
    "network_name": "Classic TV",
    "channel_number": 5,
    "network_type": "standard",
    "schedule_increment": 30,
    "break_strategy": "standard",
    "commercial_free": false,
    "monday": {
      "20": {"tags": "sitcom"},
      "21": {"tags": "drama"}
    },
    "tuesday": "monday",
    "wednesday": "monday",
    "thursday": "monday",
    "friday": "monday",
    "saturday": {},
    "sunday": {}
  }
}
```

### Loop Channel

```json
{
  "station_conf": {
    "network_name": "Music Videos",
    "channel_number": 50,
    "network_type": "loop",
    "content_dir": "media/music_videos"
  }
}
```

## API Documentation

The FastAPI server provides interactive API documentation:

- **Swagger UI:** http://localhost:4242/docs
- **ReDoc:** http://localhost:4242/redoc

These provide full schema documentation, request/response examples, and a testing interface.

## Notes

- All operations are logged to the FieldStation42 server logs
- Configuration changes are immediately reflected (auto-reload)
- The main configuration file (`confs/main_config.json`) is not accessible via this API
- Atomic file writes are used to prevent corruption
- Thread-safety is handled via the Borg singleton pattern in StationManager
