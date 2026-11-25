# Media Browser

`static/media_browser/myflix.html` provides a streaming-style interface with a featured title, horizontal movie/show rows, and season/episode browsing. The page reads all library configuration from the station's `station_conf` JSON object.

While the catalog is being scanned, the page renders animated skeleton rails beneath the station-name loading spinner. The placeholders are replaced together when the catalog response arrives and are removed if loading fails.

After the local catalog appears, named skeleton rails represent pending `TMDB_MOVIE_GENRES`. The API derives this list directly from the Python mapping and returns it as `tmdb_movie_genres`, so adding a backend genre requires no JavaScript update. Existing NFO genre rails remain visible, pending genres are inserted before TV Shows, and the placeholders are replaced with only populated genre rails after TMDB enrichment completes.

## Station configuration

Create a web station such as `confs/on_demand.json`:

```json
{
  "station_conf": {
    "network_name": "MyFlix",
    "channel_number": 44,
    "network_type": "web",
    "hidden": false,
    "web_url": "http://localhost:4242/static/media_browser/myflix.html?channel=44&resolution=480i",
    "media_browser": {
      "movies": [
        {
          "title": "Popular Movies",
          "path": "catalog/movies"
        },
        {
          "title": "Comedy Movies",
          "path": "catalog/movies/comedy"
        }
      ],
      "shows": [
        {
          "title": "TV Shows",
          "path": "catalog/shows"
        }
      ]
    }
  }
}
```

Each entry becomes a horizontal content row. A directory string can be used when a custom row title is not needed:

```json
"media_browser": {
  "movies": ["catalog/movies"],
  "shows": ["catalog/shows"]
}
```

The URL's `channel` value must match `channel_number`. The `resolution` parameter supports `480i` and `1080i`; omit it for the default responsive layout.

## Media organization

Movie directories are scanned recursively. Use matching NFO and artwork filenames:

```text
catalog/movies/
├── Example Movie (2026).mkv
├── Example Movie (2026).nfo
└── Example Movie (2026).jpg
```

Each top-level directory in a show library is treated as one series:

```text
catalog/shows/
└── Example Show/
    ├── tvshow.nfo
    ├── poster.jpg
    ├── Season 1/
    │   ├── Example Show S01E01.mkv
    │   ├── Example Show S01E01.nfo
    │   └── Example Show S01E01.jpg
    └── Season 2/
        └── Example Show S02E01.mkv
```

Kodi-style movie, `tvshow.nfo`, and episode NFO files are supported. Season and episode numbers are read from NFO metadata first and then from `S01E02` filenames. Show artwork is selected from `poster`, `folder`, or an image matching the show directory name.

When `tmdb_api_key` is configured in `confs/main_config.json`, movies are matched against TMDB after the local catalog has rendered. Each movie card label updates with the TMDB title and score as its lookup completes, and missing local descriptions, years, or posters fall back to TMDB data. The lookups run in the background so a large movie library does not delay the initial channel load. Local NFO metadata and artwork remain the preferred source for the hero and details views.

Home uses the featured-title layout with horizontal library rows. Selecting Movies or TV Shows hides the featured area and opens that section as a full-screen, vertically scrollable 4 × 2 card grid.

On Home, movie genres found in NFO metadata are expanded into additional alphabetical rails immediately below the configured Movies rail. A movie can appear in multiple genre rails. These generated rails are not duplicated in the full-screen Movies tab.

The Movies grid includes a title search field. Results update as text is entered and match only the local or TMDB movie title. Typing anywhere in the Movies view sends printable characters, Backspace, and Delete to the search field even when a card is selected.

Selecting a movie or an episode opens a full-screen detail view with its available title, show/season/episode information, year or NFO info, content and TMDB ratings, genres, description, and artwork. Playback begins only after selecting the Play button.

Episode details also show the other episodes from the selected season in a right-side list. The current episode is highlighted; use Up/Down or click an episode to change the displayed metadata, then select Play.

Movie cards use a same-name local poster first. When local artwork or metadata is missing and `tmdb_api_key` is configured in `confs/main_config.json`, the media browser uses the TMDB movie title, release year, description, and poster. TMDB responses are cached under `catalog/.tmdb_cache/`.

## Remote controls

| Remote control | Action |
| --- | --- |
| Left / Right | Move between titles. In Library sections, choose Home, Movies, or TV Shows. In show details, change seasons. |
| Page Up / Page Down | Move between rows. From the first row, Page Up selects Library sections. In show details, move between episodes. |
| OK | Apply the selected Library section, open movie details, open a show, open episode details, or activate Play in a detail view. |
| Back | Return from item details to the episode browser or library, close show details, or return from a Movies or TV Shows grid to Home. |

## Resolve ambiguous TVmaze matches

Use this when **Normalize Naming** reports `Multiple TVmaze shows match … Set the
TVmaze uniqueid in tvshow.nfo.` The error lists candidate shows with their
premiere dates and IDs. This can happen even when the premiere year is already
in the folder name or metadata.

1. Search [TVmaze](https://www.tvmaze.com/) for your series and open its **show
   page**. Check the premiere date and network against your files. You can also
   use the candidate IDs listed in the error to open the corresponding shows.
2. Copy the number immediately after `/shows/` in the show page URL. For
   example, `https://www.tvmaze.com/shows/45563/dave` gives the ID `45563`.
3. Open or create `tvshow.nfo` in the **show folder**, alongside the season
   folders. For example, use `TV Shows/Your Show/tvshow.nfo` if the episodes are
   under `TV Shows/Your Show/Season 1/`.
4. Add a `uniqueid` element inside `<tvshow>`. The attribute `type="tvmaze"`
   identifies the provider and the element text is the numeric show ID. Keep
   existing IDs for other providers.

```xml
<tvshow>
  <title>Your Show</title>
  <uniqueid type="tvmaze">YOUR_SHOW_ID</uniqueid>
</tvshow>
```

Replace `YOUR_SHOW_ID` with the number you copied. The exact ID takes precedence
over title and year searches in both Normalize Naming and MyFlix. Rerun
Normalize Naming to review the preview, or reload MyFlix to refresh its catalog.

If the error is `No episode for … in the selected order`, see
[Episode order](#episode-order) below.

## Episode order

Normalize Naming and MyFlix use TVmaze's aired order by default. If a library
uses a different order, choose the order for that show in `confs/main_config.json`.
Entries are keyed by the show's TVmaze ID. The lookup uses the chosen order;
the library's season and episode codes stay in the filenames and on screen.

- Use `{"tvmaze_list_id": 123}` with the ID of an alternate list returned by
  TVmaze's `/shows/{show_id}/alternatelists` endpoint.
- Use `{"tvdb_order": "alternate"}` for TheTVDB's alternate order when the
  show has a linked TheTVDB record. Add `tvdb_api_key` and, if required by the
  key, `tvdb_pin` to the same config. Episode titles are resolved in that order;
  MyFlix cross-references TVmaze by title and air date for still images.

For example, for the American Dad! Streaming Order, merge the following into
the existing config and restart the Web UI service.

```json
{
  "tvdb_api_key": "YOUR_TVDB_V4_API_KEY",
  "episode_orders": {
    "215": { "tvdb_order": "alternate" }
  }
}
```

## API

Episode summaries and still images are provided by [TVmaze](https://www.tvmaze.com/).

- `GET /media-browser/{channel_number}` builds the configured rows and show hierarchy.
- `GET /media-browser/{channel_number}/art/{library_id}/{path}` serves nested artwork from a configured library.
- `POST /ppv/{channel_number}/play_file` starts the selected movie or episode.

After adding or changing a station configuration, restart the player and Web UI services:

```bash
systemctl --user restart fs42.service
```
