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

## Notes and limits

* Seeking into a stream (joining a show part-way through its slot) needs the
  server to support HTTP range requests. archive.org does.
* The catalog stores the stub's path, so editing a stub (a new `#crop` or
  `#start`) takes effect the next time it plays, without a rebuild. Changing
  `#duration` needs a catalog rebuild.

## Testing

```
python3 -m pytest test/test_stream_stub.py
```

To try a stub by hand, copy `docs/examples/example.strm` into a tag folder,
point it at a real file, rebuild the catalog, and tune to the channel.
