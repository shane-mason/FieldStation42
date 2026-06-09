# Running FieldStation42 on older CPUs (x86-64-v1)

If FieldStation42 dies immediately with **`Illegal instruction (core dumped)`** and
**no Python traceback**, your machine is almost certainly an older 64-bit CPU that
predates the **x86-64-v2** instruction set. This is common on the cheap, low-power
thin clients and mini-PCs people like to use as a dedicated cable box.

## Symptom

```
$ env/bin/python3 field_player.py
Illegal instruction (core dumped)
```

No log, no error code, no traceback — the process is killed by the kernel (SIGILL)
because a native library tried to execute a CPU instruction your processor doesn't
implement. A Python `try/except` cannot catch this; it's a hardware trap.

## Cause

Modern Python wheels (NumPy, PySide6/Qt6, and many others) are now compiled for the
**x86-64-v2** microarchitecture level, which requires **SSE4.1 / SSE4.2**. Older
64-bit CPUs are only **x86-64-v1** and lack those instructions, for example:

* AMD **Bobcat** / **Jaguar** families (G-T48E, E-350, GX-/A-series APUs, …)
* Intel **Core 2**, first-gen **Atom** (Bonnell/Saltwell), early **Nano**, etc.

The first instruction to blow up is usually `pinsrq` (an SSE4.1 op). Note that AMD's
`sse4a` flag is **not** the same as SSE4.1 — it does not include `pinsrq`.

## Confirm it's your CPU

```bash
# If 'sse4_1' is MISSING from the flags, prebuilt v2 wheels will SIGILL:
lscpu | grep -o -E 'sse4_1|sse4_2|avx2?|ssse3|sse4a' | sort -u
```

You can pinpoint the faulting instruction with gdb:

```bash
gdb -batch -ex run -ex 'x/i $pc' --args env/bin/python3 -c 'import numpy'
# => ... SIGILL ... pinsrq ...   (an SSE4.1 instruction)
```

Qt6 reports it explicitly — loading the Qt libraries prints:

```
Incompatible processor. This Qt build requires the following features:
    sse4.1 sse4.2
```

## The fix: rebuild the native packages for an x86-64-v1 baseline

The affected packages in a default FieldStation42 install are **numpy** and
**PySide6** (which bundles **Qt6** and **shiboken6**). Rebuilding them with a v1 CPU
baseline (gcc `-march=x86-64` for any v1 chip, or `-march=btver1` for AMD
Bobcat/Jaguar specifically) makes them run. Qt's higher SIMD paths stay
runtime-dispatched, so nothing breaks on capable CPUs.

You have two options:

### Option A — install prebuilt wheels (fastest)

Prebuilt x86-64-v1 wheels (Qt 6.11.1 / PySide6 / shiboken6 + a from-source numpy),
built for **Python 3.12 / glibc 2.34+ (Ubuntu 24.04)**:

> **https://github.com/ScriptBlock/fs42-bobcat-deps** (see Releases)

```bash
# from your FieldStation42 dir, into its venv:
env/bin/pip uninstall -y PySide6 PySide6_Essentials PySide6_Addons shiboken6 numpy
env/bin/pip install --no-deps numpy-*.whl shiboken6-*.whl pyside6-*.whl
```

Plus the runtime system libraries and the classic-guide dependency:

```bash
sudo apt-get install -y python3-tk \
  libb2-1 libmd4c0 libicu74 libglib2.0-0 libzstd1 \
  libegl1 libglx0 libopengl0 libgl1 libx11-6 libx11-xcb1 \
  libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libfreetype6 fonts-dejavu-core \
  libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
  libxcb-randr0 libxcb-render0 libxcb-render-util0 libxcb-shape0 libxcb-shm0 \
  libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 libxcb-util1 libsm6 libice6
```

### Option B — build them yourself

The build recipe (a Docker-based, reproducible build that compiles Qt 6.11.1 qtbase
+ PySide6 + numpy with the v1 baseline) is documented here:

> **https://github.com/ScriptBlock/fs42-bobcat-deps**

A full Qt build is heavy, so prebuilt wheels (Option A) are recommended unless you
need a different Python/glibc version.

## What works and what doesn't

| Feature | Renderer | On x86-64-v1 |
| --- | --- | --- |
| Video channels (`standard`, `loop`, `streaming`) | mpv → HDMI | ✅ works |
| Classic channel guide (`guide`) | tkinter | ✅ works (needs `python3-tk`) |
| Ticker / now-playing / NFO overlays | Qt Widgets | ✅ works |
| `web` channels (a web page as a channel) | QtWebEngine (Chromium) | ❌ not built |

`QtWebEngine` (Chromium) is intentionally **not** included — it's an enormous build
and only the optional `web` channel type uses it. FieldStation42 already degrades
gracefully when it's absent (`WEB_RENDER_AVAILABLE = False`), so the player and all
other channel types are unaffected.

## Notes / caveats

* The prebuilt **numpy** is built with its SIMD dispatcher disabled
  (`-Ddisable-optimization=true`); numpy 2.4.x floors its `cpu-baseline` at x86-64-v2,
  and the chip has no AVX to dispatch to anyway, so nothing is lost on this hardware.
* `btver1` wheels enable AMD-only `sse4a`; for a non-AMD v1 CPU, use the
  `-march=x86-64` ("generic v1") wheels instead.
* Wheels are Python-version and glibc-specific (cp312, glibc 2.34+). For a different
  environment, build from source (Option B).
