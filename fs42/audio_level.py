"""Live volume leveling for streamed video, using ffmpeg's ``loudnorm`` filter."""

LEVEL_LABEL = "fs42level"

# EBU R128 style targets, a little quieter than broadcast so streams sit with typical local files
DEFAULTS = {"i": -18.0, "lra": 7.0, "tp": -1.5}


def loudnorm_af(setting):
    """Build the mpv ``af`` argument for a ``stream_loudnorm`` station setting.

    ``setting`` is ``True`` for the defaults, or a dict that overrides any of
    ``i`` (integrated loudness, LUFS), ``lra`` (loudness range) and ``tp``
    (true peak, dBTP). Returns None when leveling is off or the setting is
    invalid.
    """
    if setting is True:
        values = dict(DEFAULTS)
    elif isinstance(setting, dict):
        values = dict(DEFAULTS)
        for key in DEFAULTS:
            if key in setting:
                value = setting[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return None
                values[key] = float(value)
    else:
        return None
    # loudnorm's own limits; mpv would reject the filter otherwise
    if not (-70.0 <= values["i"] <= -5.0 and 1.0 <= values["lra"] <= 50.0 and -9.0 <= values["tp"] <= 0.0):
        return None
    # loudnorm outputs 192 kHz internally, so resample back to something the audio device takes
    return (
        f"@{LEVEL_LABEL}:lavfi=[loudnorm=I={values['i']:g}:LRA={values['lra']:g}:TP={values['tp']:g},aresample=48000]"
    )
