"""Launch the local Career Memory web app from a Windows executable."""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from dotenv import load_dotenv


def configure_runtime() -> Path:
    frozen = bool(getattr(sys, "frozen", False))
    executable_dir = Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parent
    load_dotenv(executable_dir / ".env", override=False)

    if frozen:
        local_app_data = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        data_root = Path(os.environ.setdefault("CAREER_MEMORY_DATA_ROOT", str(local_app_data / "CareerMemory")))
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url or database_url == "sqlite:///./data/career_memory.db":
            database_path = data_root / "data" / "career_memory.db"
            database_path.parent.mkdir(parents=True, exist_ok=True)
            os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

    # A local HTTP app needs a non-secure session cookie.
    os.environ["APP_ENV"] = "development"
    return Path(getattr(sys, "_MEIPASS", executable_dir)) / ("web" if frozen else "dist")


def choose_port(preferred: int) -> int:
    for candidate in (preferred, 0):
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", candidate))
                return listener.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No available local port")


def open_browser_when_ready(port: int) -> None:
    def worker() -> None:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    webbrowser.open(f"http://127.0.0.1:{port}/")
                    return
            except OSError:
                time.sleep(0.1)

    threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Career Memory local server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    web_root = configure_runtime()
    if not (web_root / "index.html").is_file():
        raise RuntimeError(f"Frontend build not found: {web_root}")

    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn

    from AI_Engine.router import app

    app.mount("/assets", StaticFiles(directory=web_root / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(web_root / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_route(path: str) -> FileResponse:
        if path.startswith("api/") or "." in path:
            raise HTTPException(status_code=404)
        return FileResponse(web_root / "index.html")

    port = choose_port(args.port)
    print(f"Career Memory: http://127.0.0.1:{port}/", flush=True)
    if not args.no_browser:
        open_browser_when_ready(port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()