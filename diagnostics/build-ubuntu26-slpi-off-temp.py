#!/usr/bin/env python3
"""Disable only the SLPI DT node in a host-built temporary recovery image."""
import hashlib
import json
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / 'artifacts'
SOURCE = ART / 'polaris-ubuntu-26.04.1-audio-recovery-v1.img'
EXPECTED = '28a3b429917142bceb985139640e72be9ee1e76926852c947f8ec3179b33ddc3'
TARGET = '/soc@0/remoteproc@5c00000'


def properties(tree, strings):
    pos, stack, result, locations = 0, [], {}, {}
    while pos < len(tree):
        start = pos
        token = struct.unpack_from('>I', tree, pos)[0]
        pos += 4
        if token == 1:
            end = tree.index(b'\0', pos)
            stack.append(tree[pos:end].decode())
            pos = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, offset = struct.unpack_from('>2I', tree, pos)
            pos += 8
            name = strings[offset:strings.index(b'\0', offset)].decode()
            key = ('/'.join(stack), name)
            if key in result:
                raise ValueError('Duplicate property')
            result[key] = tree[pos:pos + length]
            pos = (pos + length + 3) & ~3
            locations[key] = (start, pos, offset)
        elif token == 9:
            return result, locations
        elif token != 4:
            raise ValueError(f'Unexpected FDT token {token}')
    raise ValueError('Missing FDT end')


def main():
    original = SOURCE.read_bytes()
    if hashlib.sha256(original).hexdigest() != EXPECTED:
        raise SystemExit('Installed recovery source checksum mismatch')
    fields = list(struct.unpack_from('<10I', original, 8))
    ks, _, rs, _, ss, _, _, page, version, _ = fields
    if original[:8] != b'ANDROID!' or (page, version, ss) != (4096, 0, 0):
        raise SystemExit('Unexpected boot header')
    payload = original[page:page + ks]
    decoder = zlib.decompressobj(31)
    decoder.decompress(payload)
    dtb = decoder.unused_data
    if not decoder.eof or dtb[:4] != b'\xd0\x0d\xfe\xed':
        raise SystemExit('Missing appended DTB')
    h = list(struct.unpack_from('>10I', dtb))
    if h[1] != len(dtb) or not (h[4] < h[2] < h[3]):
        raise SystemExit('Unexpected DTB layout')
    tree = dtb[h[2]:h[2] + h[9]]
    strings = dtb[h[3]:h[3] + h[8]]
    before, locations = properties(tree, strings)
    if before.get((TARGET, 'compatible')) != b'qcom,sdm845-slpi-pas\0':
        raise SystemExit('SLPI identity mismatch')
    if before.get((TARGET, 'firmware-name')) != b'qcom/sdm845/polaris/slpi.mbn\0':
        raise SystemExit('SLPI firmware path mismatch')
    key = (TARGET, 'status')
    if before.get(key) != b'okay\0':
        raise SystemExit('SLPI status is not the expected okay')
    start, end, nameoff = locations[key]
    value = b'disabled\0'
    replacement = struct.pack('>3I', 3, len(value), nameoff) + value
    replacement += b'\0' * (-len(value) % 4)
    changed_tree = tree[:start] + replacement + tree[end:]
    after, _ = properties(changed_tree, strings)
    expected = dict(before)
    expected[key] = value
    if after != expected:
        raise SystemExit('Unintended DTB property change')
    delta = len(changed_tree) - len(tree)
    changed_dtb = bytearray(dtb[:h[2]] + changed_tree + dtb[h[2] + h[9]:])
    h[1] += delta
    h[3] += delta
    h[9] += delta
    struct.pack_into('>10I', changed_dtb, 0, *h)
    kernel = payload[:-len(dtb)] + changed_dtb
    ramdisk_start = page + ((ks + page - 1) // page) * page
    ramdisk = original[ramdisk_start:ramdisk_start + rs]
    header = bytearray(original[:page])
    fields[0] = len(kernel)
    struct.pack_into('<10I', header, 8, *fields)
    digest = hashlib.sha1()
    for part in (kernel, ramdisk, b''):
        digest.update(part)
        digest.update(struct.pack('<I', len(part)))
    header[576:608] = digest.digest().ljust(32, b'\0')
    image = bytes(header) + kernel + b'\0' * (-len(kernel) % page)
    image += ramdisk + b'\0' * (-len(ramdisk) % page)
    output = ART / 'polaris-ubuntu-26.04.1-slpi-off-temp-v1.img'
    output.write_bytes(image)
    (ART / 'polaris-slpi-off-temp-v1.dtb').write_bytes(changed_dtb)
    manifest = dict(source_sha256=EXPECTED, image_sha256=hashlib.sha256(image).hexdigest(),
                    image_bytes=len(image), dtb_node=TARGET, status='disabled',
                    kernel_code_unchanged=True, ramdisk_unchanged=True,
                    booted=False, phone_partition_writes=False)
    (ART / 'polaris-slpi-off-temp-v1.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
