# Wi-Fi and cellular startup on Polaris 7.2.8

The safe 7.2.8 boot image starts GNOME, audio, rmtfs, tqftpserv, and pd-mapper while leaving the modem remote processor offline. With MSS offline, the bound ath10k SNOC driver does not create `wlan0`. Starting MSS brings up the WCN3990 firmware and creates `wlan0` without rebinding ath10k. ModemManager cannot create its QRTR QMI modem until IPA creates `rmnet_ipa0`.

`polaris728-network.service` performs one staged attempt after the safe hardware service. It waits for early boot to settle, loads RMNET and IPA before MSS, starts MSS, waits for the IPA and Wi-Fi interfaces, prepares the sole present USIM while ModemManager is stopped, then restarts ModemManager. It requests LTE preference at most twice and leaves subsequent network search to ModemManager. There is no modem reset loop, ath10k rebind loop, or automatic service restart. An `ExecCondition` limits the service to `7.2.8-polaris`; the 6.1 recovery kernel does not run it.

The SIM helper previously used `qmicli -p` (QMI proxy), which returned `endpoint hangup` on this QRTR device. It now uses direct QMI access only while ModemManager is stopped. It does not print or store the SIM AID, IMSI, or ICCID. It operates only when exactly one USIM candidate is present.

Validation on 2026-10-06: after an initial service correction and a second ordinary reboot, the service reached `active (exited)` with status 0. `wlan0` connected through NetworkManager; ModemManager created a QRTR modem, registered on China Telecom LTE, and the existing CTNET profile acquired an IPv4 address on `qmapmux0.0`. Small HTTP HEAD requests bound separately to `wlan0` and `qmapmux0.0` both returned `HTTP/1.1 301`. The modem took several minutes to register after the service finished. No MSS crash, ath10k firmware crash, RCU stall, or Oops appeared during this validation. This does not validate calls, SMS, or long-duration network stability.

Install into the shared Ubuntu rootfs:

```sh
sudo install -m 0755 diagnostics/polaris728-network-up /usr/local/sbin/polaris728-network-up
sudo install -m 0755 diagnostics/polaris-sim-prepare728.py /usr/local/sbin/polaris-sim-prepare728
sudo install -m 0644 diagnostics/polaris728-network.service /etc/systemd/system/polaris728-network.service
sudo systemctl daemon-reload
sudo systemctl enable polaris728-network.service
```

For rollback, run `sudo systemctl disable polaris728-network.service` and reboot. The existing 7.2.8 safe boot and 6.1 recovery remain available.
