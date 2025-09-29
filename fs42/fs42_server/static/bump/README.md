# FieldStation42 Bump System

Create customizable station identification bumps with multiple visual styles, background music, and programming information.

## Quick Start

```
bump.html?title=MTV&subtitle=Music Television&variation=retro&bg_music=logo2.mp3
```

## Parameters

| Parameter | Description | Examples |
|-----------|-------------|----------|
| `title` | **Required.** Station name | `"MTV"`, `"CNN"`, `"ESPN"` |
| `subtitle` | Station tagline | `"Music Television"`, `"Breaking News"` |
| `detail1`, `detail2`, `detail3` | Custom info lines | `"Channel 4"`, `"Broadcasting 24/7"` |
| `variation` | Visual style | `"modern"`, `"retro"`, `"corporate"`, `"terminal"` |
| `bg_color` | Background color (hex) | `"#ff0000"`, `"#1a1a2e"` |
| `fg_color` | Text color (hex) | `"#ffffff"`, `"#000000"` |
| `bg` | Background image URL | `"background.jpg"` |
| `css` | Custom CSS file | `"custom.css"` |
| `next_network` | Show upcoming programs | `"nbc"`, `"mtv"`, `"espn"` |
| `duration` | Auto-hide after milliseconds | `5000`, `10000`, `0` (never) |
| `bg_music` | Background music file or URL | `"logo2.mp3"`, `"https://..."` |
| `strategy` | Autobump position| `start`, `end`, `both`|

## Visual Styles

### Modern (Default)
Clean, futuristic design with blue gradients
```
bump.html?title=TECH TV&subtitle=Future Forward&variation=modern
```

### Retro
80s synthwave aesthetic with neon colors
```
bump.html?title=MTV&subtitle=Music Television&variation=retro
```

### Corporate
Professional look with light colors
```
bump.html?title=CNN&subtitle=Breaking News&variation=corporate
```

### Terminal
Monospace terminal theme with green text
```
bump.html?title=HACKER TV&subtitle=System Online&variation=terminal
```

## Background Music

FieldStation42 includes 7 background music tracks: `logo0.mp3` through `logo6.mp3`

```
# Using built-in music
bump.html?title=MTV&variation=retro&bg_music=logo2.mp3

# Using custom music
bump.html?title=RADIO FM&bg_music=https://example.com/theme.mp3
```

**Features:**
- Auto-loops during display
- 30% volume by default
- Fades out when bump ends
- Supports MP3, WAV, OGG, M4A

**Add your own music:**
1. Copy files to `fs42/fs42_server/static/bump/music/`
2. Use filename in `bg_music` parameter

## Programming Integration

Show upcoming shows from FieldStation42 schedule:

```
bump.html?title=HBO&subtitle=Premium Entertainment&next_network=hbo
```

Displays next 3 upcoming shows as: `"2:30 PM - Show Title"`

## Examples

### Basic Station ID
```
bump.html?title=NBC&subtitle=Must See TV&detail1=Channel 4&detail2=nbctv.com
```

### With Music and Programming
```
bump.html?title=MTV&subtitle=Music Television&variation=retro&next_network=mtv&bg_music=logo2.mp3&duration=7000
```

### Custom Colors
```
bump.html?title=ESPN&subtitle=The Worldwide Leader&bg_color=%23ff0000&fg_color=%23ffffff
```

## JavaScript API

For dynamic control:

```javascript
configureBump({
    title: 'DISCOVERY',
    subtitle: 'Explore Your World',
    variation: 'modern',
    bgMusic: 'logo1.mp3',
    duration: 5000
});
```

## JSON Configuration

For autobump system integration:

```json
{
    "title": "FIELDSTATION42",
    "subtitle": "Your Retro Broadcast Experience",
    "variation": "retro",
    "bg_music": "logo2.mp3",
    "duration": 7000,
    "next_network": "fieldstation42"
}
```

## Color Encoding for URLs

Hex colors must be URL-encoded:
- `#ff0000` (red) becomes `%23ff0000`
- `#ffffff` (white) becomes `%23ffffff`

## Advanced Customization

### Custom CSS Override

Create a CSS file and reference it:
```
bump.html?title=LOCAL NEWS&css=custom-styles.css
```

**Common customizations:**
```css
/* Change fonts */
.bump-container .main-title {
    font-family: 'Impact', sans-serif !important;
    font-size: 8rem !important;
}

/* Custom colors and effects */
.bump-container {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
}

.bump-container .content-area {
    border: 5px solid #ffffff;
    border-radius: 20px;
    backdrop-filter: blur(10px);
}
```

### Available CSS Selectors
- `.bump-container` - Main container
- `.main-title` - Station name
- `.subtitle` - Tagline
- `.detail-line` - Info lines
- `.variation-retro`, `.variation-modern`, etc. - Style-specific

## Troubleshooting

**No programming data showing?**
- Verify network name exists in FieldStation42
- Check FieldStation42 server is running

**Music not playing?**
- Check file exists in `music/` folder
- Verify file format (MP3, WAV, OGG, M4A)
- Browser autoplay policies may require user interaction

**Colors not working?**
- URL-encode hex values: `#ff0000` → `%23ff0000`
- Use `!important` in custom CSS if needed

## File Structure
```
fs42/fs42_server/static/bump/
├── bump.html          # Main HTML file
├── bump.css           # Styling and variations
├── bump.js            # JavaScript functionality
├── music/             # Background music files
│   ├── logo0.mp3
│   ├── logo1.mp3
│   └── ...
└── README.md          # This documentation
```