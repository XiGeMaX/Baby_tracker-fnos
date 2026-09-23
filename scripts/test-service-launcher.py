#!/usr/bin/env python3

import os
from pathlib import Path
import sys


def config_dir() -> Path:
    return Path(os.environ["TRIM_PKGETC"])


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    bind_address = os.environ.get("wizard_bind_address", "").strip()
    port = os.environ.get("wizard_port", "").strip()

    if command == "configure":
        if not bind_address or not port:
            return 2
        directory = config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "bind_address").write_text(f"{bind_address}\n", encoding="utf-8")
        (directory / "service_port").write_text(f"{port}\n", encoding="utf-8")
        return 0

    if command == "restart":
        (config_dir() / "restart-called").write_text(
            f"{bind_address}:{port}\n",
            encoding="utf-8",
        )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
