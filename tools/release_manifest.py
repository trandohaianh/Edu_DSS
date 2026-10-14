"""Release manifest — generate for a built image, verify against a running deployment (C1.2).

    python tools/release_manifest.py generate --image edudss:1.0.0-rc.1 [--evidence PATH ...] [--out FILE]
    python tools/release_manifest.py verify --manifest FILE --url http://HOST:8081/version

`generate` reads the release identity FROM THE IMAGE ITSELF (docker run ... release module),
so the manifest describes exactly what will be deployed, and adds the immutable image ID /
registry digest. `verify` fetches /version from a running instance and fails (exit 1) if
version, Git SHA, dependency lock, Alembic head or RAG config differ, or if the running
database is not at the release's Alembic head. No secrets are read or written.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

MATCH_KEYS = ("version", "git_sha", "dependency_lock", "alembic_head", "config_schema_version", "rag_config_version")


def _docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"docker {' '.join(args[:2])} failed: {result.stderr.strip()[:300]}")
    return result.stdout.strip()


def image_release_identity(image: str) -> dict:
    out = _docker("run", "--rm", "--entrypoint", "python", image, "-c",
                  "import json; from dss.core.release import release_identity; print(json.dumps(release_identity()))")
    return json.loads(out.splitlines()[-1])


def generate(image: str, evidence: list[str]) -> dict:
    info = json.loads(_docker("image", "inspect", image))[0]
    identity = image_release_identity(image)
    ev = []
    for item in evidence:
        path = Path(item)
        ev.append({"path": path.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                  if path.is_file() else {"path": path.as_posix(), "sha256": None})
    return {
        "manifest_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "release": identity,
        "artifact": {
            "image": image,
            "image_id": info.get("Id"),                       # content-addressed local ID
            "repo_digests": info.get("RepoDigests") or [],    # registry digest once pushed
            "labels": {k: v for k, v in (info.get("Config", {}).get("Labels") or {}).items()
                       if k.startswith("org.opencontainers.image.")},
        },
        "test_evidence": ev,
    }


def verify(manifest: dict, running: dict) -> list[str]:
    problems = []
    release = manifest["release"]
    live = running.get("release", {})
    for key in MATCH_KEYS:
        if release.get(key) != live.get(key):
            problems.append(f"{key}: manifest={release.get(key)!r} running={live.get(key)!r}")
    db = (running.get("runtime") or {}).get("database") or {}
    if db and db.get("at_head") is False:
        problems.append(f"database revision {db.get('database_revision')} is not at release head {release.get('alembic_head')}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--image", required=True)
    g.add_argument("--evidence", nargs="*", default=[])
    g.add_argument("--out", type=Path)
    v = sub.add_parser("verify")
    v.add_argument("--manifest", type=Path, required=True)
    v.add_argument("--url", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "generate":
        manifest = generate(args.image, args.evidence)
        text = json.dumps(manifest, indent=2, ensure_ascii=False)
        if args.out:
            args.out.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    with urllib.request.urlopen(args.url, timeout=10) as resp:
        running = json.loads(resp.read().decode("utf-8"))
    problems = verify(manifest, running)
    print(json.dumps({"ok": not problems, "problems": problems,
                      "running_version": running.get("release", {}).get("version")}, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
