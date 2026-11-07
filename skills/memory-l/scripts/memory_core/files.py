"""Standard-library file locking and recoverable atomic writes."""

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import time
import threading

_locks = {}
_registry_lock = threading.Lock()
_held = threading.local()


@contextmanager
def file_lock(path: Path, timeout: float = 10):
    """The operating system releases this advisory lock on process exit."""
    key = str(path.resolve())
    with _registry_lock:
        process_lock = _locks.setdefault(key, threading.RLock())
    with process_lock:
        held = getattr(_held, "paths", set())
        if key in held:
            yield
            return
        with _os_file_lock(path, timeout):
            _held.paths = held | {key}
            try:
                yield
            finally:
                _held.paths = held


@contextmanager
def _os_file_lock(path, timeout):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + timeout
        acquired = False
        try:
            while not acquired:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Memory writer lock timed out: {path}")
                    time.sleep(0.05)
            yield
        finally:
            if acquired:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".memory-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        Path(temporary).unlink(missing_ok=True)
