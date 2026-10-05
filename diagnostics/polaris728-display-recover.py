#!/usr/bin/python3
"""Reassert Mutter's display state after an input on a stranded display.

The DSI controller can turn off while Mutter still reports PowerSaveMode=0.
Only a new touch or volume-key interrupt triggers recovery. No input payload,
coordinates, or key values are read or logged.
"""

import re
import subprocess
import time
from pathlib import Path

DRM_STATE = Path('/sys/kernel/debug/dri/0/state')
INTERRUPTS = Path('/proc/interrupts')
BUS_ENV = ['XDG_RUNTIME_DIR=/run/user/1000',
           'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus']
BUS = ['runuser', '-u', 'polaris', '--', 'env', *BUS_ENV, 'busctl', '--user']
MUTTER = ['org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
          'org.gnome.Mutter.DisplayConfig', 'PowerSaveMode']


def crtc_active():
    state = DRM_STATE.read_text()
    match = re.search(r'^crtc\[\d+\]: crtc-0\n(?:(?!^crtc\[).)*?^\s*active=(\d)',
                      state, re.MULTILINE | re.DOTALL)
    return None if match is None else match.group(1) == '1'


def input_count():
    count = 0
    for line in INTERRUPTS.read_text().splitlines():
        if not any(name in line for name in ('rmi4_i2c', 'Volume Up', 'Volume Down')):
            continue
        words = line.split(':', 1)[-1].split()
        count += sum(int(word) for word in words if word.isdecimal())
    return count


def mutter_power():
    result = subprocess.run([*BUS, 'get-property', *MUTTER],
                            capture_output=True, text=True, timeout=3, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def reassert_power_on():
    return subprocess.run([*BUS, 'set-property', *MUTTER, 'i', '0'],
                          capture_output=True, text=True, timeout=3,
                          check=False).returncode == 0


def main():
    if Path('/proc/sys/kernel/osrelease').read_text().strip() != '7.2.8-polaris':
        return
    previous = input_count()
    last_repair = 0.0
    while True:
        time.sleep(1)
        current = input_count()
        was_pressed = current > previous
        previous = current
        if not was_pressed or time.monotonic() - last_repair < 15:
            continue
        try:
            if crtc_active() is not False or mutter_power() != 'i 0':
                continue
            if reassert_power_on():
                last_repair = time.monotonic()
                print('Reasserted Mutter display power after input on inactive CRTC',
                      flush=True)
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f'Display recovery deferred: {error}', flush=True)


if __name__ == '__main__':
    main()
