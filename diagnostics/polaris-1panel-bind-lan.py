#!/usr/bin/python3
"""Bind the installed 1Panel core only to this Polaris Wi-Fi LAN."""

import ipaddress
import json
import sqlite3
import subprocess
import sys

LAN = ipaddress.ip_network("192.168.3.0/24")
records = json.loads(
    subprocess.check_output(["ip", "-4", "-j", "addr", "show", "dev", "wlan0"])
)
addresses = [
    item["local"]
    for record in records
    for item in record.get("addr_info", [])
    if item.get("family") == "inet"
]
address = next((item for item in addresses if ipaddress.ip_address(item) in LAN), None)
if address is None:
    sys.exit("1Panel LAN bind: Wi-Fi has no address in 192.168.3.0/24")

with sqlite3.connect("/opt/1panel/db/core.db", timeout=10) as db:
    for key, value in (
        ("BindAddress", address),
        ("Ipv6", "Disable"),
        ("AllowIPs", "192.168.3.0/24,127.0.0.1"),
    ):
        result = db.execute(
            "UPDATE settings SET value = ? WHERE key = ?", (value, key)
        )
        if result.rowcount != 1:
            raise RuntimeError("Missing 1Panel setting: " + key)
    db.commit()
print("1Panel bound to Wi-Fi", address)
