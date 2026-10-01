#!/usr/bin/env python3
"""Build a temporary, read-only Polaris diagnostic boot from signed pmos inputs.

No flashing or device access. Uses the matching upstream package DTB and modules.
"""
from pathlib import Path
import argparse
import base64
import gzip
import hashlib
import io
import json
import stat
import struct
import subprocess
import tarfile

BASE = Path(__file__).resolve().parent.parent
ART = BASE / "artifacts"
PMOS = ART / "pmos6167"
RELEASE = "6.16.7-sdm845"
parser = argparse.ArgumentParser()
parser.add_argument("--revision", type=int, choices=(1, 2), default=1)
revision = parser.parse_args().revision

# Verify signed repository index -> package control checksum -> data hash.
subprocess.run([
    "openssl", "dgst", "-sha1", "-verify", str(ART / "pmos-build.rsa.pub"),
    "-signature", str(ART / "pmos-index.signature"),
    str(ART / "pmos-index-member2.gz"),
], check=True)
with tarfile.open(fileobj=io.BytesIO(gzip.decompress((ART / "pmos-index-member2.gz").read_bytes()))) as tf:
    index = tf.extractfile("APKINDEX").read().decode()
records = [dict(line.split(":", 1) for line in rec.splitlines() if ":" in line) for rec in index.split("\n\n")]
record = next(r for r in records if r.get("P") == "linux-postmarketos-qcom-sdm845" and r.get("V") == "6.16.7-r3")
control = (ART / "pmos-kernel-member2.gz").read_bytes()
if record["C"] != "Q1" + base64.b64encode(hashlib.sha1(control).digest()).decode():
    raise SystemExit("Signed repository package checksum mismatch")
with tarfile.open(fileobj=io.BytesIO(gzip.decompress(control))) as tf:
    info = tf.extractfile(".PKGINFO").read().decode()
datahash = next(line.split(" = ", 1)[1] for line in info.splitlines() if line.startswith("datahash = "))
package_data = (ART / "pmos-kernel-member3.gz").read_bytes()
if hashlib.sha256(package_data).hexdigest() != datahash:
    raise SystemExit("Package data checksum mismatch")
with tarfile.open(fileobj=io.BytesIO(gzip.decompress(package_data))) as tf:
    trusted = {m.name: tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}

kernel_gzip = trusted["boot/vmlinuz"]
dtb = trusted["boot/dtbs/qcom/sdm845-xiaomi-polaris.dtb"]
image_raw = gzip.decompress(kernel_gzip)
if image_raw[56:60] != b"ARM\x64" or struct.unpack_from(">I", dtb)[0] != 0xd00dfeed:
    raise SystemExit("Unexpected ARM64 kernel or DTB format")
# The packaged DTB is already USB peripheral/high-speed; do not mix the Kali DTB.
kernel = kernel_gzip + dtb
entries = {}

def add(name, data=b"", mode=stat.S_IFREG | 0o644, major=0, minor=0):
    parent = Path(name).parent
    while str(parent) != ".":
        entries.setdefault(parent.as_posix(), (stat.S_IFDIR | 0o755, b"", 0, 0))
        parent = parent.parent
    entries[name] = (mode, data, major, minor)

for directory in ("bin", "sbin", "usr/bin", "usr/sbin", "proc", "sys", "dev", "run", "tmp", "etc"):
    add(directory, mode=stat.S_IFDIR | 0o755)
add("bin/busybox", (PMOS / "original-busybox").read_bytes(), stat.S_IFREG | 0o755)
add("bin/sh", b"busybox", stat.S_IFLNK | 0o777)
add("init", (BASE / "diagnostics/init-pmos6167-diag").read_bytes(), stat.S_IFREG | 0o755)
add("bin/diag-console", b"""#!/bin/sh
echo 'POLARIS 6.16.7: root shell; storage is read-only'
uname -a
cat /run/init.log
export PS1='polaris-6167-diag# '
exec /bin/sh -i
""", stat.S_IFREG | 0o755)
for name, major, minor in (("console", 5, 1), ("null", 1, 3), ("tty", 5, 0), ("tty1", 4, 1)):
    add("dev/" + name, mode=stat.S_IFCHR | 0o600, major=major, minor=minor)
for name, location in (
    ("gpi", "drivers/dma/qcom"), ("rmi_core", "drivers/input/rmi4"), ("rmi_i2c", "drivers/input/rmi4")
):
    member = f"lib/modules/{RELEASE}/kernel/{location}/{name}.ko.zst"
    module = subprocess.check_output(["zstd", "-dc"], input=trusted[member])
    add(f"lib/modules/{RELEASE}/diag/{name}.ko", module)

# Use only the two GPU microcode files from the already booted diagnostic image.
old = gzip.decompress((ART / "initramfs-kali61-diag-v8.cpio.gz").read_bytes())
wanted = {"lib/firmware/qcom/a630_sqe.fw", "lib/firmware/qcom/a630_gmu.bin"}
pos = 0
while old[pos:pos+6] == b"070701":
    fields = [int(old[pos+6+8*j:pos+14+8*j], 16) for j in range(13)]
    name = old[pos+110:pos+110+fields[11]-1].decode().removeprefix("./")
    start = (pos+110+fields[11]+3) & ~3
    if name in wanted:
        add(name, old[start:start+fields[6]])
        wanted.remove(name)
    pos = (start+fields[6]+3) & ~3
    if name == "TRAILER!!!":
        break
if wanted:
    raise SystemExit(f"Missing firmware: {wanted}")

# The v1 image looked for this OEM file only after mounting vendor.  On the
# installed 6.1 kernel, the first GPU probe precedes that mount and reports a
# missing zap shader.  Stage a byte-verified copy in RAM for the v2 diagnostic.
if revision >= 2:
    zap = (ART / "firmware/polaris/a630_zap.mbn").read_bytes()
    zap_hash = hashlib.sha256(zap).hexdigest()
    if len(zap) != 14256 or zap_hash != "c0a830808c7ae886e5a5b6dec48afb9c9805d0579d9cac498ebc36b8b06bedde":
        raise SystemExit("OEM Polaris a630_zap.mbn differs from the verified vendor file")
    add("lib/firmware/qcom/sdm845/polaris/a630_zap.mbn", zap)

archive = bytearray()
for ino, (name, (mode, data, major, minor)) in enumerate(
    sorted(entries.items()) + [("TRAILER!!!", (0, b"", 0, 0))], 1
):
    encoded = name.encode() + b"\0"
    fields = (ino, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0, len(data), 0, 0, major, minor, len(encoded), 0)
    archive += b"070701" + "".join(f"{v:08x}" for v in fields).encode() + encoded
    archive += b"\0" * (-len(archive) % 4)
    archive += data
    archive += b"\0" * (-len(archive) % 4)
archive += b"\0" * (-len(archive) % 512)
ramdisk = gzip.compress(archive, compresslevel=9, mtime=0)

# Keep the known bootloader-compatible header v0 addresses and page size.
reference = (ART / "polaris-ubuntu-26.04.1-recovery.img").read_bytes()
ks, ka, rs, ra, ss, sa, tags, page, version, osver = struct.unpack_from("<10I", reference, 8)
if reference[:8] != b"ANDROID!" or (page, version, ss) != (4096, 0, 0):
    raise SystemExit("Unexpected reference Android boot header")
cmdline = b"console=tty0 loglevel=4 panic=0 rdinit=/init mobile.qcomsoc=qcom/sdm845 mobile.vendor=xiaomi mobile.model=polaris"
header = bytearray(page)
header[:8] = b"ANDROID!"
struct.pack_into("<10I", header, 8, len(kernel), ka, len(ramdisk), ra, 0, 0, tags, page, 0, osver)
header[64:576] = cmdline.ljust(512, b"\0")
digest = hashlib.sha1()
for part in (kernel, ramdisk, b""):
    digest.update(part)
    digest.update(struct.pack("<I", len(part)))
header[576:608] = digest.digest().ljust(32, b"\0")
boot = bytes(header) + kernel + b"\0" * (-len(kernel) % page) + ramdisk + b"\0" * (-len(ramdisk) % page)
output = ART / f"polaris-boot-pmos6167-readonly-diag-v{revision}.img"
ramdisk_output = ART / f"initramfs-pmos6167-readonly-diag-v{revision}.cpio.gz"
output.write_bytes(boot)
ramdisk_output.write_bytes(ramdisk)
manifest = {
    "revision": revision,
    "kernel_release": RELEASE, "repository_version": "6.16.7-r3",
    "trust": "signed official APKINDEX -> control SHA1 -> data SHA256",
    "package_data_sha256": datahash,
    "kernel_sha256": hashlib.sha256(kernel_gzip).hexdigest(),
    "dtb_sha256": hashlib.sha256(dtb).hexdigest(),
    "image": output.name, "image_size": len(boot), "image_sha256": hashlib.sha256(boot).hexdigest(),
    "ramdisk_size": len(ramdisk), "booted": False,
    "purpose": "temporary read-only RAM diagnostic boot; no Ubuntu switch_root",
}
if revision >= 2:
    manifest["early_gpu_zap_sha256"] = zap_hash
manifest_output = ART / ("pmos6167-diag-manifest.json" if revision == 1 else "pmos6167-diag-v2-manifest.json")
manifest_output.write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
