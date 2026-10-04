# Polaris Linux 7.2.8 integrated RAM candidate

This candidate keeps the existing 6.1 recovery intact. It combines the
working 7.2.8 XBL framebuffer and delayed DRM path with Polaris sound card
device-tree wiring, the downstream TAS2559 speaker driver, built-in ASoC,
ath10k SNOC, remoteproc, Qualcomm DRM and loadable PDC reset, RMTFS, RMNET and IPA
drivers. Its Ubuntu root is mounted read-only with a RAM overlay.

Build on Ubuntu-Max:

```sh
./diagnostics/build-linux728-integrated.sh
python3 diagnostics/build-linux728-readonly-diag.py \
  --after-attach --ubuntu-overlay --overlay-vendor --integrated
```

The resulting `artifacts/linux728-polaris-candidate/polaris-linux728-integrated-overlay-diag.img`
is for `fastboot boot` only. It is not a recovery or boot partition image to
flash persistently. Do not install it until display, input, network, audio,
cellular data, and the application lockup case have been checked on the phone.

After the diagnostic console appears, mount Ubuntu into the RAM overlay by
creating `/run/start-ubuntu-overlay` from the USB ACM shell. The initramfs
mounts vendor, modem, and userdata read-only, symlinks firmware in the RAM
upper layer, and masks the old 6.1 services. Nothing in this boot path writes
to a phone partition.

Once Ubuntu is up, bring up one group at a time from the serial console:

```sh
sudo polaris-integrated-bringup status
sudo polaris-integrated-bringup core
sudo polaris-integrated-bringup audio
sudo polaris-integrated-bringup cellular
```

## Automatic boot candidate

Build the separate automatic candidate with:

```sh
python3 diagnostics/build-linux728-readonly-diag.py \
  --after-attach --ubuntu-overlay --overlay-vendor --integrated --integrated-auto
```

`artifacts/linux728-polaris-candidate/polaris-linux728-integrated-auto-overlay-diag.img`
waits for the diagnostic USB gadget, then automatically mounts vendor, modem
and userdata read-only, creates a RAM upper layer, and starts Ubuntu. A
systemd one-shot service brings up the modem services, sound and cellular
data in sequence. This image remains **fastboot boot only**. It is a cold-boot
workflow check before creating a recovery image that mounts userdata
read-write. Early mount failures leave the initramfs diagnostic shell
available. Power cycling returns to the installed 6.1 recovery.

`core` loads the RMTFS and PDC reset modules, starts the Qualcomm firmware
servers and modem remote processor, allowing deferred Wi-Fi probes. `audio`
loads TAS2559 and starts ADSP. `cellular` loads RMNET and IPA for packet data. This does
not include voice calling or SMS: downstream q6voice and call audio have not
been ported. A successful build is not evidence that these functions work on
the device; record actual probe logs and user-visible results before enabling
automatic services or persistent boot.

## First RAM boot on 2026-10-04

The first integrated image booted Ubuntu 26.04, GNOME and touch. Mesa reported
`EGL driver name: msm` and `OpenGL renderer: FD630`. Bluetooth HCI setup
completed. RMTFS, TFTP and PD mapper ran from the existing rootfs; the modem
remote processor reached `running`. Loading IPA created `rmnet_ipa0`, but
ModemManager did not yet find a modem because RMNET was missing from that image.
TAS2559 loaded its 96,514-byte firmware. There was no ALSA card because the
7.2.8 Polaris DTB still had ADSP disabled. Wi-Fi firmware registered WLFW
service 69, but ath10k rejected the host capability request and no `wlan0`
appeared. The working 6.1 live device tree has
`qcom,snoc-host-cap-skip-quirk`; the first 7.2.8 image did not.

## Second RAM boot on 2026-10-04

The second candidate booted GNOME with working touch and keyboard. The
`qcom,snoc-host-cap-skip-quirk` let ath10k register `wlan0`; NetworkManager
connected to the 2.4 GHz access point and acquired `192.168.3.170/24`.
Mesa's Wayland EGL driver was `msm`, and its renderer was `FD630`. Bluetooth
HCI firmware setup completed, though pairing has not been tried.

ADSP reached `running`. The TAS2559 module loaded its speaker firmware, ALSA
registered `Xiaomi Mi Mix2S` card 0, and PipeWire exposed a built-in speaker
sink. The first short PipeWire test was inaudible. Direct playback through
`hw:Mix2S,0` with 48 kHz stereo S16LE was audible, confirming that the
7.2.8 kernel, ADSP and speaker amplifier can produce sound. The existing WirePlumber
rule matched the old 6.1 node name only, so this image now stages a rule that
also matches the 7.2.8 `alsa_output.platform-sound` node and forces S16LE
without mmap. Audible output through the default PipeWire sink still requires
confirmation; initial follow-up tests used reduced stream and sink volumes.

QMI found the sole present China Telecom USIM. Activating the primary GW
provisioning session, then restarting ModemManager, registered on LTE. The
saved `中国电信 CTNET` NetworkManager profile connected through `qmapmux0.0`;
a TCP connection bound to that interface succeeded. The diagnostic bringup
now packages a 7.2.8-scoped copy of the single-SIM preparation helper and
requests LTE preference after ModemManager returns. It leaves multi-SIM or
missing-SIM cases unchanged.

These checks establish device detection and cellular packet data. They do
not establish that the kernel is stable under heavy applications. Previous
6.1 and 7.2.8 boots froze when opening Clash, ChatGPT or QQ. Keep using
`fastboot boot` and preserve the 6.1 recovery until that case is resolved.

## First automatic read-only boot on 2026-10-04

The automatic RAM-overlay image entered Ubuntu without serial intervention.
GNOME and touch worked, the rootfs remained mounted `ro,norecovery`, the
7.2.8 hardware service completed, and ALSA, Bluetooth HCI and FD630 render
node appeared. The early modem start raced ModemManager and caused two modem
remoteproc recoveries. During that recovery, ath10k's first firmware probe
timed out, leaving no `wlan0`. Once the modem settled, a single platform
driver unbind/bind created `wlan0`, which connected to the saved 2.4 GHz
network. The sole present SIM was provisioned automatically, but the initial
LTE mode request ran before ModemManager exposed a modem. Repeating the LTE
mode request later registered on China Telecom and connected CTNET. The
phone stayed responsive for more than six minutes with no RCU stall in the
live kernel log; this is not an application stress result.

The next automatic candidate stops ModemManager before launching Qualcomm
firmware services, waits for a modem before setting LTE preference, and
retries Wi-Fi once only if the first asynchronous probe did not create
`wlan0`. It remains a RAM-only `fastboot boot` candidate.

On the second automatic boot, Wi-Fi initialized and connected on its first
probe, with no modem fatal recovery. GNOME, touch and the screen keyboard
worked. The SIM preparation and initial LTE mode setting succeeded, but
registration alternated between `idle` and `searching`. Repeating that mode
request after roughly two minutes registered on China Telecom and connected
CTNET. The next candidate waits for registration and retries the same mode
request once after the modem has settled. The panel still logs DSI command
timeouts when turning the display off; wake behavior needs separate checking.

The user confirmed that the second automatic boot reached GNOME with working
touch and screen keyboard, and that the volume-key screen wake was responsive.
At about 11 minutes of uptime, opening and operating Clash Verge again froze
the entire phone. The USB ACM gadget remained enumerated on Ubuntu-Max, but
the serial shell stopped answering; the last serial output preceded the
reported freeze. Wi-Fi did not answer a ping. Before the freeze, the rootfs
and firmware partitions were still read-only, both Wi-Fi and China Telecom
data were connected, and the PipeWire built-in speaker sink existed. The
kernel log showed DSI display-off timeouts but no RCU stall, GPU/SMMU fault,
or storage error. There is no post-freeze CPU backtrace, so this trial does
not identify the subsystem that locked up. The revised candidate with one
delayed LTE retry was built after this boot and remains untested. Keep the
installed 6.1 recovery; do not flash this 7.2.8 RAM-overlay image.

## Third automatic read-only boot on 2026-10-04

The image with one delayed LTE registration retry booted GNOME with working
touch. Its first ath10k firmware probe failed, but the service's single
unbind/bind retry created `wlan0` and NetworkManager reconnected to the saved
2.4 GHz network. ModemManager later reached `home` registration and the saved
China Telecom CTNET connection became active without a manual command. The
bringup service exited successfully.

To separate the proxy engine from its GUI, `verge-mihomo` ran for 15 seconds
with a temporary local-only configuration and exited when the diagnostic
timeout sent a signal. A second headless run served 100/100 HTTP requests
through its loopback proxy to a loopback HTTP server; the core remained alive
and the desktop stayed responsive. This checks basic core startup and local
proxy traffic only. It does not cover the user's actual proxy configuration,
remote network traffic, or the Clash Verge graphical interface.

For a GUI control, a GTK3 window was shown through Xwayland with the GNOME
session's X authority, and the user confirmed it was visible. WebKitGTK's
`MiniBrowser` then displayed a local HTML page through the same X11 session
with `WEBKIT_DMABUF_RENDERER_FORCE_SHM=1`; the user confirmed it was visible
and the phone remained responsive for 15 seconds. These are short, simple
window tests, not a WebKit stress test.

Launching Clash Verge with the same X11 session and shared-memory WebKit
renderer initially showed its window, but the user then reported another
whole-phone freeze without interacting with it. The 25-second `timeout`
wrapper never returned to the serial shell. The USB ACM gadget remained
enumerated while the serial shell stopped responding, and its last output was
the launch command; no kernel backtrace was emitted. A host-only copy of the
serial transcript is in
`diagnostics/logs/serial-linux728-clash-x11-freeze-20261004.log`. This result
rules out a simple Xwayland launch failure and a failure of the basic Mihomo
proxy path, but it does not identify which Clash/WebKit activity or kernel
subsystem locks the SoC. The recovery partition must remain on 6.1.

The next discriminating test should run the same Clash binary against a
software-only offscreen X server such as Xvfb while the GNOME display remains
idle. If that still freezes the phone, the visible scanout/compositor path is
not required for reproduction. If it remains responsive, compare it with the
already-failing visible Xwayland launch. Keep the test in a RAM boot and bound
its runtime; a bound cannot terminate a process after a whole-SoC lockup.

## Offscreen diagnostic candidate (first RAM boot)

`diagnostics/build-xvfb-offscreen-bundle.sh` downloads Ubuntu arm64 `xvfb`
and `libunwind8`, checks their package SHA-256 hashes, and produces a
reproducible `xvfb-runtime-arm64.tgz`. Build a separate RAM-only image with:

```sh
python3 diagnostics/build-linux728-readonly-diag.py \
  --after-attach --ubuntu-overlay --overlay-vendor \
  --integrated --integrated-auto --offscreen-xvfb
```

The output is
`artifacts/linux728-polaris-candidate/polaris-linux728-integrated-auto-offscreen-diag.img`.
The builder verifies the Xvfb bundle hash and stages it in `/tmp` on the
phone before `switch_root`; it is never installed to userdata. The first
2026-10-04 build was 23,117,824 bytes with SHA-256
`4e9238e21bdd4aa4be738cfd8620215a1ffc549f71aee11d99a3ac25c12c37c1`.
Use only `fastboot boot`. After confirming GNOME, Wi-Fi and serial, unpack
the bundle inside `/tmp` and launch Clash on a non-networked Xvfb display
with software GL. This isolates the app and WebKit from the physical DRM
scanout path; it may still freeze the phone, so preserve the 6.1 recovery.

On 2026-10-04, `fastboot boot` accepted this image. The phone displayed the
7.2.8 RAM overlay diagnostic screen with `ACM: READY` and
`ACM bound: a600000.usb`, but the Ubuntu-Max guest saw no new USB device and
VMware reported that it could not recognize the device. The photographed
screen at approximately 77 seconds uptime still said `UBUNTU NOT STARTED`;
its final visible kernel message was `dwc3 a600000.usb: remote wakeup not
configured`. No Xvfb or Clash process has been launched in this boot.
The user's later screen state was still pending when this observation was
recorded. Do not treat the visible `ACM: READY` as proof of host enumeration.
The next build keeps screen diagnostics active through a failed Ubuntu overlay
attempt and writes its errors to `/run/init.log` for display, instead of
redirecting them to an unenumerated USB serial port. Its SHA-256 is
`1820f15afd40b23e414599b4de31ac47904aa1c0a849100d36e79ff28f4e0e95`.

This revised image booted Ubuntu 26.04 on 2026-10-04. USB ACM enumerated,
`7.2.8-polaris` reached GDM, and the physical userdata mount was
`/dev/sda21 ro,relatime,norecovery` under a writable RAM overlay. The Xvfb
bundle hash matched `789b83801919893235c79ac927c6df8621db7246ac169b50e470268d590a6616`.
Xvfb `:90` started from `/tmp`, and a five-second GTK3 control window on
`:90` opened and closed normally. After hardware bringup finished, Clash
Verge was launched on `DISPLAY=:90` with X11, software GL, and shared-memory
WebKit rendering. Clash, WebKitWebProcess, and the Verge Mihomo sidecar all
started. The serial console then reported an RCU stall involving CPU 5 at
approximately 266 seconds uptime and stopped responding shortly afterward;
the 30-second `timeout` did not restore command response. A USB ACM device
remained enumerated on the host. A serial BREAK followed by SysRq `l` did
not produce an additional backtrace. This shows that hiding the Clash window
from the physical display is insufficient to avoid the freeze. It does not
identify which of Clash, WebKit, its sidecar, or their kernel interactions
caused the stall. Host capture: `diagnostics/logs/serial-linux728-integrated-reboot-20261004.log`.
