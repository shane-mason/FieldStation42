import os
from fastapi import APIRouter

from fs42.station_manager import StationManager

router = APIRouter(prefix="/about")


def _is_servable(theme_dir, file):

    full_path = os.path.join(theme_dir, file)
    if not os.path.isfile(full_path):
        # broken symlink or a directory
        return False

    if StationManager().server_conf.get("follow_static_symlinks", False):
        return True

    # symlinks pointing outside of the static dir are rejected by the static mount
    static_dir = os.path.realpath("fs42/fs42_server/static")
    return os.path.commonpath([os.path.realpath(full_path), static_dir]) == static_dir


@router.get("/themes")
async def get_themes():
    """Get list of available themes"""
    theme_dir = "fs42/fs42_server/static/themes"
    themes = []
    try:
        for file in os.listdir(theme_dir):
            if file.endswith(".css") and _is_servable(theme_dir, file):
                name = file.replace(".css", "")
                # Create a user-friendly name from the filename
                display_name = name.replace("_", " ").replace("default", "").strip()
                if not display_name:
                    display_name = "Default"
                themes.append({"id": name, "name": display_name.title(), "path": f"/static/themes/{file}"})
        return {"themes": sorted(themes, key=lambda x: x["name"])}
    except Exception as e:
        return {"themes": [{"id": "default", "name": "Default", "path": "/static/themes/default.css"}], "error": str(e)}
