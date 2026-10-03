"""OS-held slots shared by the browsing and OASIS processes; crash-safe release."""

import asyncio
import errno
import os
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

LOCK_DIR = Path(__file__).resolve().parents[1] / ".runtime" / "concurrency"


def concurrency_limits(config):
    model = config.get("max_model_concurrency", 10)
    browser = config.get("max_browser_concurrency", 1)
    for name, value in [("LLM_MAX_CONCURRENCY", model), ("BROWSER_MAX_CONCURRENCY", browser)]:
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    return model, min(model, browser)


def try_slot(kind, limit):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    for index in range(limit):
        handle = (LOCK_DIR / f"{kind}-{index}.lock").open("a+b")
        try:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError as error:
            handle.close()
            if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise
    return None


@asynccontextmanager
async def async_slot(config, kind="model"):
    model, browser = concurrency_limits(config)
    handle = None
    try:
        while handle is None:
            handle = try_slot(kind, model if kind == "model" else browser)
            if handle is None:
                await asyncio.sleep(0.02)
        yield
    finally:
        if handle:
            handle.close()


@contextmanager
def sync_slot(config):
    model, _ = concurrency_limits(config)
    handle = None
    try:
        while handle is None:
            handle = try_slot("model", model)
            if handle is None:
                time.sleep(0.02)
        yield
    finally:
        if handle:
            handle.close()
