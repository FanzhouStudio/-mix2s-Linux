#!/usr/bin/python3
"""Initialize the sole present USIM before ModemManager on Polaris 7.2.8.

Read the live application's AID; never store subscriber identifiers, guess a
PIN, change slot mappings, reset the modem, or choose between two present cards.
"""
import os
import platform
import re
import subprocess
import time

if os.geteuid() != 0:
    raise SystemExit('Run as root before ModemManager starts')
if platform.release() != '7.2.8-polaris':
    print('Skipping: this preparation is scoped to 7.2.8-polaris')
    raise SystemExit(0)
if subprocess.run(['systemctl', 'is-active', '--quiet', 'ModemManager.service']).returncode == 0:
    raise SystemExit('ModemManager is already running; no SIM changes made')

env = dict(os.environ, LC_ALL='C')
status = None
for attempt in range(3):
    try:
        response = subprocess.run(
            ['qmicli', '-p', '-d', 'qrtr://0', '--uim-get-card-status'],
            capture_output=True, text=True, timeout=8, env=env)
        if response.returncode == 0:
            status = response.stdout
            break
    except subprocess.TimeoutExpired:
        pass
    if attempt < 2:
        time.sleep(2)
if status is None:
    raise SystemExit('QMI card status unavailable; no SIM changes made')

if re.search(r"Primary GW:\s+slot '\d+', application '\d+'", status):
    print('Primary GW session already exists; preserved')
    raise SystemExit(0)

present_cards = []
candidates = []
for match in re.finditer(r'^Slot \[(\d+)\]:\n(.*?)(?=^Slot \[|\Z)', status, re.M | re.S):
    slot, card = match.groups()
    if not re.search(r"Card state:\s*'present'", card):
        continue
    present_cards.append(slot)
    for app in re.finditer(r'Application \[\d+\]:\n(.*?)(?=\s*Application \[|\Z)', card, re.S):
        body = app.group(1)
        if not re.search(r"Application type:\s*'usim \(2\)'", body):
            continue
        aid = re.search(r'Application ID:\s*\n\s*([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2})+)', body)
        if aid and 5 <= len(aid.group(1).split(':')) <= 32:
            candidates.append((slot, aid.group(1)))

if not present_cards:
    print('No present SIM; no changes made')
    raise SystemExit(0)
if len(present_cards) != 1 or len(candidates) != 1:
    print('SIM/application selection is ambiguous; no changes made')
    raise SystemExit(0)

slot, aid = candidates[0]
try:
    result = subprocess.run(
        ['qmicli', '-p', '-d', 'qrtr://0',
         f'--uim-change-provisioning-session=slot={slot},activate=yes,session-type=primary-gw-provisioning,aid={aid}'],
        capture_output=True, text=True, timeout=12, env=env)
except subprocess.TimeoutExpired:
    raise SystemExit('SIM session activation timed out; no retry/reset attempted')
if result.returncode:
    raise SystemExit('SIM session activation failed; no retry/reset attempted')
print(f'Activated the sole present USIM in slot {slot}; ModemManager may now initialize')
