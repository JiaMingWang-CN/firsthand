"""A local, gated pipeline stage for durable job-runner tests."""

import sys
import time
from pathlib import Path


def main():
    gate, output = map(Path, sys.argv[1:])
    deadline = time.monotonic() + 15
    while not gate.is_file():
        if time.monotonic() >= deadline:
            raise SystemExit(1)
        time.sleep(0.02)
    output.write_text("completed", encoding="utf-8")


if __name__ == "__main__":
    main()
