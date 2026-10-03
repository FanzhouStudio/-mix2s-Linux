#!/usr/bin/env python3
"""Package a RAM-only SDM845 pixel-clock candidate from the known v7 image."""

from __future__ import annotations

import gzip
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
SOURCE = ART / "polaris-boot-pmos6167-panel-overlay-diag-v7.img"
SOURCE_SHA256 = "2c9cf728a95006fb105ea6150ca1f593c4ebbc175da89771d9b32fd297e76920"
KERNEL = ROOT.parent / "out-pmos6167-panel/arch/arm64/boot/Image.gz"
DTB = ART / "pmos6167/boot/dtbs/qcom/sdm845-xiaomi-polaris.dtb"
OUTPUT = ART / "polaris-boot-pmos6167-pixel-clock-ram-v1.img"
MANIFEST = ART / "pmos6167-pixel-clock-ram-v1.json"


def main() -> None:
    source = SOURCE.read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise SystemExit("Known v7 boot image checksum changed")
    fields = list(struct.unpack_from("<10I", source, 8))
    old_kernel_size, _, ramdisk_size, _, second_size, _, _, page, version, _ = fields
    if source[:8] != b"ANDROID!" or (page, version, second_size) != (4096, 0, 0):
        raise SystemExit("Unexpected Android boot image format")
    ramdisk_start = page + ((old_kernel_size + page - 1) // page) * page
    ramdisk = source[ramdisk_start:ramdisk_start + ramdisk_size]
    if not gzip.decompress(ramdisk).startswith(b"070701"):
        raise SystemExit("Unexpected diagnostic ramdisk")
    kernel_gzip = KERNEL.read_bytes()
    if gzip.decompress(kernel_gzip)[56:60] != b"ARM\x64":
        raise SystemExit("Built kernel is not an ARM64 Image")
    dtb = DTB.read_bytes()
    if struct.unpack_from(">I", dtb)[0] != 0xD00DFEED:
        raise SystemExit("Unexpected Polaris DTB")
    kernel = kernel_gzip + dtb

    header = bytearray(source[:page])
    fields[0] = len(kernel)
    struct.pack_into("<10I", header, 8, *fields)
    digest = hashlib.sha1()
    for part in (kernel, ramdisk, b""):
        digest.update(part)
        digest.update(struct.pack("<I", len(part)))
    header[576:608] = digest.digest().ljust(32, b"\0")
    image = bytes(header) + kernel + b"\0" * (-len(kernel) % page)
    image += ramdisk + b"\0" * (-len(ramdisk) % page)
    if len(image) > 64 * 1024 * 1024:
        raise SystemExit("RAM candidate exceeds the 64 MiB envelope")
    OUTPUT.write_bytes(image)
    details = {
        "kernel_release": "6.16.7-sdm845",
        "change": "SDM845 MDSS pixel clocks keep parent enabled during operations (upstream a1d63493634e)",
        "kernel_sha256": hashlib.sha256(kernel_gzip).hexdigest(),
        "dtb_sha256": hashlib.sha256(dtb).hexdigest(),
        "ramdisk_sha256": hashlib.sha256(ramdisk).hexdigest(),
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_bytes": len(image),
        "activation": "manual touch /run/start-ubuntu-overlay; exit",
        "rootfs": "userdata ext4 ro,noload plus tmpfs overlay after manual activation",
        "phone_partition_writes": False,
        "booted": False,
    }
    MANIFEST.write_text(json.dumps(details, indent=2) + "\n")
    print(f"{OUTPUT}: {len(image)} bytes SHA256 {details['image_sha256']}")


if __name__ == "__main__":
    main()
