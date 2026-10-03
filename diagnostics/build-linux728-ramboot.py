#!/usr/bin/env python3
"""Repack the known-booting recovery layout for RAM-only Linux 7.2.8 bring-up.

The old 6.1 initramfs is preserved for early diagnostics. Its kernel modules
cannot load into 7.2.8; this image is not a complete desktop update.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
CANDIDATE = ART / "linux728-polaris-candidate"
SOURCE = ART / "polaris-ubuntu-26.04.1-audio-recovery-v1.img"
OUTPUT = CANDIDATE / "polaris-linux728-ramboot.img"
MANIFEST = CANDIDATE / "ramboot-manifest.json"
SOURCE_HASH = "28a3b429917142bceb985139640e72be9ee1e76926852c947f8ec3179b33ddc3"
KERNEL_HASH = "6ccdad11f83aaef27468aac164832f68ca2bde6e3971451c17d14b8211ae922e"
DTB_HASH = "ceebbaeab7d770d85b8c78c6095e2b4486c05f4cec8c7baedc3f86ffc5c60801"


def verified(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError(f"SHA-256 mismatch: {path}: {digest}")
    return data


def main() -> None:
    boot = verified(SOURCE, SOURCE_HASH)
    kernel = verified(CANDIDATE / "Image.gz", KERNEL_HASH)
    dtb = verified(CANDIDATE / "sdm845-xiaomi-polaris.dtb", DTB_HASH)
    if boot[:8] != b"ANDROID!" or dtb[:4] != b"\xd0\x0d\xfe\xed":
        raise ValueError("Unexpected Android boot or DTB format")

    header = bytearray(boot[:4096])
    fields = list(struct.unpack_from("<10I", header, 8))
    old_kernel_len, _, ramdisk_len, _, second_len, _, _, page, version, _ = fields
    if (page, version, second_len) != (4096, 0, 0):
        raise ValueError("Working recovery layout changed")
    ramdisk_start = page + (old_kernel_len + page - 1) // page * page
    ramdisk = boot[ramdisk_start : ramdisk_start + ramdisk_len]
    if len(ramdisk) != ramdisk_len:
        raise ValueError("Truncated recovery ramdisk")

    payload = kernel + dtb
    fields[0] = len(payload)
    struct.pack_into("<10I", header, 8, *fields)
    digest = hashlib.sha1()
    for part in (payload, ramdisk, b""):
        digest.update(part)
        digest.update(struct.pack("<I", len(part)))
    header[576:608] = digest.digest().ljust(32, b"\0")

    image = bytes(header) + payload + b"\0" * (-len(payload) % page)
    image += ramdisk + b"\0" * (-len(ramdisk) % page)
    if len(image) > 64 * 1024 * 1024:
        raise ValueError("RAM image exceeds 64 MiB recovery envelope")
    OUTPUT.write_bytes(image)
    report = {
        "kernel_release": "7.2.8-polaris",
        "kernel_sha256": KERNEL_HASH,
        "dtb_sha256": DTB_HASH,
        "ramdisk_sha256": hashlib.sha256(ramdisk).hexdigest(),
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_bytes": len(image),
        "partition_flash": False,
        "device_boot_verified": False,
        "old_6_1_modules_compatible": False,
    }
    MANIFEST.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{OUTPUT}: {len(image)} bytes SHA-256 {report['image_sha256']}")


if __name__ == "__main__":
    main()
