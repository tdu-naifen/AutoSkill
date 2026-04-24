"""FastAPI app factory with WebSocket support."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import router

# Global list of connected WebSocket clients
ws_clients: list = []

# Global output directory — set by create_app
output_dir: str = "output/skills"


async def broadcast(data: dict):
    """Broadcast event to all connected WebSocket clients."""
    message = json.dumps(data, default=str)
    disconnected = []
    for ws in ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        ws_clients.remove(ws)


def create_app(output: str = "output/skills") -> FastAPI:
    global output_dir
    output_dir = output
    app = FastAPI(title="AutoSkill")
    app.include_router(router)
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app
