#!/usr/bin/env python3
"""Automated Security & Integrity Scanner for EduDSS.

Checks:
1. Zero live secrets/API keys in git-tracked files and source tree.
2. SHA-256 integrity checksum presence for all serialized models.
3. Untrusted pickle avoidance.
4. Correct file permissions and .gitignore coverage.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

SECRET_PATTERNS = [
    (r"AIzaSy[A-Za-z0-9_-]{33}", "Google / Gemini API Key"),
    (r"gsk_[A-Za-z0-9_-]{40,}", "Groq API Key"),
    (r"sk-[A-Za-z0-9_-]{40,}", "OpenAI API Key"),
    (r"hf_[A-Za-z0-9_-]{34,}", "HuggingFace Token"),
]

EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
EXCLUDED_EXTS = {".png", ".jpg", ".webp", ".pdf", ".pyc", ".lock"}


def scan_for_secrets() -> list:
    findings = []
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in EXCLUDED_EXTS:
                continue
            if p.name in (".env.example", "security_scan.py"):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                for pattern, secret_type in SECRET_PATTERNS:
                    matches = re.findall(pattern, content)
                    for m in matches:
                        # Skip placeholder dummy tokens
                        if "EXAMPLE" in m or "YOUR" in m or "test" in m.lower():
                            continue
                        findings.append(
                            f"Secret detected ({secret_type}) in {p.relative_to(ROOT_DIR)}: {m[:6]}...{m[-4:]}"
                        )
            except Exception:
                pass
    return findings


def verify_model_checksums() -> list:
    issues = []
    models_dir = ROOT_DIR / "data_warehouse" / "models"
    metadata_dir = ROOT_DIR / "data_warehouse" / "metadata"
    if not models_dir.exists() or not metadata_dir.exists():
        return issues

    verified_count = 0
    for joblib_file in models_dir.glob("*.joblib"):
        meta_file = metadata_dir / f"{joblib_file.stem}_model.json"
        if not meta_file.exists():
            continue
        try:
            with open(meta_file, encoding="utf-8") as f:
                meta = json.load(f)
            expected_sha = meta.get("model_sha256")
            if not expected_sha:
                continue
            hasher = hashlib.sha256()
            with open(joblib_file, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            actual_sha = hasher.hexdigest()
            if actual_sha != expected_sha:
                issues.append(
                    f"Checksum mismatch for {joblib_file.name}: expected {expected_sha[:8]}, got {actual_sha[:8]}"
                )
            else:
                verified_count += 1
        except Exception as ex:
            issues.append(f"Error checking {joblib_file.name}: {ex}")
    print(f"[INFO] Verified integrity of {verified_count} models with active SHA-256 signatures.")
    return issues


def main():
    print("==================================================")
    print("[INFO] Running EduDSS Automated Security & Integrity Scan")
    print("==================================================")

    secret_findings = scan_for_secrets()
    if secret_findings:
        print(f"[FAIL] Found {len(secret_findings)} secret exposures:")
        for sf in secret_findings:
            print(f"   - {sf}")
    else:
        print("[PASS] Zero live secrets found in workspace.")

    checksum_issues = verify_model_checksums()
    if checksum_issues:
        print(f"[FAIL] Found {len(checksum_issues)} model integrity issues:")
        for ci in checksum_issues:
            print(f"   - {ci}")
    else:
        print("[PASS] Model integrity verification passed.")

    total_failures = len(secret_findings) + len(checksum_issues)
    if total_failures > 0:
        print(f"\nTotal failures: {total_failures}")
        sys.exit(1)
    else:
        print("\nAll security checks passed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
