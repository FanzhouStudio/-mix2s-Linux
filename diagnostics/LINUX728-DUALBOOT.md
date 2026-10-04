# Polaris 7.2.8 boot + 6.1 recovery candidate

This is a **Linux/Linux switch on one Ubuntu userdata filesystem**. It does
not restore Android or create an Android/Ubuntu dual boot. The intended key
paths are normal Power → `boot` → 7.2.8, Volume Up + Power → `recovery` →
6.1, and Volume Down + Power → Fastboot.

The 7.2.8 candidate still hard-freezes on Clash Verge, including an offscreen
Xvfb launch. A bootable desktop and working peripheral probes do not make it
daily-use stable. Keep the working 6.1 recovery image unchanged.

## Device state before changing `boot`

On 2026-10-04 the phone reported:

| GPT partition | Device in 6.1 | Size | Live SHA-256 |
| --- | --- | ---: | --- |
| `boot` | `/dev/sde45` | 67,108,864 B | `f3cddc6de697588076dcd6775f4404360a00ab120304355a9a619412dcd50f7b` |
| `recovery` | `/dev/sda19` | 67,108,864 B | `90ef55acadbff3a2167cec88682b8e53904c4096cea309b7cf062b86091e7580` |
| `userdata` | `/dev/sda21` | 121,425,080,320 B | Ubuntu ext4, mounted RW under 6.1 |

The boot hash matches `diagnostics/backups/boot-live-20260928.img`.
The complete current recovery was copied to
`diagnostics/backups/recovery-live-20261004.img`; host size and SHA-256 match
the live recovery. These raw device backups are private host artifacts, not
GitHub release files.

## Candidate image

Build:

```sh
python3 diagnostics/build-linux728-readonly-diag.py \
  --after-attach --ubuntu-overlay --overlay-vendor \
  --integrated --integrated-auto --persistent-dualboot
```

Output: `artifacts/linux728-polaris-candidate/polaris-linux728-dualboot-persistent-candidate.img`,
22,077,440 bytes, SHA-256
`d75ee201d93ecb60b20739e8b2b7e5282383b1c806a877a463ba6983c5a9852d`.
The Android boot image v0 is below the 64 MiB `boot` partition size.
First temporary boot on 2026-10-05 reached the RAM diagnostic screen but
**failed to mount `/dev/sda21` read-write**: `mount: mounting /dev/sda21 on
/newroot failed: Invalid argument`. It has **not been flashed**. The kernel
log and mount cause must be diagnosed, then a revised image must pass this
acceptance sequence before any `boot` flash.
The serial kernel log identified the cause: `EXT4-fs (sda21): The kernel was
not built with CONFIG_QUOTA and CONFIG_QFMT_V2`. A read-only `ro,noload`
mount of the same partition succeeded and exposed the expected Ubuntu root.
The rebuilt kernel has both `CONFIG_QUOTA=y` and `CONFIG_QFMT_V2=y`; the new
image hash above has not been booted yet. The revised diagnostic screen also
shows storage kernel messages when root mounting fails.

Its initramfs mounts `vendor` and `modem` read-only and the already prepared
Ubuntu `userdata` ext4 read-write. It checks the Ubuntu root marker and
systemd before switching root. The 7.2.8-only kernel modules and audio
config are bind-mounted from RAM for this boot. The initramfs stages three
version-specific helpers, one systemd service, and a systemd generator on
the shared root. The service runs only when the 7.2.8 command line contains
`polaris.autostart=1`. The generator masks 6.1-specific startup services,
background apt timers, 1Panel services, and the QQ mount only while 7.2.8
is booted; it exits without masking them under the 6.1 recovery kernel.
Manual `apt` remains available. The root is persistent, so package and user
changes made in either kernel are visible to the other kernel.

## Acceptance sequence before flashing

1. Verify `fastboot getvar product` says `polaris`, bootloader is unlocked,
   and the boot image hash and size match the manifest.
2. Use **`fastboot boot`** with the candidate. Confirm 7.2.8, GNOME,
   touch, USB ACM, and `userdata` mounted read-write. Confirm 7.2.8 modules
   and generator masks are active, and no 6.1 modules load.
3. Reboot into the unchanged 6.1 recovery. Confirm GNOME, touch, USB,
   and normal 6.1 services still work on the same root.
4. Only after those checks, use `fastboot flash boot` with the exact tested
   image. Leave `recovery`, `userdata`, `dtbo`, and `vbmeta` untouched.
5. Verify normal boot reaches 7.2.8, then Volume Up + Power still reaches
   6.1. If normal boot fails, use 6.1 recovery and Fastboot to restore the
   raw `boot` backup.

Do not run Clash Verge, ChatGPT, QQ, or browser stress during the first
persistent boot. Their whole-device freeze remains unresolved on both
kernels.
