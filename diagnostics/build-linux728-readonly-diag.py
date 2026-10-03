#!/usr/bin/env python3
"""Build a RAM-only, no-storage-mount Android boot v0 image for Polaris."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import stat
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
OUT = ART / "linux728-polaris-candidate"
SOURCE = ART / "polaris-ubuntu-26.04.1-audio-recovery-v1.img"
SOURCE_HASH = "28a3b429917142bceb985139640e72be9ee1e76926852c947f8ec3179b33ddc3"
BUSYBOX = ART / "pmos6167/original-busybox"
BUSYBOX_HASH = "c2f279d1d5640a0f327890d41cad594c0f059f3fed3f96dd72fdcc4f5e18ec02"
FIRMWARE = ROOT / "rootfs-ubuntu-26.04.1/lib/firmware/qcom"
FIRMWARE_HASHES = {
    "a630_gmu.bin": "da8d9b1b1f5c1a0b311f32567093b4828f3c80031dd8435f91ac13c664e173a6",
    "a630_sqe.fw": "a4b9e92bbeaff044d7713610d2ba8526d733756b977a9625958fd264dfb8eaa3",
}
ZAP_FIRMWARE = ART / "firmware/polaris/a630_zap.mbn"
ZAP_FIRMWARE_HASH = "c0a830808c7ae886e5a5b6dec48afb9c9805d0579d9cac498ebc36b8b06bedde"
IMAGE = OUT / "polaris-linux728-readonly-diag.img"
MANIFEST = OUT / "readonly-diag-manifest.json"


def read_verified(path: Path, digest: str) -> bytes:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"SHA-256 mismatch: {path}")
    return data


def append_newc(out: bytearray, name: str, mode: int, data: bytes, inode: int,
                major: int = 0, minor: int = 0) -> None:
    encoded = name.encode() + b"\0"
    fields = (inode, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0,
              len(data), 0, 0, major, minor, len(encoded), 0)
    out += b"070701" + b"".join(f"{value:08x}".encode() for value in fields)
    out += encoded
    out += b"\0" * (-len(out) % 4)
    out += data
    out += b"\0" * (-len(out) % 4)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-zap-firmware", action="store_true",
                        help="Test GPU secure firmware separately from fbdev changes")
    parser.add_argument("--legacy-dpu-planes", action="store_true",
                        help="Use the non-virtual DPU plane default of the working 6.16 branch")
    parser.add_argument("--reserve-xbl-framebuffer", action="store_true",
                        help="Use the DTB variant reserving XBL's 36 MiB scanout buffer")
    parser.add_argument("--xbl-iommu-map", action="store_true",
                        help="Map the reserved XBL scanout buffer before display IOMMU attach")
    args = parser.parse_args()
    if args.xbl_iommu_map and (args.legacy_dpu_planes or args.include_zap_firmware):
        parser.error("XBL IOMMU handoff must be isolated from other kernel changes")
    if args.legacy_dpu_planes and args.reserve_xbl_framebuffer:
        parser.error("Test legacy planes and XBL reservation separately")
    boot = read_verified(SOURCE, SOURCE_HASH)
    busybox = read_verified(BUSYBOX, BUSYBOX_HASH)
    kernel_name = "Image-xbl-iommu.gz" if args.xbl_iommu_map else "Image.gz"
    kernel = (OUT / kernel_name).read_bytes()
    dtb_name = ("sdm845-xiaomi-polaris-xbl-reserved.dtb"
                if args.reserve_xbl_framebuffer or args.xbl_iommu_map
                else "sdm845-xiaomi-polaris.dtb")
    dtb = (OUT / dtb_name).read_bytes()
    if (args.reserve_xbl_framebuffer or args.xbl_iommu_map) and b"framebuffer@9d400000" not in dtb:
        raise ValueError("Selected DTB has no XBL framebuffer reservation")
    config = (OUT / "kernel.config").read_text()
    for option in ("SCSI_UFS_QCOM", "PHY_QCOM_QMP_UFS", "PHY_QCOM_QUSB2",
                   "USB_CONFIGFS", "USB_CONFIGFS_ACM", "U_SERIAL_CONSOLE",
                   "REGULATOR_QCOM_REFGEN", "QCOM_GPI_DMA",
                   "BACKLIGHT_QCOM_WLED",
                   "REGULATOR_QCOM_LABIBB"):
        if f"CONFIG_{option}=y\n" not in config:
            raise ValueError(f"Required built-in driver missing: {option}")
    if gzip.decompress(kernel)[56:60] != b"ARM\x64" or dtb[:4] != b"\xd0\x0d\xfe\xed":
        raise ValueError("Unexpected kernel or DTB format")
    if "# CONFIG_USB_G_SERIAL is not set\n" not in config:
        raise ValueError("Legacy gadget must not claim the UDC before init")
    if boot[:8] != b"ANDROID!":
        raise ValueError("Unexpected reference boot image")
    fields = list(struct.unpack_from("<10I", boot, 8))
    _, _, _, _, second_size, _, _, page, version, _ = fields
    if (page, version, second_size) != (4096, 0, 0):
        raise ValueError("Unexpected reference boot layout")

    entries: dict[str, tuple[int, bytes, int, int]] = {}

    def add(name: str, mode: int, data: bytes = b"", major: int = 0,
            minor: int = 0) -> None:
        parent = Path(name).parent
        while str(parent) != ".":
            entries.setdefault(parent.as_posix(), (stat.S_IFDIR | 0o755, b"", 0, 0))
            parent = parent.parent
        entries[name] = mode, data, major, minor

    for directory in ("bin", "sbin", "usr/bin", "usr/sbin", "dev", "proc", "sys", "run", "tmp"):
        add(directory, stat.S_IFDIR | 0o755)
    add("bin/busybox", stat.S_IFREG | 0o755, busybox)
    add("bin/sh", stat.S_IFLNK | 0o777, b"busybox")
    add("init", stat.S_IFREG | 0o755,
        (ROOT / "diagnostics/init-linux728-readonly").read_bytes())
    for name, digest in FIRMWARE_HASHES.items():
        add("lib/firmware/qcom/" + name, stat.S_IFREG | 0o644,
            read_verified(FIRMWARE / name, digest))
    if args.include_zap_firmware:
        add("lib/firmware/qcom/sdm845/polaris/a630_zap.mbn", stat.S_IFREG | 0o644,
            read_verified(ZAP_FIRMWARE, ZAP_FIRMWARE_HASH))
    for name, major, minor in (("console", 5, 1), ("null", 1, 3),
                               ("tty", 5, 0), ("tty1", 4, 1)):
        add("dev/" + name, stat.S_IFCHR | 0o600, b"", major, minor)
    archive = bytearray()
    for inode, (name, (mode, data, major, minor)) in enumerate(sorted(entries.items()), 1):
        append_newc(archive, name, mode, data, inode, major, minor)
    append_newc(archive, "TRAILER!!!", 0, b"", len(entries) + 1)
    archive += b"\0" * (-len(archive) % 512)
    ramdisk = gzip.compress(archive, compresslevel=9, mtime=0)

    payload = kernel + dtb
    header = bytearray(boot[:page])
    fields[0], fields[2] = len(payload), len(ramdisk)
    struct.pack_into("<10I", header, 8, *fields)
    cmdline = b"console=tty0 console=ttyGS0 loglevel=6 panic=0 fw_devlink=off deferred_probe_timeout=60 rdinit=/init mobile.qcomsoc=qcom/sdm845 mobile.vendor=xiaomi mobile.model=polaris"
    if args.legacy_dpu_planes:
        cmdline += b" msm.dpu_use_virtual_planes=0"
    if len(cmdline) > 512:
        raise ValueError("Diagnostic kernel command line exceeds boot image field")
    header[64:576] = cmdline.ljust(512, b"\0")
    digest = hashlib.sha1()
    for part in (payload, ramdisk, b""):
        digest.update(part)
        digest.update(struct.pack("<I", len(part)))
    header[576:608] = digest.digest().ljust(32, b"\0")
    image = bytes(header) + payload + b"\0" * (-len(payload) % page)
    image += ramdisk + b"\0" * (-len(ramdisk) % page)
    if len(image) > 64 * 1024 * 1024:
        raise ValueError("Diagnostic image exceeds recovery size")
    image_name = ("polaris-linux728-xbl-iommu-diag.img"
                  if args.xbl_iommu_map else
                  "polaris-linux728-xbl-reserved-diag.img"
                  if args.reserve_xbl_framebuffer else
                  "polaris-linux728-legacy-dpu-diag.img"
                  if args.legacy_dpu_planes else IMAGE.name)
    manifest_name = ("xbl-iommu-diag-manifest.json"
                     if args.xbl_iommu_map else
                     "xbl-reserved-diag-manifest.json"
                     if args.reserve_xbl_framebuffer else
                     "legacy-dpu-diag-manifest.json"
                     if args.legacy_dpu_planes else MANIFEST.name)
    image_path = OUT / image_name
    manifest_path = OUT / manifest_name
    image_path.write_bytes(image)
    manifest = {
        "kernel_release": "7.2.8-polaris",
        "kernel_sha256": hashlib.sha256(kernel).hexdigest(),
        "dtb_sha256": hashlib.sha256(dtb).hexdigest(),
        "ramdisk_sha256": hashlib.sha256(ramdisk).hexdigest(),
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_bytes": len(image),
        "storage_mounts": False,
        "partition_flash": False,
        "zap_firmware": args.include_zap_firmware,
        "legacy_dpu_planes": args.legacy_dpu_planes,
        "xbl_framebuffer_reserved": args.reserve_xbl_framebuffer or args.xbl_iommu_map,
        "xbl_iommu_map": args.xbl_iommu_map,
        "cmdline": cmdline.decode(),
        "device_boot_verified": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{image_path}: {len(image)} bytes SHA-256 {manifest['image_sha256']}")


if __name__ == "__main__":
    main()
