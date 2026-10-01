#!/usr/bin/env python3
"""Package the panel-fixed 6.16.7 kernel for RAM-only Polaris diagnosis."""

from __future__ import annotations

import gzip
import hashlib
import json
import struct
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
ART = BASE / "artifacts"
KERNEL = BASE.parent / "out-pmos6167-panel/arch/arm64/boot/Image.gz"
DTB = ART / "pmos6167/boot/dtbs/qcom/sdm845-xiaomi-polaris.dtb"
SOURCE = ART / "polaris-boot-pmos6167-readonly-diag-v2.img"
IMAGE = ART / "polaris-boot-pmos6167-panel-readonly-diag-v3.img"
DETAILS = ART / "pmos6167-panel-diag-v3-manifest.json"
SOURCE_SHA256 = "2e819115dba4a462f3895963c76dbda5a0ed1c5cccdf308dda0250356f4d7a92"


def main() -> None:
    source = SOURCE.read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise SystemExit("The already-booted read-only diagnostic image changed")
    fields = list(struct.unpack_from("<10I", source, 8))
    old_kernel_size, _, ramdisk_size, _, second_size, _, _, page, version, _ = fields
    if source[:8] != b"ANDROID!" or (page, version, second_size) != (4096, 0, 0):
        raise SystemExit("Unexpected Android boot image layout")
    ramdisk_start = page + ((old_kernel_size + page - 1) // page) * page
    ramdisk = source[ramdisk_start:ramdisk_start + ramdisk_size]
    if not gzip.decompress(ramdisk).startswith(b"070701"):
        raise SystemExit("Diagnostic initramfs is not a newc archive")

    kernel_gzip = KERNEL.read_bytes()
    image_raw = gzip.decompress(kernel_gzip)
    dtb = DTB.read_bytes()
    if image_raw[56:60] != b"ARM\x64" or struct.unpack_from(">I", dtb)[0] != 0xd00dfeed:
        raise SystemExit("Built kernel or matching Polaris DTB has unexpected format")
    kernel = kernel_gzip + dtb
    fields[0] = len(kernel)
    header = bytearray(source[:page])
    struct.pack_into("<10I", header, 8, *fields)
    digest = hashlib.sha1()
    for part in (kernel, ramdisk, b""):
        digest.update(part)
        digest.update(struct.pack("<I", len(part)))
    header[576:608] = digest.digest().ljust(32, b"\0")
    output = bytes(header) + kernel + b"\0" * (-len(kernel) % page)
    output += ramdisk + b"\0" * (-len(ramdisk) % page)
    if len(output) > 64 * 1024 * 1024:
        raise SystemExit("Temporary image exceeds the 64 MiB recovery envelope")
    IMAGE.write_bytes(output)
    details = {
        "kernel_release": "6.16.7-sdm845",
        "kernel_source_tag": "sdm845-6.16.7-r0",
        "panel_patch": "historical postmarketOS prepare_prev_first for NT35596S",
        "kernel_sha256": hashlib.sha256(kernel_gzip).hexdigest(),
        "dtb_sha256": hashlib.sha256(dtb).hexdigest(),
        "ramdisk_sha256": hashlib.sha256(ramdisk).hexdigest(),
        "image_sha256": hashlib.sha256(output).hexdigest(),
        "image_bytes": len(output),
        "partition_flash": False,
        "booted": False,
    }
    DETAILS.write_text(json.dumps(details, indent=2) + "\n")
    print(f"{IMAGE}: {len(output)} bytes SHA256 {details['image_sha256']}")


if __name__ == "__main__":
    main()
