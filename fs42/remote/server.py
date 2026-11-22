from fs42.remote.commands import read_status, write_command

from pydantic import BaseModel, validator
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from fastapi.responses import FileResponse

app = FastAPI()

app.mount("/static", StaticFiles(directory="fs42/remote/static", html="true"), name="static")

# Define allowed commands
ALLOWED_COMMANDS = {"up", "down", "direct"}
class CommandPayload(BaseModel):
    command: str
    channel: int

    @validator("command")
    def validate_command(cls, v):
        if v not in ALLOWED_COMMANDS:
            raise ValueError(f"Invalid command: {v}")
        return v

@app.post("/api/command")
async def handle_command(payload: CommandPayload):
    try:
        status = write_command(payload.dict())

        return {
            "status": "ok",
            "current": status
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status")
def get_status():
    return read_status()

@app.get("/")
def remote():
    return FileResponse("fs42/remote/static/index.html")