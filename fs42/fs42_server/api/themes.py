import os
from fastapi import APIRouter

router = APIRouter(prefix="/about")

@router.get("/themes")
async def get_themes():
    """Get list of available themes"""
    theme_dir = "fs42/fs42_server/static/themes"
    themes = []
    try:
        for file in os.listdir(theme_dir):
            if file.endswith(".css"):
                name = file.replace(".css", "")
                # Create a user-friendly name from the filename
                display_name = name.replace("_", " ").replace("default", "").strip()
                if not display_name:
                    display_name = "Default"
                themes.append({"id": name, "name": display_name.title(), "path": f"/static/themes/{file}"})
        return {"themes": sorted(themes, key=lambda x: x["name"])}
    except Exception as e:
        return {"themes": [{"id": "default", "name": "Default", "path": "/static/themes/default.css"}], "error": str(e)}
