#!/usr/bin/env python3
"""Repack the RAM-only 6.16.7 panel diagnostic with the booting Kali DTB.

This isolates the DTB as the single variable. It does not write a device.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
ART = BASE / "artifacts"
SOURCE = ART / "polaris-boot-pmos6167-panel-readonly-diag-v3.img"
WORKING = ART / "polaris-ubuntu-26.04.1-audio-recovery-v1.img"
OUTPUT = ART / "polaris-boot-pmos6167-panel-kali-dtb-readonly-diag-v4.img"
MANIFEST = ART / "pmos6167-panel-kali-dtb-diag-v4-manifest.json"
SOURCE_SHA256 = "80d8b6945eb5def7108b4c88840968360839057dee00a554eaaa331900ff0b9e"
WORKING_SHA256 = "28a3b429917142bceb985139640e72be9ee1e76926852c947f8ec3179b33ddc3"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"


def pieces(boot: bytes) -> tuple[bytearray, list[int], bytes, bytes, int]:
    if boot[:8] != b"ANDROID!":
        raise ValueError("Unexpected boot magic")
    fields = list(struct.unpack_from("<10I", boot, 8))
    kernel_len, _, ramdisk_len, _, second_len, _, _, page, version, _ = fields
    if (page, version, second_len) != (4096, 0, 0):
        raise ValueError("Unexpected boot layout")
    kernel = boot[page : page + kernel_len]
    ramdisk_start = page + (kernel_len + page - 1) // page * page
    ramdisk = boot[ramdisk_start : ramdisk_start + ramdisk_len]
    return bytearray(boot[:page]), fields, kernel, ramdisk, page


def dtb_from_kernel(kernel: bytes) -> tuple[int, bytes]:
    offset = kernel.find(FDT_MAGIC)
    if offset < 0 or kernel.find(FDT_MAGIC, offset + 4) >= 0:
        raise ValueError("Expected one appended DTB")
    size = struct.unpack_from(">I", kernel, offset + 4)[0]
    if offset + size != len(kernel):
        raise ValueError("DTB is not at the end of the kernel payload")
    return offset, kernel[offset:]


def main() -> None:
    source = SOURCE.read_bytes()
    working = WORKING.read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise SystemExit("Panel-fixed RAM diagnostic differs from verified source")
    if hashlib.sha256(working).hexdigest() != WORKING_SHA256:
        raise SystemExit("Working installed recovery differs from verified source")
    header, fields, kernel, ramdisk, page = pieces(source)
    _, _, old_kernel, _, _ = pieces(working)
    offset, prior_dtb = dtb_from_kernel(kernel)
    _, working_dtb = dtb_from_kernel(old_kernel)
    updated_kernel = kernel[:offset] + working_dtb
    fields[0] = len(updated_kernel)
    struct.pack_into("<10I", header, 8, *fields)
    digest = hashlib.sha1()
    for part in (updated_kernel, ramdisk, b""):
        digest.update(part)
        digest.update(struct.pack("<I", len(part)))
    header[576:608] = digest.digest().ljust(32, b"\0")
    image = bytes(header) + updated_kernel + b"\0" * (-len(updated_kernel) % page)
    image += ramdisk + b"\0" * (-len(ramdisk) % page)
    if len(image) > 64 * 1024 * 1024:
        raise SystemExit("Temporary image exceeds the recovery envelope")
    OUTPUT.write_bytes(image)
    manifest = {
        "kernel_release": "6.16.7-sdm845",
        "kernel_sha256": hashlib.sha256(kernel[:offset]).hexdigest(),
        "prior_dtb_sha256": hashlib.sha256(prior_dtb).hexdigest(),
        "working_kali_dtb_sha256": hashlib.sha256(working_dtb).hexdigest(),
        "ramdisk_sha256": hashlib.sha256(ramdisk).hexdigest(),
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_bytes": len(image),
        "partition_flash": False,
        "booted": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{OUTPUT}: {len(image)} bytes SHA256 {manifest['image_sha256']}")


if __name__ == "__main__":
    main()
