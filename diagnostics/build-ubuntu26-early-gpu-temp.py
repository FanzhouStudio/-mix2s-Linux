#!/usr/bin/env python3
"""Add the verified Polaris GPU firmware to the currently booting recovery image.

The image is only an artifact for `fastboot boot`; this script never writes a
device partition. Its kernel, DTB, and all other initramfs entries are retained.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import runpy
import stat
import struct
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
ART = BASE / "artifacts"
SOURCE = ART / "polaris-ubuntu-26.04.1-audio-recovery-v1.img"
FIRMWARE = ART / "firmware/polaris/a630_zap.mbn"
IMAGE = ART / "polaris-ubuntu-26.04.1-early-gpu-temp-v1.img"
RAMDISK = ART / "initramfs-ubuntu-26.04.1-early-gpu-temp-v1.cpio.gz"
DETAILS = ART / "ubuntu26-early-gpu-temp-v1.json"
COMMON = runpy.run_path(str(BASE / "diagnostics/build-kali61-audio-diag.py"))
SOURCE_SHA256 = "28a3b429917142bceb985139640e72be9ee1e76926852c947f8ec3179b33ddc3"
FIRMWARE_SHA256 = "c0a830808c7ae886e5a5b6dec48afb9c9805d0579d9cac498ebc36b8b06bedde"
FIRMWARE_PATH = "lib/firmware/qcom/sdm845/polaris/a630_zap.mbn"


def main() -> None:
    original = SOURCE.read_bytes()
    firmware = FIRMWARE.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA256:
        raise SystemExit("Source image is not the installed known-booting recovery")
    if len(firmware) != 14256 or hashlib.sha256(firmware).hexdigest() != FIRMWARE_SHA256:
        raise SystemExit("OEM Polaris GPU firmware differs from the verified copy")
    fields = list(struct.unpack_from("<10I", original, 8))
    kernel_size, _, ramdisk_size, _, second_size, _, _, page, version, _ = fields
    if original[:8] != b"ANDROID!" or page != 4096 or second_size or version:
        raise SystemExit("Unexpected Android boot image header")
    kernel = original[page:page + kernel_size]
    ramdisk_start = page + ((kernel_size + page - 1) // page) * page
    entries, highest_inode = COMMON["parse_cpio"](
        gzip.decompress(original[ramdisk_start:ramdisk_start + ramdisk_size])
    )
    out = bytearray()
    names = set()
    changed_init = False
    for name, header, data in entries:
        names.add(name)
        if name == "init":
            old = b'    ln -sf /run/vendor/firmware/a630_zap.elf "$fwroot/a630_zap.mbn"'
            new = b'    [ -e "$fwroot/a630_zap.mbn" ] || ln -sf /run/vendor/firmware/a630_zap.elf "$fwroot/a630_zap.mbn"'
            if data.count(old) != 1:
                raise SystemExit("Expected a single GPU firmware alias in init")
            data = data.replace(old, new)
            header = header[:54] + f"{len(data):08x}".encode() + header[62:]
            changed_init = True
        out.extend(header)
        out.extend(name.encode() + b"\0")
        out.extend(b"\0" * (-len(out) % 4))
        out.extend(data)
        out.extend(b"\0" * (-len(out) % 4))
    if not changed_init or FIRMWARE_PATH in names:
        raise SystemExit("Init unchanged or GPU firmware already present")
    inode = highest_inode + 1
    for directory in ("lib/firmware/qcom/sdm845", "lib/firmware/qcom/sdm845/polaris"):
        if directory not in names:
            COMMON["append_cpio"](out, directory, stat.S_IFDIR | 0o755, b"", inode)
            inode += 1
    COMMON["append_cpio"](out, FIRMWARE_PATH, stat.S_IFREG | 0o644, firmware, inode)
    inode += 1
    COMMON["append_cpio"](out, "TRAILER!!!", 0, b"", inode)
    out.extend(b"\0" * (-len(out) % 512))
    compressed = gzip.compress(bytes(out), compresslevel=9, mtime=0)
    RAMDISK.write_bytes(compressed)
    header = bytearray(original[:page])
    fields[2] = len(compressed)
    struct.pack_into("<10I", header, 8, *fields)
    digest = hashlib.sha1()
    for part in (kernel, compressed, b""):
        digest.update(part)
        digest.update(struct.pack("<I", len(part)))
    header[576:608] = digest.digest().ljust(32, b"\0")
    image = bytes(header) + kernel + b"\0" * (-len(kernel) % page)
    image += compressed + b"\0" * (-len(compressed) % page)
    if len(image) > 64 * 1024 * 1024:
        raise SystemExit("Temporary boot image exceeds 64 MiB")
    IMAGE.write_bytes(image)
    DETAILS.write_text(json.dumps({
        "source_sha256": SOURCE_SHA256,
        "firmware_sha256": FIRMWARE_SHA256,
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_bytes": len(image),
        "kernel_sha256": hashlib.sha256(kernel).hexdigest(),
        "changes": "Early OEM a630_zap.mbn in initramfs; keep file instead of replacing it with a late vendor symlink",
        "partition_flash": False,
    }, indent=2) + "\n")
    print(f"{IMAGE}: {len(image)} bytes SHA256 {hashlib.sha256(image).hexdigest()}")


if __name__ == "__main__":
    main()
