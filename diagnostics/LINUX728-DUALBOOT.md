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
The rebuilt kernel has both `CONFIG_QUOTA=y` and `CONFIG_QFMT_V2=y`. Its
temporary boot on 2026-10-05 reached Ubuntu GNOME with `/dev/sda21` mounted
`rw,noatime`; USB ACM, Wi-Fi, GPU render node, and PipeWire speaker sink were
present. The 7.2.8 module and audio bind mounts were active, and the runtime
generator masked 6.1-specific services. This is a partial acceptance only:
touch, keyboard, and wake were then confirmed by the user. Reboot into the
unchanged 6.1 recovery reached GNOME and mounted the same `/dev/sda21` RW;
the 7.2.8 service was inactive and 6.1-specific units were not runtime-masked.

On 2026-10-05 `fastboot flash boot` accepted this exact image. The device
reported `product: polaris`, `unlocked: yes`, and a 64 MiB boot partition;
Fastboot reported both sending and writing `OKAY`. `recovery`, `userdata`,
`dtbo`, and `vbmeta` were not flashed. A subsequent ordinary reboot reached
Ubuntu's `graphical.target` under the installed 7.2.8 boot image. The user
confirmed the desktop and touch work after the normal boot. Screen keyboard
and wake worked in the preceding temporary boot. On 2026-10-05, after the
7.2.8 boot flash, Volume Up + Power again entered the 6.1 recovery desktop;
the user confirmed USB, and the serial console reported `6.1-sdm845`.

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

## 2026-10-05: application removal and compressed swap

The installed ChatGPT and QQ builds were portable SquashFS images, not APT
packages. Their mount services, launchers, icons, and images were removed from
the shared Ubuntu root. User settings under `/home/polaris` and downloaded
installers under `/home/polaris/下载` were left in place.

The running 7.2.8 kernel lacked built-in zram. Matching `zsmalloc.ko` and
`zram.ko` were built from the exact 7.2.8-polaris kernel configuration and
installed on the phone under
`/usr/local/lib/polaris-zram/7.2.8-polaris/`. Copies are in
`diagnostics/modules/7.2.8-polaris/`. The setup script and systemd unit in
this directory are installed as `/usr/local/sbin/polaris-zram-setup` and
`/etc/systemd/system/polaris-zram.service`. The service applies only to
`7.2.8-polaris`; the 6.1 recovery kernel does not load these modules.

The service creates a **6 GiB zram swap device** with LZ4, swap priority
100, `vm.swappiness=150`, and `vm.page-cluster=0`. This favors compressed RAM
swap without writing swap pages to userdata. Six GiB is the device's logical
capacity, not additional physical RAM. After a normal reboot, the phone
reported kernel `7.2.8-polaris`, `/dev/zram0` active at 6 GiB and priority
100, both sysctls at their configured values, `polaris-zram.service` enabled
and active, and GNOME with working touch. The phone root remained
`/dev/sda21` mounted read-write. No application stress test was run; zram does
not establish a fix for the known whole-device freezes.

## Public rootfs export attempt

An idle-I/O-priority, rate-limited, read-only tar of the live userdata stalled
the 7.2.8 kernel on CPU 5 with RCU warnings and blocked I/O tasks. The phone
required a forced restart. A slower repeat after booting 6.1 recovery also
stopped responding before the archive completed. Both partial archives were
discarded. Release v0.2.0-preview.1 instead derives its public rootfs from
the already audited v0.1.0 snapshot and adds the installed 7.2.8 zram files.
This is not an exact export of the current private userdata; new-device boot
of the public combination has not been verified.

## 2026-10-06: bounded boot handoff and safe hardware startup

The original 7.2.8 boot image sometimes remained on its diagnostic screen
despite mounting `/dev/sda21` at about 14 seconds. One observed boot did not
start GNOME until about 75 minutes later. Its initramfs unconditionally
`wait`ed for the USB diagnostic shell supervisor before `switch_root`.
The revised initramfs records the diagnostic shell PID, stops the workers,
and proceeds without an unbounded wait. In a temporary boot, it mounted
userdata at 13.83 seconds, moved the virtual filesystems at 14.89 seconds,
and reached GNOME in about a minute. The same handoff times were observed
after flashing the revised image to `boot` and rebooting normally.

Automatic full hardware bringup caused repeated modem firmware crashes and
`ath10k` errors. During one temporary boot, the forced Wi-Fi unbind/rebind
left NetworkManager, the hardware service, and udev workers in D state;
17 tasks were blocked and the load average exceeded 17. The safer default
starts the Qualcomm firmware servers and audio DSP but does not explicitly
start the modem, configure cellular service, or force a Wi-Fi driver rebind.
The earlier full bringup remains gated behind `polaris.hardware=full` in
the kernel command line. The safe candidate showed zero D-state tasks and
low load after seven minutes; the user confirmed GNOME, touch, and screen
keyboard. It was flashed only to `boot` after that temporary run. A normal
reboot then reached the 7.2.8 desktop with the same quick initramfs handoff;
`recovery` and userdata were not flashed. Wi-Fi and cellular may be absent
in this safe mode. Long-term stability and the cause of 6.1's reported
post-desktop power-off/reboot are still under investigation.
