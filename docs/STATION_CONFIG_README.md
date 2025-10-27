# FieldStation42 Station Configuration Reference

This document describes the configuration format for FieldStation42 station/channel configurations.

## Table of Contents
- [Overview](#overview)
- [Required Properties](#required-properties)
- [Network Types](#network-types)
- [Top-Level Properties](#top-level-properties)
- [Day Scheduling](#day-scheduling)
- [Time Slot Configuration](#time-slot-configuration)
- [Advanced Features](#advanced-features)
- [Examples](#examples)

## Overview

Each station is configured via a JSON file in the `confs/` directory. The configuration file must contain a top-level `station_conf` object with the station's settings.

### Minimal Configuration

```json
{
  "station_conf": {
    "network_name": "MyChannel",
    "channel_number": 5
  }
}
```

All other properties have sensible defaults applied by the system.

### Default Values

If not specified, the following defaults are automatically applied:

| Property | Default Value |
|----------|---------------|
| `network_type` | `"standard"` |
| `schedule_increment` | `30` |
| `break_strategy` | `"standard"` |
| `commercial_free` | `false` |
| `clip_shows` | `[]` |
| `break_duration` | `120` |
| `hidden` | `false` |

## Required Properties

Only two properties are **strictly required**:

| Property | Type | Description |
|----------|------|-------------|
| `network_name` | string | Display name of the network/channel |
| `channel_number` | integer | Channel number for tuning |

## Network Types

The `network_type` property determines how the station operates:

| Type | Description | Common Use Case |
|------|-------------|-----------------|
| `standard` | Traditional TV station with scheduled programming | Broadcast channels with hourly schedules |
| `web` | Embeds a web page as the channel | Diagnostic pages, web content |
| `guide` | Interactive program guide display | Channel 0 / EPG |
| `loop` | Continuously loops content | Simple playlist channels |
| `streaming` | Plays external streaming sources | Live streams, HLS/m3u8 feeds |

## Top-Level Properties

### General Properties

| Property | Type | Description | Valid Values |
|----------|------|-------------|--------------|
| `network_name` | string | **Required.** Name of the network | Any string |
| `network_long_name` | string | Extended/full network name | Any string |
| `channel_number` | integer | **Required.** Channel number | Any positive integer |
| `network_type` | string | Type of network operation | `"standard"`, `"web"`, `"guide"`, `"loop"`, `"streaming"` |
| `hidden` | boolean | Hide channel from guide listings | `true`, `false` |

### Scheduling Properties (Standard Networks)

| Property | Type | Description | Valid Values |
|----------|------|-------------|--------------|
| `schedule_increment` | integer | Time slot increment in minutes | `0` (continuous), `30`, `60`, etc. |
| `schedule_offset` | integer | Offset in minutes from start of hour for showtimes | `5` (shows at :05, :35), `15` (shows at :15, :45), etc. |
| `break_strategy` | string | When to insert commercial breaks | `"standard"` (interspersed), `"end"` (end of program), `"center"` (single break in middle) |
| `commercial_free` | boolean | Whether channel has commercials | `true`, `false` |
| `break_duration` | integer | Duration of commercial breaks in seconds | Any positive integer (default: `120`) |
| `fallback_tag` | string | Tag/folder used when no content is found for a scheduled slot | Any valid tag string |

### Directory Paths

| Property | Type | Description |
|----------|------|-------------|
| `content_dir` | string | Directory containing video content files |
| `bump_dir` | string | Directory containing bump/interstitial videos |
| `commercial_dir` | string | Directory containing commercial videos |
| `runtime_dir` | string | Directory for runtime data (schedules, catalogs) |

### Media Files

| Property | Type | Description |
|----------|------|-------------|
| `standby_image` | string | Image shown when channel is on standby |
| `be_right_back_media` | string | Image/video shown during brief interruptions |
| `sign_off_video` | string | Video played during sign-off event |
| `off_air_video` | string | Video/pattern shown when off-air |

### Data Files

| Property | Type | Description |
|----------|------|-------------|
| `catalog_path` | string | Path to binary catalog file (`.bin`) |
| `schedule_path` | string | Path to binary schedule file (`.bin`) |

### Clip Shows

| Property | Type | Description |
|----------|------|-------------|
| `clip_shows` | array | List of clip show configurations |

Clip shows can be specified as:
- **Simple string**: `"show_tag"` (defaults to 60-minute duration)
- **Object**: `{"tags": "show_tag", "duration": 30}` (duration in minutes)

Example:
```json
"clip_shows": [
  "quickstop",
  {"tags": "variety", "duration": 30}
]
```

The system automatically adjusts durations based on `break_strategy` to account for commercial time.

### Fallback Content

| Property | Type | Description |
|----------|------|-------------|
| `fallback_tag` | string | Tag/folder to use when no matching content is found |

When the scheduler cannot find content matching the scheduled tags (e.g., due to filtering or empty catalog), it will attempt to use content from the `fallback_tag` directory instead. This is useful for generic content that should only play when all other scheduled content has been filtered out.

Example:
```json
"fallback_tag": "generic-content"
```

If no `fallback_tag` is specified and content is not found, the scheduler will generate an error and stop.

### Display Properties

| Property | Type | Description |
|----------|------|-------------|
| `video_keepaspect` | boolean | Maintain video aspect ratio (default: `true`) |
| `panscan` | number | MPV panscan value (e.g., `1.0`) to fill screen by cropping top/bottom and left/right edges |
| `fullscreen` | boolean | Display in fullscreen mode |
| `width` | integer | Window width (pixels) |
| `height` | integer | Window height (pixels) |
| `window_decorations` | boolean | Show window decorations |

### Video Effects

| Property | Type | Description |
|----------|------|-------------|
| `video_scramble_fx` | string | Apply preset scrambling effect (see values below) |
| `station_fx` | string | Custom FFMPEG video filter string (ignored if `video_scramble_fx` is set) |

**Available `video_scramble_fx` values:**
- `horizontal_line` - Classic cable horizontal line scrambling
- `diagonal_lines` - Deep scrambling with diagonal patterns
- `static_overlay` - Static distortion overlay with rapid effects
- `pixel_block` - Heavy pixelation with random blocks
- `color_inversion` - Horizontal bars with inverted colors
- `severe_noise` - Intense noise effect
- `wavy` - Wavy distortion pattern
- `random_block` - Random block replacement distortion
- `chunky_scramble` - Complex realistic scramble effect

### On-Screen Display (Logo) Properties

| Property | Type | Description |
|----------|------|-------------|
| `logo_dir` | string | Directory containing logo image files |
| `show_logo` | boolean | Whether to display station logo on screen |
| `default_logo` | string | Default logo filename (e.g., `"StationLogo.png"`) |
| `logo_permanent` | boolean | If `true`, logo stays on screen; if `false`, may appear/disappear |
| `multi_logo` | string | Multi-logo configuration identifier |

### Web Network Properties

| Property | Type | Description |
|----------|------|-------------|
| `web_url` | string | URL to display (e.g., `"http://localhost:4242/diagnostics.html"`) |

### Guide Network Properties

| Property | Type | Description |
|----------|------|-------------|
| `messages` | array of strings | Text messages to display |
| `images` | array of strings | Image paths to display |
| `play_sound` | boolean | Whether to play background sound |
| `sound_to_play` | string | Path to audio file |
| `scroll_speed` | number | Speed of scrolling (e.g., `1.0`) |

### Streaming Network Properties

| Property | Type | Description |
|----------|------|-------------|
| `streams` | array of objects | Stream definitions |

Each stream object contains:
```json
{
  "url": "https://example.com/stream.m3u8",
  "duration": 30,
  "title": "Stream Title"
}
```

## Day Scheduling

**Standard networks require all 7 days to be defined** (even if they're empty `{}`). Days are specified using lowercase full names:

- `monday`
- `tuesday`
- `wednesday`
- `thursday`
- `friday`
- `saturday`
- `sunday`

### Direct Scheduling

Define hour-by-hour slots directly:

```json
"monday": {
  "0": {"tags": "late-night"},
  "1": {"tags": "late-night"},
  "6": {"tags": "morning"},
  "12": {"tags": "daytime"},
  "20": {"tags": "primetime"}
}
```

**Note:** Hours not specified are treated as **off-air**. Days can be empty objects `{}` if the entire day is off-air, but all 7 days must be present in the configuration.

### Template References

Create reusable schedules using `day_templates`:

```json
"day_templates": {
  "weekday": {
    "6": {"tags": "morning"},
    "12": {"tags": "daytime"},
    "20": {"tags": "primetime"}
  }
},
"monday": "weekday",
"tuesday": "weekday",
"wednesday": "weekday"
```

**Processing:** Template references are resolved during config preprocessing by `ConfigProcessor._process_templates()`.

## Time Slot Configuration

Each hour slot is an object that can contain:

### Basic Properties

| Property | Type | Description |
|----------|------|-------------|
| `tags` | string or array | Content tag(s) to select from catalog |
| `event` | string | Special event (`"signoff"`) |

### Tag Selection

Tags can be:
- **Single string**: `"tags": "sitcom"`
- **Array** (for half-hour splits): `"tags": ["show1", "show2"]`
  - First half-hour (0-29 minutes): uses first tag
  - Second half-hour (30-59 minutes): uses second tag
- **Array with `random_tags`**: Randomly selects from the array

### Bump/Commercial Overrides

| Property | Type | Description |
|----------|------|-------------|
| `start_bump` | string | Path to bump video before content |
| `end_bump` | string | Path to bump video after content |
| `bump_dir` | string | Override bump directory for this slot |
| `commercial_dir` | string | Override commercial directory for this slot |
| `video_scramble_fx` | string or boolean | Apply video scrambling effect (see available effects above) or `false` to disable |

### Scheduling Overrides

| Property | Type | Description |
|----------|------|-------------|
| `schedule_increment` | integer | Override time increment for this slot |
| `break_strategy` | string | Override break strategy (`"standard"`, `"end"`, or `"center"`) |

### Sequences

Sequences allow playing episodes in order from a specific range:

| Property | Type | Description |
|----------|------|-------------|
| `sequence` | string | Sequence identifier |
| `sequence_start` | number | Starting point (0.0 to 1.0) |
| `sequence_end` | number | Ending point (0.0 to 1.0) |

Example:
```json
{
  "tags": "golden_girls",
  "sequence": "gg-season1",
  "sequence_start": 0.0,
  "sequence_end": 0.5
}
```

This plays the first half of the `gg-season1` sequence in order.

### Marathons

Trigger probabilistic multi-episode marathons:

| Property | Type | Description |
|----------|------|-------------|
| `marathon` | object | Marathon configuration |

Marathon object contains:
- `chance`: Probability (0.0 to 1.0) of marathon occurring
- `count`: Number of episodes to play consecutively

Example:
```json
{
  "tags": "real_people",
  "marathon": {
    "chance": 0.5,
    "count": 6
  }
}
```

This has a 50% chance of playing 6 consecutive episodes.

**Processing:** Marathons are detected and executed by `MarathonAgent` during schedule building.

### Slot Overrides

Define named override sets for reuse across multiple time slots:

```json
"slot_overrides": {
  "prime_slots": {
    "start_bump": "caps/primetime_start.mp4",
    "end_bump": "caps/primetime_end.mp4",
    "break_strategy": "end",
    "schedule_increment": 60
  }
},
"monday": {
  "20": {"tags": "drama", "overrides": "prime_slots"},
  "21": {"tags": "sitcom", "overrides": "prime_slots"}
}
```

**Processing:** The `overrides` key is resolved by `ConfigProcessor._process_strategy()`, which inlines the properties and removes the `overrides` key.

**Overridable Properties:**
- `start_bump`, `end_bump`
- `bump_dir`, `commercial_dir`
- `break_strategy`
- `sequence`, `sequence_start`, `sequence_end`
- `schedule_increment`
- `random_tags`
- `video_scramble_fx`
- `marathon`

### Random Tag Selection

```json
{
  "tags": ["show1", "show2", "show3"],
  "random_tags": true
}
```

Randomly selects one tag from the array for each scheduling operation.

### Continued Slots

Use `"continued": true` to inherit the previous hour's tags (applies tag smoothing):

```json
"monday": {
  "20": {"tags": "movie"},
  "21": {"continued": true},
  "22": {"continued": true}
}
```

**Processing:** Tag smoothing is applied by `SlotReader.smooth_tags()` during station initialization.

## Advanced Features

### Autobump

Automatically generate bump videos with metadata:

```json
"autobump": {
  "title": "NBC TV",
  "subtitle": "Classic Television",
  "variation": "retro",
  "detail1": "Line 1 of details",
  "detail2": "Line 2 of details",
  "detail3": "Line 3 of details",
  "bg_music": "logo1.mp3",
  "strategy": "both"
}
```

| Property | Description |
|----------|-------------|
| `strategy` | When to show autobumps: `"both"`, `"start"`, `"end"` |
| `variation` | Visual style variant |

### Configuration Processing Pipeline

1. **Load JSON** (`StationManager.load_json_stations()`)
2. **Preprocess** (`ConfigProcessor.preprocess()`)
   - Resolve template references
   - Inline slot overrides
3. **Apply Defaults** (from `__overwatch`)
4. **Normalize Clip Shows** (convert to duration objects)
5. **Smooth Tags** (for standard networks via `SlotReader.smooth_tags()`)
6. **Add Metadata** (`_has_catalog`, `_has_schedule`)


## Validation

A JSON Schema is provided at `station_config_schema.json` for validation. Use the included `validate_configs.py` script:

```bash
python3 validate_configs.py
```

## Notes

- **File paths** in configuration are relative to the FieldStation42 root directory
- **Hour keys** in day schedules are strings (`"0"` through `"23"`)
- **Off-air hours** are simply omitted from the schedule
- **Template and override references** are case-sensitive
- **Network types** without schedules: `guide`, `streaming`, `web`
- **Network types** without catalogs: `guide`, `streaming`, `web`

## See Also

- `confs/examples/` - Example configuration files
- `station_config_schema.json` - JSON Schema for validation
- `fs42/config_processor.py` - Configuration preprocessing logic
- `fs42/slot_reader.py` - Schedule slot reading logic
- `fs42/station_manager.py` - Station loading and initialization
