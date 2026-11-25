# Pay-Per-View (PPV)

FieldStation42 includes two PPV interfaces:

- `ppv.html` shows the library as a poster slideshow.
- `ppv_list.html` shows a scrollable movie list with a details panel. It can also provide search, filters, and sorting.
Both interfaces read the station's `content_dir`, use local NFO and poster files when available, and can fall back to TMDB metadata. For the separate movie-and-show interface, see `../media_browser/README.md`.

## Create a PPV List Station

Create a station configuration such as `confs/ppv_library.json`:

```json
{
  "station_conf": {
    "network_name": "PPV Library",
    "channel_number": 43,
    "network_type": "web",
    "hidden": false,
    "content_dir": "catalog/ppv",
    "web_url": "http://localhost:4242/static/ppv/ppv_list.html?channel=43&resolution=480i&searchable=true"
  }
}
```

The `channel` value in `web_url` must match `channel_number`. Use `localhost` for a page served by FieldStation42 itself so the player and remote can communicate with it correctly.

Place movies in the configured content directory:

```text
catalog/ppv/
├── The Matrix (1999).mp4
├── The Matrix (1999).nfo
└── The Matrix (1999).jpg
```

Supported video extensions are `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.flv`, `.webm`, and `.m4v`.

After adding or changing the station config, reload the FieldStation42 station data or restart the player and Web UI services.

## PPV List URL Parameters

`ppv_list.html` accepts these parameters:

| Parameter | Values | Description |
| --- | --- | --- |
| `channel` | Channel number | Required. Must identify the station whose `content_dir` will be listed. |
| `resolution` | `480i`, `1080i` | Applies the matching display layout. Omit it for the full/default layout. |
| `searchable` | `true` | Shows the horizontal search, filter, and sort controls. They remain hidden when omitted. |
| `music` | Directory path | Uses audio files from this directory as the page's background playlist. |
| `random_music` | `true`, `false` | Randomizes background music by default. Set to `false` to follow playlist order. |

Examples:

```text
# 480i library with search and filters
http://localhost:4242/static/ppv/ppv_list.html?channel=43&resolution=480i&searchable=true

# 1080i library with an ordered station-specific music directory
http://localhost:4242/static/ppv/ppv_list.html?channel=43&resolution=1080i&searchable=true&music=runtime/ppv_music/movies&random_music=false

# Default full-resolution library without search controls
http://localhost:4242/static/ppv/ppv_list.html?channel=43
```

## PPV List Features

When `searchable=true` is present, the controls appear in one horizontal row below the channel title:

- Search matches the displayed movie name only.
- Year filter includes every year detected in the current library.
- Movie filter can show all movies, movies with or without posters, or movies with or without local NFO metadata.
- Sort supports title A–Z, title Z–A, newest or oldest release year, and Recently added.
- Recently added sorts by the video file's modification time. Copying or modifying a file can therefore change its position.

The left panel contains the movie list. The right details panel contains the poster, metadata, and description and can be selected and scrolled independently.

## Remote Controls for `ppv_list.html`

Open `/remote`, switch to the navigation pad, and use:

| Remote control | PPV list action |
| --- | --- |
| Left / Right | Move focus through the movie list, search field, filter controls, sort control, and details panel. |
| Page Up / Page Down | Move through movies, change the selected dropdown value, or scroll the details panel, depending on focus. |
| OK | Play the selected movie. On the search field, open the on-screen keyboard. On a dropdown, advance its value. |
| Back | Close the on-screen keyboard. When the keyboard is closed, return focus to the movie list. |
| Keyboard button | Open the phone's native keyboard. Text, numbers, spaces, punctuation, and Backspace are forwarded to the movie-name search. |

Search and dropdown changes apply immediately. The filtered list, counter, selection, poster, and description refresh as soon as a value changes.

The remote sends navigation through `POST /player/web/key/{key_name}`. The older `POST /ppv/{channel}/key/{key_name}` alias remains available.

## Original Poster Slideshow

To use the original poster slideshow, point the station at `ppv.html`:

```json
{
  "station_conf": {
    "network_name": "Movie Posters",
    "channel_number": 42,
    "network_type": "web",
    "hidden": false,
    "content_dir": "catalog/ppv",
    "web_url": "http://localhost:4242/static/ppv/ppv.html?channel=42&duration=10000&variation=modern"
  }
}
```

`ppv.html` accepts:

| Parameter | Description |
| --- | --- |
| `channel` | Required station channel number. |
| `duration` | Slideshow duration in milliseconds; default is `10000`. |
| `variation` | Theme: `modern`, `retro`, or `terminal`. |
| `css` | Custom CSS file. |
| `bg` | Background image. |
| `bg_color` | Background color. |
| `music` | Station-specific background music directory. |
| `random_music` | `true` for random playback or `false` for listed order. |

## Background Music

Each PPV channel can use its own playlist by adding `music=<path>` to `web_url`:

```text
/static/ppv/ppv_list.html?channel=43&searchable=true&music=runtime/ppv_music/movies
```

The directory may contain `.mp3`, `.ogg`, `.wav`, `.flac`, `.aac`, `.m4a`, or `.opus` files.

If `music` is omitted, the page loads the shared playlist from `fs42/fs42_server/static/ppv/music_playlist.json`:

```json
{
  "music_files": [
    "music/track1.mp3",
    "music/track2.mp3"
  ]
}
```

Music plays at 30% volume and stops when a movie starts.

## TMDB Setup (Optional)

Create a TMDB API key and add it to `confs/main_config.json`:

```json
{
  "tmdb_api_key": "your_api_key_here"
}
```

For better matching, include the release year in the video filename, for example `The Matrix (1999).mp4`.

Without TMDB, provide local NFO files and poster images for curated metadata.

## Manual Metadata

An NFO file uses the same base name as its video and contains:

1. Title
2. Information line, such as the release year
3. Description

Example `The Big City.nfo`:

```text
The Big City
1998
In this feature, they talk about the big city and what that means.
```

Poster images also use the video's base name:

```text
The Big City.mp4
The Big City.nfo
The Big City.jpg
```

Supported local poster extensions are `.jpg`, `.jpeg`, and `.png`.

## Metadata Priority

1. Use a local NFO file when present.
2. Use a local poster image when present.
3. Fetch missing metadata from TMDB.
4. Fetch a missing poster from TMDB.

Local and TMDB data can be mixed. TMDB results are cached under `catalog/.tmdb_cache/`.

## API Endpoints

- `GET /ppv/{channel_number}` lists videos and metadata. Each item includes `modified_at`, which powers Recently added sorting.
- `GET /ppv/image/{channel_number}/{filename}` serves local poster images.
- `POST /ppv/{channel_number}/play_file` starts the selected movie.
- `POST /player/web/key/{key_name}` forwards remote navigation, typing, and Back/Escape to the active web channel.

Example play request:

```json
{
  "file_path": "catalog/ppv/The Matrix (1999).mp4"
}
```

## Troubleshooting

**Movies do not appear:** Verify the station's `content_dir`, supported file extensions, and the channel number in both the config and URL. Check the Web UI logs for PPV API errors.

**Search controls do not appear:** Add `searchable=true` to `web_url` and reload the station.

**The remote cannot navigate or type:** Confirm the player command queue is connected, then restart the FieldStation42 player and Web UI so the current web-key routes are loaded.

**Recently added order is unexpected:** It uses each video file's modification timestamp rather than the date encoded in the title.

**TMDB does not match a movie:** Verify `tmdb_api_key`, include the release year in the filename, and check the server logs.

**A local poster does not load:** Confirm that the image and video use the same base filename and a supported image extension.
