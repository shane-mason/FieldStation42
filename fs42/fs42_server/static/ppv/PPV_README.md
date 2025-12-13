# Pay-Per-View (PPV)

Video-on-demand interface for FieldStation42. Browse movies with page up/down keys, hit ENTER to play. Shows a slideshow with posters, titles, and descriptions.

Metadata handling: checks for local NFO files first, falls back to TMDB API if missing. You can manually curate some content and automate the rest. Optimized for CRT displays.

## Setup

Create a station config file like `confs/ppv_movies.json`:

```json
{
  "station_conf": {
    "network_name": "Movie Library",
    "channel_number": 42,
    "network_type": "web",
    "content_dir": "catalog/ppv",
    "web_url": "/static/ppv/ppv.html"
  }
}
```

Drop your movie files in `catalog/ppv/`. Supported: `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.flv`, `.webm`, `.m4v`

For TMDB matching, put the year in the filename: `The Matrix (1999).mp4`

### TMDB Setup (optional)

Get a free API key at https://www.themoviedb.org/signup (Settings → API → Request an API Key)

Add it to `confs/main_config.json`:
```json
{
  "tmdb_api_key": "your_api_key_here"
}
```

Without TMDB, you'll need to create NFO files manually.

For testing, you can access at `http://localhost:4242/static/ppv/ppv.html?channel=42`

## Controls

- **← →** - Navigate movies
- **ENTER/SPACE** - Play selected movie
- **P** - Pause/resume slideshow (10s auto-advance)

## Manual Metadata

NFO files are just ascii text files - FS42 will parse them looking for the first 3 lines to be:
1. Title
2. Info line (year, artist, etc)
3. Description

Example `The_Big_City.nfo`:
```
The Big City
Unknown Artist
In this feature, they talk about the big city and what that means.
```

Poster images: same base filename as video (`movie.mp4` → `movie.jpg` or `.png`)

## Metadata Priority

1. Local NFO → use it (skip TMDB)
2. Local image → use it (skip TMDB)
3. No NFO → fetch from TMDB
4. No image → use TMDB poster

Mix and match as needed. TMDB data gets cached in `catalog/.tmdb_cache/`

## URL Parameters

- `channel` (required) - channel number
- `duration` - slideshow duration in ms (default: 10000)
- `variation` - theme: `modern`, `retro`, `terminal`
- `css` - custom CSS file
- `bg` - background image
- `bg_color` - background color

Example: `?channel=42&duration=15000&variation=retro`

## Background Music

Create `fs42/fs42_server/static/ppv/music_playlist.json`:

```json
{
  "music_files": [
    "music/track1.mp3",
    "music/track2.mp3"
  ]
}
```

Loops at 30% volume, stops when you play a video.

## API Endpoints

- `GET /ppv/{channel_number}` - list videos with metadata
- `GET /ppv/image/{channel_number}/{filename}` - serve poster images
- `POST /ppv/{channel_number}/play_file` - send play command to player queue

Example play request:
```json
{
  "file_path": "catalog/ppv/The_Matrix_(1999).mp4"
}
```

## Troubleshooting

**Movies not showing?** Check file extensions, verify `content_dir` path, check server logs.

**TMDB not working?** Verify API key in `confs/main_config.json`, include year in filenames. Rate limit is 40 req/10s.

**Posters not loading?** Check filename matches video, browser console for errors.
