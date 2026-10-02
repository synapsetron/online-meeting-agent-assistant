from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api import health, websocket
from server.config import Config
from server.services.session_manager import SessionManager

app = FastAPI(title="Meeting Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(websocket.router)

config = Config.from_env()
session_manager = SessionManager()
websocket.configure(session_manager, config)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host=config.host, port=config.port, reload=True)
