#!/usr/bin/env python3
"""Resume a slow, checkpointed transfer of the ChatGPT SquashFS image.

The phone only writes small chunks; decompression and image creation happen on
the host. The SSH profile is the existing key-only, Wi-Fi-bound diagnostic one.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "artifacts/chatgpt-arm64-portable/chatgpt-26.924.22138-arm64.squashfs"
SSH_CONFIG = ROOT / "diagnostics/ssh/config"
REMOTE = "polaris-diag"
DEST = "/home/polaris/.local/share/polaris-chatgpt/chatgpt.squashfs.part"
CHUNK = 8 * 1024 * 1024
BLOCK = 64 * 1024
RATE_BYTES_PER_SEC = 2 * 1024 * 1024


def ssh(*remote_args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-F", str(SSH_CONFIG), REMOTE, *remote_args],
        text=True,
        capture_output=capture,
        check=True,
    )


def remote_size() -> int:
    result = ssh("sh", "-c", f"'stat -c %s {DEST} 2>/dev/null || echo 0'", capture=True)
    return int(result.stdout.strip())


def main() -> None:
    size = SOURCE.stat().st_size
    existing = remote_size()
    if existing > size:
        raise SystemExit(f"Remote file is larger than the source: {existing} > {size}")
    start = existing // CHUNK
    count = (size + CHUNK - 1) // CHUNK
    print(f"Source: {size} bytes; remote: {existing} bytes; resume chunk {start}/{count}", flush=True)
    with SOURCE.open("rb") as source:
        for index in range(start, count):
            source.seek(index * CHUNK)
            remaining = min(CHUNK, size - index * CHUNK)
            command = [
                "ssh", "-F", str(SSH_CONFIG), REMOTE,
                "dd", f"of={DEST}", "bs=1M", f"seek={index * (CHUNK // (1024 * 1024))}",
                "conv=notrunc,fsync", "status=none",
            ]
            with subprocess.Popen(command, stdin=subprocess.PIPE) as process:
                assert process.stdin is not None
                while remaining:
                    data = source.read(min(BLOCK, remaining))
                    if not data:
                        raise RuntimeError("Unexpected end of source image")
                    process.stdin.write(data)
                    remaining -= len(data)
                    time.sleep(len(data) / RATE_BYTES_PER_SEC)
                process.stdin.close()
                if process.wait() != 0:
                    raise RuntimeError(f"SSH transfer failed on chunk {index}; rerun to resume")
            expected = min((index + 1) * CHUNK, size)
            actual = remote_size()
            if actual != expected:
                raise RuntimeError(f"Remote length after chunk {index}: {actual}, expected {expected}")
            print(f"Transferred {actual}/{size} bytes", flush=True)
    digest = hashlib.sha256()
    with SOURCE.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    local_hash = digest.hexdigest()
    remote_hash = ssh("sha256sum", DEST, capture=True).stdout.split()[0]
    if remote_hash != local_hash:
        raise RuntimeError(f"SHA-256 mismatch: local {local_hash}, remote {remote_hash}")
    print(f"SHA-256 verified: {local_hash}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
