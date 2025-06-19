## Logo Display Configuration Guide

The on-screen logo display can be configured at two levels:
1.  **`osd.json`**: Provides global default settings for the logo display.
2.  **`<station>.json`**: Provides station-specific settings, which can override some global defaults and define which logos are used for that particular station.

---

### 1. `osd.json` Configuration

Stores the default and global settings related to Logo Display including:
*   define default logo location display parameters (size, position, margin)
*   define default logo display timing
*   define a global default logo.
*   control whether any logo is shown at all.

**Example `osd.json` (LogoDisplay section only):**
```json
[
    // ... other OSD settings ...
    {
        "type": "LogoDisplay",
        "halign": "RIGHT",
        "valign": "BOTTOM",
        "width": 0.112,
        "height": 0.15,
        "x_margin": 0.05,
        "y_margin": 0.05,
        "display_time": 5.0,
        "always_show": false,
        "default_logo": "fs42/osd/FS42.png",
        "default_logo_alpha": 1.0,
        "default_show_logo": true,
        "default_logo_permanent": false
    }
]
```

**Fields for the `LogoDisplay` object in `osd.json`:**

*   **`type`** (string): **Required**. Must be `"LogoDisplay"` for this configuration block to be recognized.
*   **`halign`** (string, enum: "LEFT", "RIGHT", "CENTER"): **Optional**. Default horizontal alignment of the logo.
*   **`valign`** (string, enum: "TOP", "BOTTOM", "CENTER"): **Optional**. Default vertical alignment of the logo.
*   **`width`** (float): **Optional**. Default logo width, fraction of screen width /2 (ex: 0.1 = 5% of half the screen).
*   **`height`** (float): **Optional**. Default logo height, fraction of screen height /2.
*   **`x_margin`** (float): **Optional**. Default horizontal margin, fraction of screen width /2
*   **`y_margin`** (float): **Optional**. Default vertical margin, fraction of the screen height /2
*   **`display_time`** (float): **Optional**. Default number of seconds logo is shown after channel change or return to "FEATURE" content
*   **`always_show`** (boolean): **Optional**. Default that if true, logo will ignore the `display_time`, but still is only displayed during "FEATURE" content
*   **`default_logo`** (string | null): **Optional**. Path to a global default logo file.
*   **`default_logo_alpha`** (float): **Optional**. Sets the default alpha (transparency) applied to logos (ex: 0.8 - 80% opacity).
*   **`default_show_logo`** (boolean): **Optional**. Controls whether the `default_logo` is ever displayed.
*   **`default_logo_permanent`** (boolean): **Optional**. If true, the `default_logo` will ignore `display_time` and remain visible as long as "FEATURE" content is playing.

---

### 2. `confs/<station>.json` Configuration (Per-Station Settings)

Configuration at each station level that defines station logos, behavior, and overides for global settings.
*   Specifes if a logo should be shown for this station.
*   Defines the location of logo_dir and defines a default logo for this station.
*   Controls if Multiple logos will be used (multi_logo).
*   override global display parameters (size, position, timing, permanent)

**Example `<station>.json`:**
```json
{
    "station_conf": {
    // ... other OSD settings ...

        // Required config for this station to have logo(s):
        "logo_dir": "logos",
        "show_logo": true,
        "default_logo": "station_static.png",
        "logo_permanent": false,
        "multi_logo": "off",

        // Optional logo overrides for this station:
        "logo_display_time": 10.0,
        "logo_halign": "RIGHT",
        "logo_valign": "TOP",
        "logo_width": 0.1,
        "logo_height": 0.12,
        "logo_x_margin": 0.03,
        "logo_y_margin": 0.03,
        "logo_alpha": 0.75

    // ... other station configurations ...
    }
}
```

**Fields within `"station_conf"` for Logo Display:**

*   **`logo_dir`** (string): **Required** (if using station logos). The directory where this station's logos are stored.
*   **`show_logo`** (boolean): **Optional**. Show logo on this station.
*   **`default_logo`** (string): **Optional**. The filename of the station's default logo
*   **`logo_permanent`** (boolean): **Optional**. If true, ignore `logo_display_time` (or the global `display_time`) as long as "FEATURE" content is playing.
*   **`multi_logo`** (string): **Optional**. Controls logo selection behavior for this station.
    *    `"off"` or `"single"` (default): Uses the logo specified by the `default_logo` field
    *    `"random"` or `"multi"`: Randomly selects a logo from all supported image files (`.png`, `.jpg`, `.gif`) found in the station `logo_dir` each time a logo is to be shown.

*   **`logo_display_time`** (float): **Optional**. Overrides `display_time` from `osd.json`
*   **`logo_halign`** (string, enum: "LEFT", "RIGHT", "CENTER"): **Optional**. Overrides `halign` from `osd.json`
*   **`logo_valign`** (string, enum: "TOP", "BOTTOM", "CENTER"): **Optional**. Overrides `valign` from `osd.json`
*   **`logo_width`** (float): **Optional**. Overrides `width` from `osd.json`
*   **`logo_height`** (float): **Optional**. Overrides `height` from `osd.json`
*   **`logo_x_margin`** (float): **Optional**. Overrides `x_margin` from `osd.json`
*   **`logo_y_margin`** (float): **Optional**. Overrides `y_margin` from `osd.json`
*   **`logo_alpha`** (float): **Optional**. Overrides `default_logo_alpha` from `osd.json`.
