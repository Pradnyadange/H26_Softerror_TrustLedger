#!/usr/bin/env python3
"""
verify_capsule.py - Re-check integrity of capsules and raw execution evidence against manifest.json.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest(manifest_path: Path) -> tuple[bool, list[str]]:
    if not manifest_path.exists():
        return False, [f"Manifest not found: {manifest_path}"]

    base_dir = manifest_path.parent
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        return False, [f"Failed to parse manifest JSON: {e}"]

    errors = []
    files_checked = 0

    artifacts = manifest.get("artifacts", {})
    if not artifacts:
        return False, ["Manifest contains no artifact records."]

    for rel_path, expected_sha in artifacts.items():
        file_path = base_dir / rel_path
        if not file_path.exists():
            errors.append(f"Missing artifact: {rel_path}")
            continue

        actual_sha = sha256_file(file_path)
        if actual_sha != expected_sha:
            errors.append(f"Checksum mismatch for {rel_path}: expected {expected_sha}, got {actual_sha}")
        else:
            files_checked += 1

    return len(errors) == 0, errors


def main():
    parser = argparse.ArgumentParser(description="Verify capsule integrity manifest.")
    parser.add_argument("--manifest", default="assets/manifest.json", help="Path to manifest.json")
    args = parser.parse_args()

    m_path = Path(args.manifest).resolve()
    valid, errors = verify_manifest(m_path)

    if valid:
        sys.stdout.write(f"[SUCCESS] Integrity manifest verified: all files match recorded SHA-256 digests.\n")
        sys.exit(0)
    else:
        sys.stderr.write(f"[FAIL] Integrity verification failed ({len(errors)} errors):\n")
        for err in errors:
            sys.stderr.write(f"  - {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
