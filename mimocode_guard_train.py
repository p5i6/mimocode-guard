#!/usr/bin/env python3
"""MiMoCode Guard 1.1 single-file launcher.

Downloads the pinned compressed trainer payload from this repository, verifies
its SHA-256, extracts a readable implementation beside this file, and runs it.
Requires network access on first launch; all model work remains CPU-only.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import runpy
import urllib.request
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/p5i6/mimocode-guard/main/payload/"
PARTS = ("part-01.txt", "part-02.txt", "part-03.txt", "part-04.txt", "part-05.txt")
EXPECTED_SHA256 = "b4c48906ecff6d00f91fc4b8f344c2ac508b589989568b976b0ebc69f3b2af9d"


def main() -> None:
    encoded_parts = []
    for name in PARTS:
        request = urllib.request.Request(BASE_URL + name, headers={"User-Agent": "MiMoCode-Guard/1.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            encoded_parts.append(response.read().decode("ascii").strip())
    source = gzip.decompress(base64.b64decode("".join(encoded_parts), validate=True))
    actual_sha256 = hashlib.sha256(source).hexdigest()
    if actual_sha256 != EXPECTED_SHA256:
        raise RuntimeError(
            f"Trainer integrity check failed: expected {EXPECTED_SHA256}, got {actual_sha256}"
        )

    implementation = Path(__file__).resolve().with_name("_mimocode_guard_train_impl.py")
    implementation.write_bytes(source)
    print(f"[MiMoCode Guard] Verified trainer SHA-256: {actual_sha256}", flush=True)
    runpy.run_path(str(implementation), run_name="__main__")


if __name__ == "__main__":
    main()
