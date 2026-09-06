from __future__ import annotations

import _thread
import os
import runpy
import site
import sys
import threading
import time
from pathlib import Path


product_root = Path(__file__).resolve().parents[2]
site_packages = product_root / ".venv" / "Lib" / "site-packages"
application = product_root / "web_app.py"
stdout_log = Path(os.environ.pop("AOM_LAUNCHER_STDOUT_LOG"))
stderr_log = Path(os.environ.pop("AOM_LAUNCHER_STDERR_LOG"))
stop_file = Path(os.environ.pop("AOM_LAUNCHER_STOP_FILE"))
stop_token = os.environ.pop("AOM_LAUNCHER_STOP_TOKEN")

if not site_packages.is_dir():
    raise SystemExit(f"Missing private site-packages directory: {site_packages}")
if not application.is_file():
    raise SystemExit(f"Missing application entry point: {application}")

sys.stdout = stdout_log.open("a", encoding="utf-8", buffering=1)
sys.stderr = stderr_log.open("a", encoding="utf-8", buffering=1)


def watch_for_stop() -> None:
    while True:
        try:
            if stop_file.is_file() and stop_file.read_text(encoding="ascii").strip() == stop_token:
                _thread.interrupt_main()
                return
        except OSError:
            pass
        time.sleep(0.2)


threading.Thread(target=watch_for_stop, name="portable-stop-watcher", daemon=True).start()
site.addsitedir(str(site_packages))
sys.path.insert(0, str(product_root))
sys.argv = [str(application), *sys.argv[1:]]
runpy.run_path(str(application), run_name="__main__")
