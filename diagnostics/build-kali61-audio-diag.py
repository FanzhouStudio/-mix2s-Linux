#!/usr/bin/env python3
"""Build a RAM-only Polaris audio probe from the already booted v8 image.

The image stages the OEM audio service map before pd-mapper starts. Audio
modules are present in RAM but are loaded only by an explicit serial command.
No userdata mount, partition write, driver rebind, or automatic audio probe is
added to the boot path.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import lzma
import stat
import struct
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
ART = BASE / "artifacts"
SOURCE = ART / "polaris-boot-kali61-diag-v8.img"
STAGE = ART / "kali61-audio-module-stage/lib/modules/6.1-sdm845"
DEPENDENCIES = ART / "kali61-audio-reference/modules.dep"
MANIFEST = ART / "kali61-audio-module-manifest.txt"
IMAGE = ART / "polaris-boot-kali61-audio-ramdiag-v1.img"
RAMDISK = ART / "initramfs-kali61-audio-ramdiag-v1.cpio.gz"
DETAILS = ART / "kali61-audio-ramdiag-v1.json"

PHASES = {
    "base": (
        "regmap-slimbus", "soundwire-bus", "soundwire-qcom",
        "slim-qcom-ngd-ctrl", "wcd934x", "gpio-wcd934x",
        "snd-soc-wcd-mbhc", "snd-soc-wcd934x", "snd-soc-tas2559",
        "snd-soc-rl6231", "snd-soc-rt5663",
    ),
    "dsp": (
        "snd-q6dsp-common", "q6core", "q6afe", "q6afe-dai",
        "q6afe-clocks", "q6adm", "q6routing", "q6asm", "q6asm-dai",
    ),
    "card": ("snd-soc-qcom-common", "snd-soc-sdm845"),
    "voice": (
        "q6voice-common", "q6cvp", "q6cvs", "q6mvm",
        "q6voice", "q6voice-dai",
    ),
}


def parse_cpio(raw: bytes) -> tuple[list[tuple[str, bytes, bytes]], int]:
    entries = []
    pos = 0
    highest_inode = 0
    while pos + 110 <= len(raw) and raw[pos:pos + 6] == b"070701":
        header = raw[pos:pos + 110]
        fields = [int(header[6 + 8 * i:14 + 8 * i], 16) for i in range(13)]
        name_end = pos + 110 + fields[11]
        name = raw[pos + 110:name_end - 1].decode()
        data_start = (name_end + 3) & ~3
        data_end = data_start + fields[6]
        highest_inode = max(highest_inode, fields[0])
        if name == "TRAILER!!!":
            return entries, highest_inode
        entries.append((name, header, raw[data_start:data_end]))
        pos = (data_end + 3) & ~3
    raise SystemExit("Source ramdisk has no valid newc trailer")


def append_cpio(out: bytearray, name: str, mode: int, data: bytes, inode: int) -> None:
    encoded = name.encode() + b"\0"
    fields = (inode, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0,
              len(data), 0, 0, 0, 0, len(encoded), 0)
    out.extend(b"070701" + b"".join(f"{value:08x}".encode() for value in fields))
    out.extend(encoded)
    out.extend(b"\0" * (-len(out) % 4))
    out.extend(data)
    out.extend(b"\0" * (-len(out) % 4))


def module_catalog() -> tuple[dict[str, str], dict[str, list[str]]]:
    paths = MANIFEST.read_text().splitlines()
    by_name = {Path(path).name.removesuffix(".ko.xz"): path for path in paths}
    if len(by_name) != 28:
        raise SystemExit(f"Expected 28 audio modules, found {len(by_name)}")
    deps = {}
    for line in DEPENDENCIES.read_text().splitlines():
        path, _, remainder = line.partition(":")
        name = Path(path).name.removesuffix(".ko.xz")
        if name in by_name:
            deps[name] = [Path(item).name.removesuffix(".ko.xz")
                          for item in remainder.split() if Path(item).name.removesuffix(".ko.xz") in by_name]
    if set(deps) != set(by_name):
        raise SystemExit("Audio module dependency list is incomplete")
    return by_name, deps


def ordered_phases(by_name: dict[str, str], deps: dict[str, list[str]]) -> dict[str, list[str]]:
    planned = set()
    result = {}
    for phase, names in PHASES.items():
        order = []
        visiting = set()

        def visit(name: str) -> None:
            if name in planned:
                return
            if name in visiting:
                raise SystemExit(f"Module dependency cycle at {name}")
            if name not in by_name:
                raise SystemExit(f"Missing audio module {name}")
            visiting.add(name)
            for dep in deps[name]:
                visit(dep)
            visiting.remove(name)
            planned.add(name)
            order.append(name)

        for name in names:
            visit(name)
        result[phase] = order
    if planned != set(by_name):
        raise SystemExit(f"Unassigned audio modules: {sorted(set(by_name) - planned)}")
    return result


def probe_script(phases: dict[str, list[str]]) -> bytes:
    lines = [
        "#!/bin/sh", "set -u", "phase=${1:-status}",
        "module_root=/lib/modules/6.1-sdm845/audio",
        "case \"$phase\" in",
        "  status)",
        "    echo 'Remote processors:'",
        "    for r in /sys/class/remoteproc/remoteproc*; do [ -r \"$r/name\" ] && echo \"$(cat \"$r/name\"): $(cat \"$r/state\")\"; done",
        "    echo 'ALSA cards:'; cat /proc/asound/cards",
        "    echo 'Audio firmware map:'; ls -l /lib/firmware/qcom/sdm845/polaris/adspua.jsn",
        "    echo 'APR devices:'; ls /sys/bus/aprbus/devices 2>/dev/null || true",
        "    echo 'Recent kernel audio messages:'",
        "    dmesg | grep -Ei 'apr|q6|slim|sound|audio|wcd|tas2559' | tail -n 35",
        "    exit 0 ;;",
    ]
    for phase, names in phases.items():
        lines.append(f"  {phase})")
        for name in names:
            lines.extend([
                f"    echo 'Loading {name}'",
                f"    if [ ! -d /sys/module/{name.replace('-', '_')} ]; then",
                f"      insmod \"$module_root/{name}.ko\" || exit 1",
                "    fi",
            ])
        lines.extend(["    cat /proc/asound/cards", "    exit 0 ;;"])
    lines.extend([
        "  *) echo 'Usage: audio-probe [status|base|dsp|card|voice]' >&2; exit 2 ;;",
        "esac", "",
    ])
    return "\n".join(lines).encode()


def main() -> None:
    original = SOURCE.read_bytes()
    if original[:8] != b"ANDROID!":
        raise SystemExit("Source is not an Android boot image")
    fields = list(struct.unpack_from("<10I", original, 8))
    kernel_size, _, ramdisk_size, _, second_size, _, _, page, version, _ = fields
    if page != 4096 or version != 0 or second_size != 0:
        raise SystemExit("Unexpected boot header layout")
    kernel = original[page:page + kernel_size]
    ramdisk_start = page + ((kernel_size + page - 1) // page) * page
    entries, highest_inode = parse_cpio(gzip.decompress(original[ramdisk_start:ramdisk_start + ramdisk_size]))
    by_name, deps = module_catalog()
    phases = ordered_phases(by_name, deps)
    insertion = """    if [ -r /run/modem/image/adspua.jsn ]; then
        cp /run/modem/image/adspua.jsn "$mapdir/adspua.jsn"
        echo 'OEM audio service map staged before pd-mapper'
    fi
    if [ -r /run/vendor/firmware/tas2559_uCDSP.bin ]; then
        ln -sf /run/vendor/firmware/tas2559_uCDSP.bin /lib/firmware/tas2559_uCDSP.bin
    fi
"""
    needle = "    for descriptor in modemuw.jsn adspr.jsn cdspr.jsn; do\n        cp \"$wifi_tools/$descriptor\" \"$mapdir/$descriptor\"\n    done\n"
    out = bytearray()
    existing = set()
    init_changed = False
    for name, header, data in entries:
        existing.add(name)
        if name == "init":
            source = data.decode()
            if source.count(needle) != 1:
                raise SystemExit("Source init audio-map splice point changed")
            data = source.replace(needle, needle + insertion).encode()
            header = header[:54] + f"{len(data):08x}".encode() + header[62:]
            init_changed = True
        encoded = name.encode() + b"\0"
        out.extend(header)
        out.extend(encoded)
        out.extend(b"\0" * (-len(out) % 4))
        out.extend(data)
        out.extend(b"\0" * (-len(out) % 4))
    if not init_changed:
        raise SystemExit("Source init missing")
    inode = highest_inode + 1
    for directory in ("usr/local", "usr/local/sbin", "lib/modules/6.1-sdm845/audio"):
        if directory not in existing:
            append_cpio(out, directory, stat.S_IFDIR | 0o755, b"", inode)
            inode += 1
    append_cpio(out, "usr/local/sbin/audio-probe", stat.S_IFREG | 0o755, probe_script(phases), inode)
    inode += 1
    for name, path in by_name.items():
        data = lzma.decompress((STAGE / path).read_bytes())
        append_cpio(out, f"lib/modules/6.1-sdm845/audio/{name}.ko", stat.S_IFREG | 0o644, data, inode)
        inode += 1
    append_cpio(out, "TRAILER!!!", 0, b"", inode)
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
        raise SystemExit("Audio probe image exceeds 64 MiB")
    IMAGE.write_bytes(image)
    DETAILS.write_text(json.dumps({
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_bytes": len(image),
        "ramdisk_bytes": len(compressed),
        "audio_module_phases": phases,
        "first_boot_action": "Read-only status only; no audio module autoload",
    }, indent=2) + "\n")
    print(f"{IMAGE}: {len(image)} bytes SHA256 {hashlib.sha256(image).hexdigest()}")
    print(f"{RAMDISK}: {len(compressed)} bytes")
    print("Audio modules load only with /usr/local/sbin/audio-probe phase")


if __name__ == "__main__":
    main()
