"""Shared filesystem paths for packaged and Docker deployments."""
import os
import shutil


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.abspath(os.getenv("IPTV_DATA_DIR", PROJECT_ROOT))


def ensure_data_dir() -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return DATA_DIR


def data_path(filename: str, *, seed_from_project: bool = False, default_content: str | None = None) -> str:
    ensure_data_dir()
    target = os.path.join(DATA_DIR, filename)
    if os.path.exists(target):
        return target

    source = os.path.join(PROJECT_ROOT, filename)
    if seed_from_project and os.path.exists(source) and os.path.abspath(source) != os.path.abspath(target):
        shutil.copy2(source, target)
    elif default_content is not None:
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(default_content)
    return target
