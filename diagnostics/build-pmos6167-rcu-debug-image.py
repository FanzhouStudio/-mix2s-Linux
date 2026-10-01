#!/usr/bin/env python3
"""Package the instrumented SDM845 kernel for RAM-only boot diagnosis.

Reuses the previously booted v7 read-only Ubuntu-overlay ramdisk and Polaris
DTB. Only the kernel payload and explicit pseudo-NMI boot option change.
No phone partition is accessed by this program.
"""

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
KERNEL = ROOT.parent / "out-pmos6167-rcu-debug/arch/arm64/boot/Image.gz"
CONFIG = ROOT.parent / "out-pmos6167-rcu-debug/.config"
DTB = ART / "pmos6167/boot/dtbs/qcom/sdm845-xiaomi-polaris.dtb"
OUTPUT = ART / "polaris-boot-pmos6167-rcu-debug-ram-v1.img"
MANIFEST = ART / "pmos6167-rcu-debug-ram-v1.json"
PARAMETER = b"irqchip.gicv3_pseudo_nmi=1"


def main() -> None:
    source = SOURCE.read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise SystemExit("Previously booted v7 image checksum changed")
    config = CONFIG.read_text()
    for symbol in ("ARM64_PSEUDO_NMI", "IRQSOFF_TRACER", "PREEMPT_TRACER"):
        if f"CONFIG_{symbol}=y\n" not in config:
            raise SystemExit(f"Debug kernel lacks CONFIG_{symbol}")
    fields = list(struct.unpack_from("<10I", source, 8))
    old_kernel_size, _, ramdisk_size, _, second_size, _, _, page, version, _ = fields
    if source[:8] != b"ANDROID!" or (page, version, second_size) != (4096, 0, 0):
        raise SystemExit("Unexpected Android boot-image format")
    ramdisk_start = page + ((old_kernel_size + page - 1) // page) * page
    ramdisk = source[ramdisk_start:ramdisk_start + ramdisk_size]
    if not gzip.decompress(ramdisk).startswith(b"070701"):
        raise SystemExit("Unexpected v7 diagnostic ramdisk")
    kernel_gzip = KERNEL.read_bytes()
    if gzip.decompress(kernel_gzip)[56:60] != b"ARM\x64":
        raise SystemExit("Built kernel is not an ARM64 Image")
    dtb = DTB.read_bytes()
    if struct.unpack_from(">I", dtb)[0] != 0xD00DFEED:
        raise SystemExit("Polaris DTB has unexpected format")
    kernel = kernel_gzip + dtb

    header = bytearray(source[:page])
    cmdline = header[64:576].split(b"\0", 1)[0]
    if PARAMETER in cmdline or len(cmdline) + len(PARAMETER) + 2 > 512:
        raise SystemExit("Cannot safely add pseudo-NMI boot option")
    header[64:576] = (cmdline + b" " + PARAMETER).ljust(512, b"\0")
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
        raise SystemExit("RAM candidate exceeds the 64 MiB recovery envelope")
    OUTPUT.write_bytes(image)
    details = {
        "kernel_release": "6.16.7-sdm845",
        "debug_config": ["ARM64_PSEUDO_NMI", "IRQSOFF_TRACER", "PREEMPT_TRACER"],
        "kernel_sha256": hashlib.sha256(kernel_gzip).hexdigest(),
        "dtb_sha256": hashlib.sha256(dtb).hexdigest(),
        "ramdisk_sha256": hashlib.sha256(ramdisk).hexdigest(),
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_bytes": len(image),
        "boot_option": PARAMETER.decode(),
        "activation": "manual touch /run/start-ubuntu-overlay; exit",
        "rootfs": "userdata ext4 ro,norecovery plus tmpfs overlay after manual activation",
        "phone_partition_writes": False,
        "booted": False,
    }
    MANIFEST.write_text(json.dumps(details, indent=2) + "\n")
    print(f"{OUTPUT}: {len(image)} bytes SHA256 {details['image_sha256']}")


if __name__ == "__main__":
    main()
