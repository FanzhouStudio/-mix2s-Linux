#!/usr/bin/env python3
"""Build a RAM-only, manually activated Ubuntu overlay boot for Polaris.

The phone is untouched. The signed postmarketOS module tree is embedded so
systemd cannot load the installed 6.1 modules under the 6.16.7 kernel.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess

BASE = Path(__file__).resolve().parent.parent
ART = BASE / "artifacts"
SOURCE = ART / "polaris-boot-pmos6167-panel-readonly-diag-v3.img"
SOURCE_SHA256 = "80d8b6945eb5def7108b4c88840968360839057dee00a554eaaa331900ff0b9e"
MODULES = ART / "pmos6167/lib/modules/6.16.7-sdm845"
DEST = ART / "polaris-boot-pmos6167-panel-overlay-diag-v7.img"
MANIFEST = ART / "pmos6167-panel-overlay-diag-v7-manifest.json"


def parse_newc(raw: bytes) -> dict[str, tuple[int, bytes, int, int]]:
    entries: dict[str, tuple[int, bytes, int, int]] = {}
    pos = 0
    while raw[pos:pos + 6] == b"070701":
        fields = [int(raw[pos + 6 + 8 * j:pos + 14 + 8 * j], 16) for j in range(13)]
        name_start = pos + 110
        name = raw[name_start:name_start + fields[11] - 1].decode().removeprefix("./")
        data_start = (name_start + fields[11] + 3) & ~3
        data = raw[data_start:data_start + fields[6]]
        pos = (data_start + fields[6] + 3) & ~3
        if name == "TRAILER!!!":
            return entries
        if not name or name in entries:
            raise SystemExit(f"Invalid duplicate/empty initramfs member: {name!r}")
        entries[name] = (fields[1], data, fields[9], fields[10])
    raise SystemExit("Unexpected CPIO archive termination")


def pack_newc(entries: dict[str, tuple[int, bytes, int, int]]) -> bytes:
    result = bytearray()
    for ino, (name, (mode, data, major, minor)) in enumerate(
        list(sorted(entries.items())) + [("TRAILER!!!", (0, b"", 0, 0))], 1
    ):
        encoded = name.encode() + b"\0"
        fields = (ino, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0,
                  len(data), 0, 0, major, minor, len(encoded), 0)
        result += b"070701" + "".join(f"{n:08x}" for n in fields).encode() + encoded
        result += b"\0" * (-len(result) % 4)
        result += data
        result += b"\0" * (-len(result) % 4)
    result += b"\0" * (-len(result) % 512)
    return bytes(result)


def add(entries: dict[str, tuple[int, bytes, int, int]], name: str,
        data: bytes = b"", mode: int = stat.S_IFREG | 0o644) -> None:
    parent = Path(name).parent
    while str(parent) != ".":
        entries.setdefault(parent.as_posix(), (stat.S_IFDIR | 0o755, b"", 0, 0))
        parent = parent.parent
    entries[name] = (mode, data, 0, 0)


def main() -> None:
    source = SOURCE.read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise SystemExit("The already booted panel-fixed diagnostic image changed")
    fields = list(struct.unpack_from("<10I", source, 8))
    kernel_size, _, ramdisk_size, _, second_size, _, _, page, version, _ = fields
    if source[:8] != b"ANDROID!" or (page, version, second_size) != (4096, 0, 0):
        raise SystemExit("Unexpected Android boot image layout")
    start = page + ((kernel_size + page - 1) // page) * page
    kernel = source[page:page + kernel_size]
    old_ramdisk = source[start:start + ramdisk_size]
    entries = parse_newc(gzip.decompress(old_ramdisk))
    add(entries, "init", (BASE / "diagnostics/init-pmos6167-overlay").read_bytes(),
        stat.S_IFREG | 0o755)
    add(entries, "bin/diag-console", b"""#!/bin/sh
echo 'POLARIS 6.16.7 RAM overlay candidate; storage is read-only'
echo 'To start Ubuntu: touch /run/start-ubuntu-overlay; exit'
cat /run/init.log
export PS1='polaris-6167-overlay# '
exec /bin/sh -i
""", stat.S_IFREG | 0o755)

    module_count = 0
    for path in sorted(MODULES.rglob("*")):
        rel = "lib/modules/6.16.7-sdm845/" + path.relative_to(MODULES).as_posix()
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            add(entries, rel, mode=stat.S_IFDIR | 0o755)
        elif stat.S_ISLNK(info.st_mode):
            add(entries, rel, os.readlink(path).encode(), stat.S_IFLNK | 0o777)
        elif stat.S_ISREG(info.st_mode):
            add(entries, rel, path.read_bytes(), stat.S_IFREG | (info.st_mode & 0o777))
            module_count += 1
        else:
            raise SystemExit(f"Unexpected module tree entry: {path}")
    compressed_overlay = (MODULES / "kernel/fs/overlayfs/overlay.ko.zst").read_bytes()
    overlay = subprocess.check_output(["zstd", "-dc"], input=compressed_overlay)
    add(entries, "lib/modules/6.16.7-sdm845/diag/overlay.ko", overlay)

    ramdisk = gzip.compress(pack_newc(entries), compresslevel=9, mtime=0)
    fields[2] = len(ramdisk)
    header = bytearray(source[:page])
    struct.pack_into("<10I", header, 8, *fields)
    digest = hashlib.sha1()
    for part in (kernel, ramdisk, b""):
        digest.update(part)
        digest.update(struct.pack("<I", len(part)))
    header[576:608] = digest.digest().ljust(32, b"\0")
    image = bytes(header) + kernel + b"\0" * (-len(kernel) % page)
    image += ramdisk + b"\0" * (-len(ramdisk) % page)
    if len(image) > 64 * 1024 * 1024:
        raise SystemExit("Candidate exceeds 64 MiB recovery image envelope")
    DEST.write_bytes(image)
    manifest = {
        "kernel_release": "6.16.7-sdm845",
        "kernel_source": SOURCE.name,
        "kernel_sha256": hashlib.sha256(kernel).hexdigest(),
        "module_files": module_count,
        "module_tree_sha256": hashlib.sha256(b"".join(
            hashlib.sha256(p.read_bytes()).digest() for p in sorted(MODULES.rglob("*")) if p.is_file()
        )).hexdigest(),
        "ramdisk_sha256": hashlib.sha256(ramdisk).hexdigest(),
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_bytes": len(image),
        "activation": "manual touch /run/start-ubuntu-overlay; exit",
        "rootfs": "userdata ext4 ro,noload with tmpfs overlay upper",
        "phone_partition_writes": False,
        "booted": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{DEST}: {len(image)} bytes SHA256 {manifest['image_sha256']}")


if __name__ == "__main__":
    main()
