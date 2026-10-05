# 7.2.8 display wake recovery

On the Mi MIX 2S, some blanking transitions log `msm_dsi ... wait for video done timed out` and DCS `SET_DISPLAY_OFF` / `ENTER_SLEEP_MODE` errors. The DRM debug state then shows `crtc-0 active=0` while Mutter still reports `PowerSaveMode=0`. The kernel, USB serial, and GNOME process may remain responsive even though the user sees a frozen screen and touch appears ineffective.

The `polaris728-touch-wake.service` starts the existing S3330 raw double-tap listener on 7.2.8; the 6.1 service remains masked by the 7.2.8 generator. The GNOME extension now sends the power-on request even if Mutter already reports mode 0. `polaris728-display-recover.service` is a fallback: after a new touchscreen or volume-key interrupt, it reasserts mode 0 only if DRM says the CRTC is inactive and Mutter says it should be on. It does not read touch coordinates or key values. Both services have a kernel-version condition so they do not run under the 6.1 recovery kernel.

Live validation on 2026-10-06: the raw listener counted the double tap, the extension change made double-tap wake work, and a temporary copy of the recovery program reactivated an inactive CRTC without restarting GNOME or the phone. The permanent services were then installed and observed active. A full reboot validation is still pending.

This is a recovery path for a display state mismatch. It does not establish that the DSI timeout is fixed, nor does it resolve previously captured RCU/CPU stalls during some applications. The 7.2.8 safe image still omits Wi-Fi and cellular startup.

Install in the shared Ubuntu rootfs (from a 7.2.8 session):

```sh
sudo install -m 0755 diagnostics/polaris728-display-recover.py /usr/local/sbin/polaris728-display-recover
sudo install -m 0644 diagnostics/polaris728-display-recover.service diagnostics/polaris728-touch-wake.service /etc/systemd/system/
install -Dm 0644 diagnostics/polaris-touch-controls@local/extension.js ~/.local/share/gnome-shell/extensions/polaris-touch-controls@local/extension.js
sudo systemctl daemon-reload
sudo systemctl enable --now polaris728-display-recover.service polaris728-touch-wake.service
```

To disable the fallback, run `sudo systemctl disable --now polaris728-display-recover.service`. The manual recovery used during diagnosis was a user-session D-Bus write of Mutter `PowerSaveMode=0`.
