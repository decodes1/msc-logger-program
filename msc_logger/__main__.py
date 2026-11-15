"""Desktop launcher, instance locking, startup diagnostics, and clean shutdown."""

import argparse
import json
import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

from .desktop import start_window
from .engine import Engine
from .server import LocalServer
from .storage import Store


def data_directory():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MSC Logger"
    return Path.home() / ".msc-logger"


class InstanceLock:
    def __init__(self, path):
        self.file = open(path, "a+b")
        self.file.seek(0)
        if not self.file.read(1):
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("MSC Logger is already running for this workspace.") from None

    def close(self):
        self.file.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="MSC Logger local crew-maintenance simulator")
    parser.add_argument("--demo", action="store_true", help="Use the separate, resettable rehearsal workspace")
    parser.add_argument("--data-dir", type=Path, default=data_directory())
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true", help="Backend-only test mode; no desktop window")
    args = parser.parse_args(argv)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        args.data_dir.chmod(0o700)
    except OSError:
        pass
    profile = "demo" if args.demo else "workspace"
    session_path = args.data_dir / f"{profile}-session.json"
    log = logging.handlers.RotatingFileHandler(args.data_dir / "msc-logger.log", maxBytes=1000000, backupCount=3)
    logging.basicConfig(level=logging.INFO, handlers=[log], format="%(asctime)s %(levelname)s %(message)s")
    try:
        lock = InstanceLock(args.data_dir / f"{profile}.lock")
    except RuntimeError:
        if session_path.is_file() and not args.no_browser:
            raise RuntimeError("MSC Logger is already open. Switch to its existing desktop window.") from None
        raise
    store = None
    server = None
    worker = None
    window = None
    try:
        store = Store(args.data_dir / f"{profile}.sqlite3")
        engine = Engine(store, demo=args.demo)
        server = LocalServer(engine, args.port)
        session_path.write_text(json.dumps({"url": server.url, "pid": os.getpid()}))
        try:
            session_path.chmod(0o600)
        except OSError:
            pass
        worker = threading.Thread(target=server.worker, name="mission-worker", daemon=True)
        worker.start()
        if sys.stdout:
            print(f"MSC Logger is ready at {server.url}", flush=True)
        if not args.no_browser:
            window = start_window(server.url, args.data_dir / f"{profile}-display")
            def wait_for_window():
                window.wait()
                server.shutdown()
            threading.Thread(target=wait_for_window, daemon=True).start()
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        return 0
    finally:
        if window and window.poll() is None:
            window.terminate()
            window.wait(timeout=10)
        if server:
            server.stop_event.set()
            if worker:
                worker.join(timeout=15)
            server.server_close()
        if store:
            try:
                store.backup(args.data_dir / "backups" / f"{profile}-last-close.sqlite3")
            except Exception:
                logging.exception("Final backup failed; existing database was retained")
            store.close()
        session_path.unlink(missing_ok=True)
        lock.close()


def desktop_entry(argv=None):
    try:
        return main(argv)
    except Exception as error:
        logging.exception("Application startup failed")
        message = f"MSC Logger could not start.\n\n{error}\n\nExisting records were not replaced. See the app log in {data_directory()}."
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "MSC Logger", 0x10)
        elif sys.stderr:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(desktop_entry())
