#!/usr/bin/env python3
"""Build a RAM-only Polaris boot image with periodic scheduler ticks.

The kernel, ramdisk, DTB, and every other image byte are copied from the
known-booting installed recovery image. This script never accesses the phone.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "artifacts/polaris-ubuntu-26.04.1-audio-recovery-v1.img"
OUTPUT = ROOT / "artifacts/polaris-ubuntu-26.04.1-nohz-off-temp-v1.img"
SOURCE_SHA256 = "28a3b429917142bceb985139640e72be9ee1e76926852c947f8ec3179b33ddc3"
CMDLINE_START = 64
CMDLINE_SIZE = 512


def main() -> None:
    original = SOURCE.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA256:
        raise SystemExit("Source is not the verified installed recovery image")
    if original[:8] != b"ANDROID!":
        raise SystemExit("Unexpected boot-image magic")
    fields = struct.unpack_from("<10I", original, 8)
    kernel_size, _, ramdisk_size, _, second_size, _, _, page_size, header_version, _ = fields
    if page_size != 4096 or header_version != 0 or second_size:
        raise SystemExit("Unexpected boot-image header format")
    if page_size + kernel_size + ramdisk_size > len(original) or len(original) >= 64 * 1024 * 1024:
        raise SystemExit("Unexpected payload size")
    field = original[CMDLINE_START:CMDLINE_START + CMDLINE_SIZE]
    cmdline = field.split(b"\0", 1)[0]
    if b"nohz=" in cmdline or len(cmdline) + len(b" nohz=off") >= CMDLINE_SIZE:
        raise SystemExit("Cannot safely append nohz=off")
    changed = bytearray(original)
    changed[CMDLINE_START:CMDLINE_START + CMDLINE_SIZE] = (cmdline + b" nohz=off").ljust(CMDLINE_SIZE, b"\0")
    if original[page_size:] != changed[page_size:]:
        raise SystemExit("Boot payload unexpectedly changed")
    OUTPUT.write_bytes(changed)
    print(f"source SHA256 {SOURCE_SHA256}")
    print(f"image SHA256  {hashlib.sha256(changed).hexdigest()}")
    print(f"image bytes   {len(changed)}")
    print(f"cmdline       {(cmdline + b' nohz=off').decode()}")
    print("partition writes: none")


if __name__ == "__main__":
    main()
