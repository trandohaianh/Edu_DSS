"""Regenerate requirements.lock.txt inside the pinned production base image (C1.2).

    python tools/lock_dependencies.py            # rewrite requirements.lock.txt
    python tools/lock_dependencies.py --check    # exit 1 if a fresh resolution would differ

Human workflow: edit requirements.txt (direct dependencies, deliberate versions) ->
run this tool -> review the lock diff -> run the release gate. Resolution happens in
the SAME base image the Dockerfile pins (linux/amd64, CPython 3.11.16), never on a
developer machine, so Windows/macOS wheels cannot leak into the lock. Requires Docker.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
LOCK = APP / "requirements.lock.txt"
DOCKERFILE = APP / "Dockerfile"
HEADER = """# EduDSS machine-resolved dependency lock (C1.2) — DO NOT EDIT BY HAND.
# Human-maintained direct dependencies live in requirements.txt; this file pins the
# COMPLETE resolved environment of the production image (python:3.11.16-slim-trixie,
# linux/amd64) so every build of a release installs identical versions.
# Regenerate: python tools/lock_dependencies.py   (see docs/operations/RELEASE_PROCESS.md)
# pip=={pip}
"""


def base_image() -> str:
    match = re.search(r"^FROM\s+(\S+)", DOCKERFILE.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit("cannot find FROM in Dockerfile")
    return match.group(1)


def current_pip() -> str:
    match = re.search(r"^# pip==(\S+)", LOCK.read_text(encoding="utf-8"), re.M) if LOCK.exists() else None
    return match.group(1) if match else "26.2.1"


def resolve(pip_version: str) -> str:
    script = (
        f"pip install -q 'pip=={pip_version}' >/dev/null && "
        "pip install -q -r /src/requirements.txt >/dev/null && "
        "pip install -q --no-deps \"$(grep -i '^xgboost' /src/requirements.lock.txt || echo xgboost==3.1.2)\" >/dev/null && "
        "pip freeze --all | grep -viE '^(pip|setuptools|wheel)=='"
    )
    cmd = ["docker", "run", "--rm", "-v", f"{APP}:/src:ro", "--entrypoint", "sh", base_image(), "-c", script]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"resolution failed:\n{result.stderr[-2000:]}")
    return HEADER.format(pip=pip_version) + result.stdout


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    fresh = resolve(current_pip())
    if args.check:
        same = LOCK.read_text(encoding="utf-8").strip() == fresh.strip()
        print("lock is current" if same else "lock differs from a fresh resolution — review and regenerate")
        return 0 if same else 1
    LOCK.write_text(fresh, encoding="utf-8")
    print(f"wrote {LOCK.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
