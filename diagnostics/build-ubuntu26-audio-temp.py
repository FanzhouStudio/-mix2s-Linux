#!/usr/bin/env python3
"""Build a temporary Ubuntu boot image with the RAM-proven Polaris audio stack.

This starts from the byte-for-byte backup of the installed recovery image and
does not create an image for flashing. The existing Ubuntu userdata remains
untouched until the normal initramfs switch_root, and audio modules stay in the
initramfs rather than being copied to userdata.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import lzma
import runpy
import stat
import struct
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
ART = BASE / "artifacts"
SOURCE = ART / "polaris-ubuntu-26.04.1-recovery.img"
IMAGE = ART / "polaris-ubuntu-26.04.1-audio-temp-v1.img"
RAMDISK = ART / "initramfs-ubuntu-26.04.1-audio-temp-v1.cpio.gz"
DETAILS = ART / "ubuntu26-audio-temp-v1.json"
COMMON = runpy.run_path(str(BASE / "diagnostics/build-kali61-audio-diag.py"))


def modify_init(data: bytes, phases: dict[str, list[str]]) -> bytes:
    source = data.decode()
    map_needle = '    for descriptor in modemuw.jsn adspr.jsn cdspr.jsn; do\n        cp "$wifi_tools/$descriptor" "$mapdir/$descriptor"\n    done\n'
    map_addition = """    if [ -r /run/modem/image/adspua.jsn ]; then
        cp /run/modem/image/adspua.jsn "$mapdir/adspua.jsn"
        echo 'OEM audio service map staged before pd-mapper'
    fi
    if [ -r /run/vendor/firmware/tas2559_uCDSP.bin ]; then
        ln -sf /run/vendor/firmware/tas2559_uCDSP.bin /lib/firmware/tas2559_uCDSP.bin
    fi
"""
    if source.count(map_needle) != 1:
        raise SystemExit("Installed init map splice point changed")
    source = source.replace(map_needle, map_needle + map_addition)

    module_lines = [
        "load_audio_modules() {",
        "    audio_dir=/usr/lib/polaris-audio",
        "    echo 'waiting for mapped APR audio service' >/run/audio-probe.log",
        "    tries=0",
        "    while [ ! -e /sys/bus/aprbus/devices/aprsvc:apr-service:4:3 ] && [ \"$tries\" -lt 45 ]; do",
        "        sleep 1",
        "        tries=$((tries+1))",
        "    done",
        "    if [ ! -e /sys/bus/aprbus/devices/aprsvc:apr-service:4:3 ]; then",
        "        echo 'APR audio service absent; skipping modules' >>/run/audio-probe.log",
        "        return 0",
        "    fi",
    ]
    for phase, names in phases.items():
        module_lines.append(f"    echo 'phase {phase}' >>/run/audio-probe.log")
        for name in names:
            module_lines.extend([
                f"    echo 'loading {name}' >>/run/audio-probe.log",
                f"    if ! insmod \"$audio_dir/{name}.ko\" >>/run/audio-probe.log 2>&1; then",
                "        echo 'audio module load stopped on error' >>/run/audio-probe.log",
                "        return 0",
                "    fi",
            ])
    module_lines.extend([
        "    cat /proc/asound/cards >>/run/audio-probe.log",
        "}", "",
    ])
    marker = "echo 'POLARIS Ubuntu 26.04 persistent init started'"
    if source.count(marker) != 1:
        raise SystemExit("Installed init startup marker changed")
    source = source.replace(marker, "\n".join(module_lines) + marker)
    start = 'wait "$qcom_pid"\necho \'hardware initialization finished\''
    if source.count(start) != 1:
        raise SystemExit("Installed init audio start marker changed")
    source = source.replace(start, 'wait "$qcom_pid"\nload_audio_modules\necho \'hardware initialization finished\'')
    return source.encode()


def main() -> None:
    original = SOURCE.read_bytes()
    if hashlib.sha256(original).hexdigest() != "54740351bbd9eb5d6052ef4f61d46a78ba49042fd851364fd393d59bb2159c22":
        raise SystemExit("Installed recovery backup differs from known-good image")
    fields = list(struct.unpack_from("<10I", original, 8))
    kernel_size, _, ramdisk_size, _, second_size, _, _, page, version, _ = fields
    if original[:8] != b"ANDROID!" or page != 4096 or second_size or version:
        raise SystemExit("Unexpected boot image format")
    kernel = original[page:page + kernel_size]
    ramdisk_start = page + ((kernel_size + page - 1) // page) * page
    entries, highest_inode = COMMON["parse_cpio"](gzip.decompress(original[ramdisk_start:ramdisk_start + ramdisk_size]))
    by_name, deps = COMMON["module_catalog"]()
    phases = COMMON["ordered_phases"](by_name, deps)
    out = bytearray()
    present = set()
    modified = False
    for name, header, data in entries:
        present.add(name)
        if name == "init":
            data = modify_init(data, phases)
            header = header[:54] + f"{len(data):08x}".encode() + header[62:]
            modified = True
        out.extend(header)
        out.extend(name.encode() + b"\0")
        out.extend(b"\0" * (-len(out) % 4))
        out.extend(data)
        out.extend(b"\0" * (-len(out) % 4))
    if not modified:
        raise SystemExit("Installed recovery init missing")
    inode = highest_inode + 1
    audio_dir = "usr/lib/polaris-audio"
    if audio_dir not in present:
        COMMON["append_cpio"](out, audio_dir, stat.S_IFDIR | 0o755, b"", inode)
        inode += 1
    stage = ART / "kali61-audio-module-stage/lib/modules/6.1-sdm845"
    for name, path in by_name.items():
        data = lzma.decompress((stage / path).read_bytes())
        COMMON["append_cpio"](out, f"{audio_dir}/{name}.ko", stat.S_IFREG | 0o644, data, inode)
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
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_bytes": len(image),
        "ramdisk_bytes": len(compressed),
        "module_phases": phases,
        "changes": "OEM audio map and pre-desktop loading of RAM-only modules",
        "partition_flash": False,
    }, indent=2) + "\n")
    print(f"{IMAGE}: {len(image)} bytes SHA256 {hashlib.sha256(image).hexdigest()}")


if __name__ == "__main__":
    main()
