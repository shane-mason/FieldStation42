# Home TV Server Architecture

## Status and goals

This document records the architecture of the headless Home TV mode. The
existing `field_player.py`/MPV player remains supported as a legacy local
playback mode. Home TV adds a second consumer of the same station
configuration, catalog, and liquid schedule: a FastAPI service that resolves
the program airing at wall-clock time and exposes it as browser-compatible
HLS.

The first release targets a trusted home LAN and a small number of clients. It
does not expose arbitrary media paths, does not require a display or audio
device on the server, and keeps generated stream data in a bounded runtime
directory.

## Existing data model and broadcast calculation

`StationManager` loads `confs/main_config.json` and station JSON files. All
catalog entries and liquid schedule blocks are stored in the SQLite database
selected by `db_path` (normally `runtime/fs42_fluid.db`).

A `liquid_blocks` row contains a scheduled `start_time`, `end_time`, title, and
an ordered `plan_json`. Each plan item contains:

- `path`: the server-side media path
- `skip`: the media start point selected by the scheduler
- `duration`: the scheduled duration of this item
- `is_stream`, `content_type`, and `media_type`

Guide display names are derived from NFO metadata when explicitly requested
and otherwise from series/movie library paths. Container title tags are not
treated as authoritative program identity. Conventional nested supplemental
directories (`Extras`, `Featurettes`, `Trailers`, `Deleted Scenes`, and
`Deleted and Extended Scenes`, and similar) are excluded from recursive
feature scans; rebuilding the catalog and regenerating the schedule is
required to remove previously scheduled extras. Both the guide and `/watch`
consume the same canonical identity fields. Episode presentation is separated
into the series name and `Season N, Episode N: Episode Title`.

Commercial placement uses a deliberately conservative feature-only analysis.
A candidate internal break must be either an explicitly named act/break
chapter, or a sustained fade-to-black aligned within five seconds of an
embedded chapter boundary. Candidates within two minutes of either edge are
discarded, credits/ending chapters are rejected, and accepted breaks must be
at least three minutes apart. If no trustworthy boundary remains, the feature
is not cut and its filler is placed after it. Commercial and bump content is
never analyzed for black frames, trimmed, or shortened.

For a request at time `now`, Home TV selects the row satisfying
`start_time <= now < end_time`. It then walks the ordered plan from the block
start until it finds the item containing `now`.

```text
elapsed in block = now - block.start_time
selected item    = first item whose cumulative duration exceeds elapsed
playback offset  = selected item.skip + elapsed - preceding item durations
```

The half-open end boundary avoids selecting two programs at the exact handoff.
The API returns both the block and plan-item times. If no row covers `now`, the
channel is unavailable until its schedule is extended.

## Components

```text
read-only media ─┐
station configs ─┼─> schedule resolver ─> HLS session manager ─> FFmpeg
SQLite schedule ─┘          │                       │              │
                            └─> watch API            └─> runtime/hls/<id>
                                      │                            │
                                      └──────── /watch browser <───┘
```

- **Schedule resolver** performs read-only, parameterized SQLite queries and
  converts a schedule block into a current media path and exact offset.
- **HLS session manager** owns FFmpeg subprocesses, validates every selected
  media path against configured catalog entries, creates per-session
  directories, tracks activity, and expires idle sessions.
- **Watch API** exposes channel metadata, current-program information, session
  creation/deletion, and only the HLS files belonging to opaque session IDs.
- **Watch client** is a responsive HTML application. Browsers with native HLS
  use it directly; other modern browsers use the bundled HLS.js client.
- **Legacy player** continues to run through `field_player.py`; no web session
  controls or depends on its MPV instance.

## HTTP API

All routes are same-origin under the existing FastAPI server.

- `GET /watch` returns the viewer application.
- `GET /api/watch/channels` lists visible scheduled channels. It never returns
  filesystem paths.
- `GET /api/watch/channels/{channel}/now` returns channel number/name, program
  and item titles, scheduled start/end, duration, current offset, progress, and
  a server timestamp.
- `POST /api/watch/sessions` accepts `{channel, profile}`. It resolves the
  current item, starts FFmpeg at the broadcast offset, and returns an opaque
  session ID and playlist URL.
- `GET /api/watch/sessions/{id}/master.m3u8` and
  `GET /api/watch/sessions/{id}/{asset}` serve only generated HLS artifacts.
- `POST /api/watch/sessions/{id}/heartbeat` refreshes activity.
- `DELETE /api/watch/sessions/{id}` stops FFmpeg and removes its output.
- `GET /health` reports process health without touching MPV, X11, or audio.

Invalid channels, profiles, session identifiers, expired schedules, missing
media, and non-catalog paths produce explicit 4xx/5xx responses. API responses
do not reveal media paths.

## HLS and FFmpeg strategy

The MVP creates one FFmpeg process per watch session. This is intentionally
simple and allows different channels and client profiles independently. A
future optimization may share a channel/profile pipeline while retaining the
same API.

FFmpeg seeks to the calculated offset and writes a short, rolling HLS playlist
with independent MPEG-TS segments. The initial profiles are:

- `auto`: transcode to H.264/AAC for broad browser and Raspberry Pi support.
- `copy`: stream-copy both tracks for already compatible H.264/AAC sources.

The conservative default avoids relying on filename extensions: MKV, MP4,
HEVC, AV1, AC3, EAC3, and other FFmpeg-readable inputs become H.264/AAC. The
explicit copy profile is useful on known-compatible libraries. A later version
can use `ffprobe` plus client capabilities to choose copy/remux per stream.

For the automatic profile, FFprobe also inspects stream-language tags. When
the primary audio is explicitly tagged as non-English and an English subtitle
stream exists, FFmpeg burns that subtitle into the HLS video by default. Audio
with an absent or `und` language tag is not guessed. The explicit `copy`
profile remains unchanged because burning subtitles requires video encoding.

The rolling playlist retains 12 two-second segments (at least 24 seconds).
The client starts as soon as HLS reports a playable manifest and leaves
ordinary buffering to HLS.js and the browser. There is deliberately no
client-side startup-buffer gate or pause/resume controller.
At scheduled item boundaries the client displays every frame through the
scheduled end, then fades/holds black while replacing the item without showing
a tuning message, and fades back on the video element's `playing` event. The
fade does not begin early, trim an ad or bumper, pause an active stream, or
create additional buffering policy.

The FFmpeg command is constructed as an argument vector, never a shell string.
No endpoint accepts a command or path. Input paths come only from the current
schedule and must resolve to a catalog-approved file.

## Synchronization and channel changes

The server is authoritative for time. Creating or changing a session resolves
the schedule at that instant and seeks into the selected media item.
Consequently, viewers joining the same channel see approximately the same
point; their difference is bounded by startup and segment latency. The web
client periodically fetches `now`, displays progress using the returned server
timestamp, and recreates a session after a program boundary or playback error.

A channel change deletes the previous session before creating the next.
Volume, mute, and fullscreen are browser-local and never alter another viewer
or the legacy MPV player.

## Session lifecycle and cleanup

Each session has an opaque UUID, channel/profile metadata, process handle,
creation time, last-access time, and a directory below the configured HLS
runtime root (`runtime/hls` by default).

Creation uses a private temporary directory that is renamed only after setup.
Playlist and segment requests refresh `last_access`. Heartbeats cover paused
or temporarily buffered clients. A lifespan cleanup task expires idle
sessions, terminates and then kills unresponsive FFmpeg processes, and removes
only the resolved session directory. Startup removes stale session directories
left by an unclean shutdown. Shutdown stops every owned process. Configurable
limits cap idle time and concurrent sessions.

## Database concurrency

SQLite connections share one configuration:

- a nonzero `timeout` and `PRAGMA busy_timeout`
- WAL journal mode for readers concurrent with one writer
- `PRAGMA synchronous=NORMAL`
- short transactions with rollback on exceptions

Catalog and schedule mutations additionally use a process-wide operation
coordinator. Only one catalog/schedule job may run at once, regardless of which
web endpoint started it. Task state is changed in `finally` paths so failures
cannot leave the console stuck on “running”. Double-clicks receive `409
Conflict`, and task records include progress plus traceback-backed error logs.

A catalog rebuild is destructive to its associated schedule because plan rows
refer to catalog IDs. The API therefore requires an explicit
`reset_schedule=true` acknowledgement, or a combined rebuild-and-generate
operation. The console presents that warning before submission. The rebuild
scanner replaces legacy generic chapter rows with conservative commercial
boundaries. Scanning can be disabled per rebuild; doing so also disables
internal commercial placement, leaving filler after uninterrupted features.

Database locks coordinate threads in one server process. Production Compose
runs a single application worker; multiple independent writers against the
same database are unsupported.

## Security boundaries

Home TV is designed for a trusted LAN, not direct Internet exposure.

- Media mounts are read-only.
- Browsers receive channel/program metadata and generated HLS only.
- Schedule paths are checked against catalog records and canonicalized.
- HLS asset names are restricted to a small allowlist pattern and resolved
  beneath the opaque session directory.
- No API serves user-supplied filesystem paths or invokes user-supplied shell
  commands.
- Configuration, database, logs, and HLS cache have separate writable mounts.
- Deployments needing Internet access should add authentication and TLS at a
  reverse proxy.

The pre-existing `/media` management routes are outside the watch API. They
must not be used for scheduled playback and should be restricted or disabled
before exposing the management console beyond a trusted LAN.

## Docker and Unraid deployment

The production image installs FFmpeg and Python dependencies but not MPV, X11,
PulseAudio, Tk, or OpenGL desktop packages. It runs `station_42.py --server`
with `start_mpv=false`. Compose mounts:

- `/media` read-only
- `/app/confs` for configuration
- `/app/catalog` for generated auxiliary catalog data
- `/app/runtime` for SQLite and HLS cache
- `/app/logs` for logs

The listen host and port are set with environment variables, with the container
health check calling `/health`. Time zone data is mounted read-only. An Unraid
template/example `.env` documents host paths and port mapping.

## Raspberry Pi viewer

The Pi contains no FieldStation42 data. Chromium starts from the graphical
desktop in kiosk mode at `http://UNRAID-IP:PORT/watch`, with session restore
prompts and screen blanking disabled. A small launcher retries Chromium after
unexpected exit. The page itself retries API and HLS playback after network
loss. Keyboard arrows change channel; `M` toggles mute; `F` toggles fullscreen;
volume keys remain usable.

## Testing strategy

Unit tests create temporary configurations, SQLite databases, HLS roots, and
generated FFmpeg color/tone media. They never use a live runtime.

- Resolver tests cover block boundaries, plan-item offsets, and absent
  schedules.
- API tests cover channels, validation, session/channel changes, and error
  responses.
- Session tests substitute a controllable FFmpeg process where possible and
  include one generated-media integration test when FFmpeg is installed.
- Security tests attempt traversal through session IDs/assets and verify that
  non-catalog schedule paths are rejected.
- Concurrency tests start overlapping database jobs and force worker failures,
  checking lock conflicts and terminal task states.
- Docker tests inspect the image/Compose configuration and run the headless
  health endpoint without X11 or PulseAudio mounts.
- Existing tests run after each major layer to preserve local-player
  compatibility.

## Deferred work

The MVP does not promise frame-perfect synchronization, DRM, WAN security,
adaptive multi-bitrate ladders, hardware acceleration, or shared FFmpeg
pipelines. These can be added without changing the schedule resolver or public
session lifecycle.
