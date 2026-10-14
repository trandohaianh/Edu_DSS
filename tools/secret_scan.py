"""Secret scanner for the release gate (C1.2). Prints ONLY path, provider and match count —
never the matched value.

    python tools/secret_scan.py [ROOT] [--history] [--allow-local-stores]

- Scans the working tree (tracked, untracked AND git-ignored files, plus members of
  .docx/.pptx/.xlsx/.zip archives) for live-looking API keys and private keys.
- --history also scans every commit reachable from any ref, via `git grep` (paths only).
- Git-ignored local secret stores (`.env`, `app/.env`) are reported but only block when
  --allow-local-stores is NOT given; CI checkouts never contain them.
Exit 1 when a blocking finding exists.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

PATTERNS = {
    "OpenAI": rb"sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}",
    "Anthropic": rb"sk-ant-[A-Za-z0-9_-]{32,}",
    "Groq": rb"gsk_[A-Za-z0-9]{40,}",
    "Google/Gemini (AIza)": rb"AIza[0-9A-Za-z_-]{35}",
    "Google/Gemini (AQ.)": rb"AQ\.[A-Za-z0-9_-]{40,}",
    "HuggingFace": rb"hf_[A-Za-z0-9]{30,}",
    "GitHub token": rb"gh[pousr]_[A-Za-z0-9]{36,}",
    "AWS access key": rb"AKIA[0-9A-Z]{16}",
    "Private key": rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
}
COMPILED = {name: re.compile(p) for name, p in PATTERNS.items()}
SKIP_DIRS = {
    ".git",
    ".venv",
    ".venv_torch210_experimental",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".conda",
}
ARCHIVES = {".docx", ".pptx", ".xlsx", ".zip"}
LOCAL_STORES = {".env", "app/.env"}
MAX_BYTES = 50 * 1024 * 1024


def _hits(data: bytes) -> dict:
    return {name: len(rx.findall(data)) for name, rx in COMPILED.items() if rx.search(data)}


def scan_tree(root: Path) -> list[tuple[str, str, int]]:
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            try:
                if path.stat().st_size > MAX_BYTES:
                    continue
                if path.suffix.lower() in ARCHIVES and zipfile.is_zipfile(path):
                    with zipfile.ZipFile(path) as zf:
                        for member in zf.namelist():
                            for provider, n in _hits(zf.read(member)).items():
                                findings.append((f"{rel}!{member}", provider, n))
                    continue
                for provider, n in _hits(path.read_bytes()).items():
                    findings.append((rel, provider, n))
            except (OSError, zipfile.BadZipFile, RuntimeError):
                continue
    return findings


def scan_history(root: Path) -> list[tuple[str, str, int]]:
    try:
        revs = subprocess.run(["git", "rev-list", "--all"], cwd=root, capture_output=True, text=True,
                              check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return []
    findings: dict[tuple[str, str], int] = {}
    for provider, pattern in PATTERNS.items():
        regex = pattern.decode()
        for i in range(0, len(revs), 50):
            out = subprocess.run(["git", "grep", "-l", "-E", "-e", regex, *revs[i:i + 50]], cwd=root,
                                 capture_output=True, text=True).stdout
            for line in out.splitlines():
                commit, _, path = line.partition(":")
                findings[(path, provider)] = findings.get((path, provider), 0) + 1
    return [(f"history:{path}", provider, n) for (path, provider), n in sorted(findings.items())]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--allow-local-stores", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    findings = scan_tree(root) + (scan_history(root) if args.history else [])
    blocking = 0
    for rel, provider, n in sorted(findings):
        local = rel in LOCAL_STORES
        is_blocking = not (local and args.allow_local_stores)
        blocking += is_blocking
        label = "BLOCKING" if is_blocking else "LOCAL_SECRET_STORE (git-ignored, allowed)"
        print(f"{rel}\t{provider}\tmatches={n}\t{label}")
    print(f"--- secret scan: findings={len(findings)} blocking={blocking} history={'yes' if args.history else 'no'}")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
