# FieldStation42 Main Configuration Reference

This document describes the main configuration file (`confs/main_config.json`) which contains global settings that apply across all stations.

## Table of Contents
- [Overview](#overview)
- [Configuration Options](#configuration-options)
- [Day Parts](#day-parts)
- [Custom Holidays](#custom-holidays)
- [Following Symlinks in Static Directories](#following-symlinks-in-static-directories)
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
| `custom_holidays` | object | `{}` | Named yearly dates to use in schedules and hints (see below) |
| `follow_static_symlinks` | boolean | `false` | Serve symlinks that point outside the static directories (see below) |
| `api_key` | string | none | Requires this key for the web console and API. Not set means no security (see [API_SECURITY.md](API_SECURITY.md)) |

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

## Custom Holidays

Custom holidays give a name to a date that comes around every year. Define them once here and use the name in any station.

```json
{
  "custom_holidays": {
    "thanksgiving": "4th thursday november",
    "christmas": "December 25",
    "memorial_day": "last monday may",
    "station_anniversary": "September 30"
  }
}
```

### Date Formats

Each holiday is either:

- **A fixed date**: a full month name and a day, like `"December 25"`. It's always that date, even on a weekend
- **A weekday rule**: `1st`, `2nd`, `3rd`, `4th` or `last`, then a weekday and a month, like `"4th thursday november"` or `"last monday may"`

Month names must be spelled out in full. Upper or lower case doesn't matter in the date.

### Using Holidays

Use the holiday's name in a station config:

- **Date overrides**: `"date_overrides": {"thanksgiving": "holiday_day"}` uses a day template on that day. In the visual station editor, add a date and choose **Holiday**
- **Marathon hints**: `"marathon": {"chance": 1.0, "count": 8, "hint": "thanksgiving"}`
- **Meta hints**: `{"tags": "specials/parades", "custom_holiday": "thanksgiving"}`
- **Folder names**: a folder named `thanksgiving` in a catalog only plays on that day

### Naming Rules

- Names are matched exactly, including upper and lower case. A folder named `Thanksgiving` doesn't match a holiday named `thanksgiving`
- A name can't also read as another kind of hint: a month, a quarter like `Q4`, a weekday, a day part, a week number like `week number 20`, a date range or a bump position like `pre`. FieldStation42 won't load a config with a name like that
- If a date override uses a holiday that isn't defined here, its station won't load. A marathon hint with an unknown name logs a warning, and the marathon runs on its chance alone

## Following Symlinks in Static Directories

By default, the web server won't serve a symlink that points outside of the static directories.
Enable `follow_static_symlinks` to keep themes or guide videos elsewhere on disk:

```json
{
  "follow_static_symlinks": true
}
```

```bash
ln -s ~/my-themes/vaporwave.css fs42/fs42_server/static/themes/vaporwave.css
ln -s /mnt/media/bumpers/guide_loop.mp4 runtime/guide_videos/guide_loop.mp4
```

Linked themes show up in the theme picker automatically.

Note that the web server has no authentication, so whatever you link in is readable by anyone on
your network - only link the files you intend to serve.

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
