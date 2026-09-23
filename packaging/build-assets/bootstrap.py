#!/usr/bin/env python3

import os
from pathlib import Path

import app as baby_tracker


def main():
    data_dir = os.environ.get("BABY_TRACKER_DATA_DIR") or os.environ.get("TRIM_PKGVAR")
    if not data_dir:
        raise RuntimeError("BABY_TRACKER_DATA_DIR or TRIM_PKGVAR is required")

    database_path = Path(data_dir) / "baby.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    baby_tracker.app.config["DATABASE"] = str(database_path)

    with baby_tracker.app.app_context():
        baby_tracker.init_db()


if __name__ == "__main__":
    main()
