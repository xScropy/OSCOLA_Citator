"""CiteRight desktop launcher.

Runs the API and the web interface as one local program and opens it in the
browser. This is the entry point of the packaged Windows executable; it also
works from source after `STATIC_EXPORT=1 npm run build` in ../frontend.

Your library is stored on this computer only:
  Windows: %APPDATA%\\CiteRight        elsewhere: ~/.citeright
"""
from __future__ import annotations

import os
import secrets
import socket
import sys
import threading
import webbrowser
from pathlib import Path

DEFAULT_PORT = 8765


def data_dir() -> Path:
    base = Path(os.environ["APPDATA"]) if os.name == "nt" and os.environ.get("APPDATA") else Path.home()
    folder = base / ("CiteRight" if os.name == "nt" else ".citeright")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def secret_key(folder: Path) -> str:
    """A signing key kept between runs, so you stay signed in after a restart."""
    file = folder / "secret.key"
    if not file.exists():
        file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return file.read_text(encoding="utf-8").strip()


def static_dir() -> Path:
    if getattr(sys, "frozen", False):  # unpacked next to the bundled code by PyInstaller
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "frontend"
    return Path(__file__).resolve().parent.parent / "frontend" / "out"


def free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return probe.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No free network port is available.")


def main() -> None:
    folder = data_dir()
    interface = static_dir()
    if not (interface / "index.html").is_file():
        sys.exit(f"The web interface was not found at {interface}. Build it with: STATIC_EXPORT=1 npm run build")

    os.environ.setdefault("DATABASE_URL", f"sqlite:///{(folder / 'citeright.db').as_posix()}")
    os.environ.setdefault("SECRET_KEY", secret_key(folder))
    os.environ["CITERIGHT_STATIC_DIR"] = str(interface)

    import uvicorn

    from app.main import app  # imported after the environment is configured

    port = free_port(int(os.environ.get("CITERIGHT_PORT", DEFAULT_PORT)))
    url = f"http://127.0.0.1:{port}"
    print("CiteRight is running.", flush=True)
    print(f"  Open:     {url}", flush=True)
    print(f"  Library:  {folder}", flush=True)
    print("  To quit:  close this window (or press Ctrl+C).", flush=True)
    if not os.environ.get("CITERIGHT_NO_BROWSER"):
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
