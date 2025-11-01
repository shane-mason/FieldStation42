# FieldStation42 Main Configuration Reference

This document describes the main configuration file (`confs/main_config.json`) which contains global settings that apply across all stations.

## Table of Contents
- [Overview](#overview)
- [Configuration Options](#configuration-options)
- [Day Parts](#day-parts)
- [Custom Title Patterns](#custom-title-patterns)

## Overview

The `confs/main_config.json` file is optional. If it doesn't exist, FieldStation42 uses built-in defaults. Any settings you specify will override the defaults.

### Example Configuration

```json
{
  "server_host": "0.0.0.0",
  "server_port": 4242,
  "normalize_titles": true,
  "day_parts": {
    "morning": {"start_hour": 6, "end_hour": 10},
    "daytime": {"start_hour": 10, "end_hour": 18},
    "prime": {"start_hour": 18, "end_hour": 23},
    "late": {"start_hour": 23, "end_hour": 2},
    "overnight": {"start_hour": 2, "end_hour": 6}
  }
}
```

## Configuration Options

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `server_host` | string | `"0.0.0.0"` | Host address for the web server |
| `server_port` | integer | `4242` | Port for the web server |
| `channel_socket` | string | `"runtime/channel.socket"` | Unix socket for channel control |
| `status_socket` | string | `"runtime/play_status.socket"` | Unix socket for status updates |
| `time_format` | string | `"%H:%M"` | Format for displaying times (strftime format) |
| `date_time_format` | string | `"%Y-%m-%dT%H:%M:%S"` | Format for date/time values (strftime format) |
| `start_mpv` | boolean | `true` | Whether to start mpv player automatically |
| `db_path` | string | `"runtime/fs42_fluid.db"` | Path to the SQLite database |
| `normalize_titles` | boolean | `false` | Enable automatic title normalization from filenames |
| `title_patterns` | array | `[]` | Custom regex patterns for title parsing (see below) |

## Day Parts

Day parts define time periods used for scheduling purposes. Each day part has a start and end hour (0-23).

### Configuration

```json
{
  "day_parts": {
    "morning": {"start_hour": 6, "end_hour": 10},
    "daytime": {"start_hour": 10, "end_hour": 18},
    "prime": {"start_hour": 18, "end_hour": 23},
    "late": {"start_hour": 23, "end_hour": 2},
    "overnight": {"start_hour": 2, "end_hour": 6}
  }
}
```

### Wrapping Midnight

When `end_hour` is less than `start_hour`, the period wraps around midnight. For example, `late` runs from 11 PM to 2 AM.

## Custom Title Patterns

When `normalize_titles` is enabled, FieldStation42 automatically parses video filenames to extract clean, display-ready titles. You can add custom regex patterns to handle special naming conventions in your media library.

### Why Use Custom Patterns?

The built-in patterns handle common formats like:
- `Show Name - s01e05.mp4` → "Show Name"
- `Movie (2020).mp4` → "Movie"
- `[Group] Title - 03.mkv` → "Title"

But if your files use a unique naming scheme, you can add custom patterns to parse them correctly.

### Pattern Format

Each pattern is an object with three fields:

```json
{
  "pattern": "regex pattern here",
  "group": 1,
  "description": "What this pattern matches"
}
```

- **pattern**: A regular expression string (remember to escape backslashes in JSON!)
- **group**: The capture group number containing the title (usually `1`)
- **description**: Optional human-readable description

### Example Patterns

```json
{
  "title_patterns": [
    {
      "pattern": "^\\[Studio\\][\\s._-]+(.+?)[\\s._-]+Special.*$",
      "group": 1,
      "description": "Studio specials with [Studio] prefix"
    },
    {
      "pattern": "^(.+?)[\\s._-]+HD[\\s._-]+\\d+p.*$",
      "group": 1,
      "description": "Videos with HD quality markers"
    },
    {
      "pattern": "^(.+?)_REMASTER_\\d{4}.*$",
      "group": 1,
      "description": "Remastered content"
    }
  ]
}
```

### How It Works

1. Custom patterns are tried **first**, in the order you specify
2. If a custom pattern matches, that title is used
3. If no custom pattern matches, built-in patterns are tried
4. The first matching pattern wins

**Example:**

Filename: `[Studio] My Great Show - Special Edition.mp4`

- **Without custom pattern**: "My Great Show Special Edition"
- **With pattern above**: "My Great Show"

### JSON Regex Escaping Guide

JSON requires backslashes to be escaped. Here's a quick reference:

| Regex Pattern | In JSON String |
|---------------|----------------|
| `\d` (any digit) | `"\\d"` |
| `\s` (whitespace) | `"\\s"` |
| `\w` (word character) | `"\\w"` |
| `\.` (literal period) | `"\\."` |
| `\[` (literal bracket) | `"\\["` |
| `[abc]` (character class) | `"[abc]"` *(no escape)* |
| `(group)` (capture group) | `"(group)"` *(no escape)* |
| `.*` (zero or more) | `".*"` *(no escape)* |
| `.+?` (non-greedy) | `".+?"` *(no escape)* |

### Common Separator Pattern

Many patterns use a "separator" regex to match spaces, dots, underscores, and dashes:

```json
"pattern": "^(.+?)[\\s._-]+Episode[\\s._-]+\\d+$"
```

This matches titles like:
- `Show Title Episode 05.mp4`
- `Show.Title.Episode.05.mp4`
- `Show_Title_Episode_05.mp4`
- `Show-Title-Episode-05.mp4`

### Testing Your Patterns

Before adding patterns to your config:

1. Test your regex using a tool like [regex101.com](https://regex101.com)
2. Make sure to select the Python flavor
3. Remember to add the JSON escaping when copying to your config
4. Check the FieldStation42 logs on startup - they will show if patterns fail to compile

### Example: Complete Configuration

```json
{
  "server_port": 4242,
  "normalize_titles": true,
  "title_patterns": [
    {
      "pattern": "^\\[STUDIO\\][\\s._-]+(.+?)[\\s._-]+\\d{4}[\\s._-]+\\d+.*$",
      "group": 1,
      "description": "Studio releases with year and episode"
    },
    {
      "pattern": "^(.+?)[\\s._-]+REMASTERED[\\s._-]+.*$",
      "group": 1,
      "description": "Remastered editions"
    }
  ],
  "day_parts": {
    "morning": {"start_hour": 6, "end_hour": 10},
    "daytime": {"start_hour": 10, "end_hour": 18},
    "prime": {"start_hour": 18, "end_hour": 23},
    "late": {"start_hour": 23, "end_hour": 2},
    "overnight": {"start_hour": 2, "end_hour": 6}
  }
}
```

## Validation and Error Handling

When FieldStation42 loads `main_config.json`:

1. **Pattern validation**: Each regex pattern is compiled to check for syntax errors
2. **Required fields**: Patterns must have both `pattern` and `group` fields
3. **Logging**: Successfully loaded patterns are logged with their descriptions
4. **Error recovery**: Invalid patterns are logged and skipped (they won't crash the system)

Check your logs on startup to verify your patterns loaded correctly:

```
INFO: Loaded custom title pattern: Studio releases with year and episode
INFO: Loaded custom title pattern: Remastered editions
INFO: Loaded 2 custom title pattern(s)
```

## Best Practices

1. **Start simple**: Add one pattern at a time and test it
2. **Order matters**: Put more specific patterns first
3. **Be precise**: Use `^` and `$` anchors to match the whole filename
4. **Use non-greedy**: `.+?` instead of `.+` to avoid over-matching
5. **Document**: Always include a description for future reference
6. **Test filenames**: Verify your patterns work with actual filenames from your library
