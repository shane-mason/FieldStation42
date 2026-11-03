# Streaming a Catalog from URLs (`.strm` stubs)

A `.strm` stub is a small text file that stands in for a video file in your
catalog. Instead of reading the video from disk, FieldStation42 streams it from
the URL inside the stub. This lets a channel use a long list of shows without
downloading them first. The [Internet Archive](https://archive.org) is the
typical source, but any URL that mpv can play works.

Stubs behave like ordinary video files everywhere else: put them in a tag
folder, scan them into the catalog, and schedule them with the usual slots,
bumps, sequences and `random_tags`.

> Stubs are different from the `streaming` network type. A `streaming` network
> plays a live feed (HLS and similar) in place of a schedule. A stub is a
> recorded episode or movie that sits inside a normal catalog and schedule.

## Stub format

```
https://archive.org/download/some-item/episode-01.mp4
#duration=1425
#start=0
#crop=640:480:40:0
#aid=1
```

The first non-comment line is the target. Everything after `#` is an option.
See [`docs/examples/example.strm`](examples/example.strm).

| Line | Required | Description |
|------|----------|-------------|
| URL or path | yes | What to play: an `http(s)` URL, or a path to a local file |
| `#duration=N` | yes, for the catalog scan | Length in seconds, **after** any `#start` trim. The scan reads this instead of probing the URL, which would need a download per file |
| `#start=N` | no | Skip the first N seconds (intros, leader, bars and tone) |
| `#crop=w:h:x:y` | no | Crop the picture, for files with black side bars. Same numbers as ffmpeg's `cropdetect` prints |
| `#aid=N` | no | Audio track to use when the file has more than one |

Unknown lines are ignored, and a bad value (for example `#duration=abc`) is
skipped as if the line were not there.

Stub files are read as UTF-8. Both Unix and Windows line endings work.

## Setting up a channel

1. Make a tag folder in the station's `content_dir` as usual, for example
   `catalog/my_station/cartoons/`.
2. Put one `.strm` file per episode in it. Use the file name as the title,
   just as you would for a video.
3. Rebuild the catalog:

   ```
   python3 station_42.py -r --skip_chapter_scan
   ```

   Stubs without a `#duration` are skipped with a warning in the log.
4. Schedule the tag like any other.

`.nfo` files next to a stub work as they do next to a video (see
`fs42/nfo_agent.py`).

## Finding the values

* **Duration:** for an archive.org item, the item's metadata page
  (`https://archive.org/metadata/<item>`) lists a `length` in seconds for each
  video file.
* **Crop:** run ffmpeg against the URL for a few seconds:

  ```
  ffmpeg -ss 120 -i "<url>" -t 5 -vf cropdetect -f null - 2>&1 | grep crop=
  ```

  Use the `crop=w:h:x:y` it settles on. Leave `#crop` out if the picture has
  no bars.
* **Audio track:** `ffprobe -show_streams "<url>"` lists the tracks.

## Volume leveling

Streamed files come from many uploaders and vary a lot in loudness, so the
volume can jump between episodes (and against local files and commercials).
Turn on live leveling for a station with `stream_loudnorm` in its config:

```json
{
  "station_conf": {
    "network_name": "Cartoons",
    "stream_loudnorm": true
  }
}
```

Leveling is **off by default** and only applies to `.strm` stubs and streaming
entries; local files are played untouched. It adds ffmpeg's `loudnorm` audio
filter to mpv while the stream plays and removes it afterwards. It does not
change any files and does not touch other audio filters (such as
`audio_scramble_fx`).

`true` uses a target of -18 LUFS, loudness range 7 and true peak -1.5 dBTP. To
change them, give an object; any value you leave out keeps its default:

```json
"stream_loudnorm": { "i": -16, "lra": 11, "tp": -1.5 }
```

| Key | Meaning | Allowed range |
|-----|---------|---------------|
| `i` | Integrated loudness target (LUFS) | -70 to -5 |
| `lra` | Loudness range target | 1 to 50 |
| `tp` | True peak ceiling (dBTP) | -9 to 0 |

An invalid value is ignored (a warning is logged) and the stream plays without
leveling.

`loudnorm` works on a rolling window of the live audio, so the first couple of
seconds of an episode can still be slightly off, and it uses some CPU. On a
Raspberry Pi 4 it adds a small amount of load for stereo audio; if you see
dropped frames, turn it off.

## When a stream will not play

Streams depend on a server you do not control. If a stub's URL does not start
within `video_seek_timeout` seconds (the same server setting local files use,
default 10), or the stream stops part-way through, FieldStation42 does not skip
the entry or stop the channel. It shows an on-screen message for the rest of
that entry's time, then moves on to the next entry on schedule, so the rest of
the day is unaffected.

* The message defaults to `TECHNICAL DIFFICULTIES`. Change it per station with
  `stream_down_message` in the station config.
* The remote stays responsive while a stream is loading, so you can change
  channels without waiting for the timeout.
* The same fallback is used for entries on `streaming` networks.

## Notes and limits

* Seeking into a stream (joining a show part-way through its slot) needs the
  server to support HTTP range requests. archive.org does.
* The catalog stores the stub's path, so editing a stub (a new `#crop` or
  `#start`) takes effect the next time it plays, without a rebuild. Changing
  `#duration` needs a catalog rebuild.

## Testing

```
python3 -m pytest test/test_stream_stub.py test/test_stream_fallback.py test/test_audio_level.py
```

To try a stub by hand, copy `docs/examples/example.strm` into a tag folder,
point it at a real file, rebuild the catalog, and tune to the channel.

To see the fallback, point a stub at a URL that does not exist (for example
`https://example.invalid/ep.mp4`) and tune to the channel: the message appears
after the timeout and the channel carries on at the next entry.
