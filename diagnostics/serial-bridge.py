#!/usr/bin/python3
"""Keep the Polaris ACM port open across interactive host commands."""
import argparse
import os
from pathlib import Path
import select
import sys
import termios
import time
import tty

import serial

parser = argparse.ArgumentParser()
parser.add_argument('--log', help='Append received console output to a private host file')
args = parser.parse_args()
log = None
if args.log:
    path = Path(args.log)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    log = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), 'wb', buffering=0)

original = termios.tcgetattr(sys.stdin.fileno())
connection = None
escape_state = "text"


def emit(data):
    os.write(sys.stdout.fileno(), data)
    if log is not None:
        log.write(data)


def plain_terminal(data):
    # Do not forward terminal queries/OSC shell integration to the host PTY.
    # Host terminal replies must never become input to the phone's shell.
    global escape_state
    result = bytearray()
    for byte in data:
        if escape_state == "text":
            if byte == 27:
                escape_state = "escape"
            elif byte >= 32 or byte in (9, 10, 13):
                result.append(byte)
        elif escape_state == "escape":
            if byte == 91:
                escape_state = "csi"
            elif byte in (93, 80, 94, 95, 88):
                escape_state = "string"
            else:
                escape_state = "text"
        elif escape_state == "csi":
            if 64 <= byte <= 126:
                escape_state = "text"
        elif escape_state == "string":
            if byte == 7:
                escape_state = "text"
            elif byte == 27:
                escape_state = "string_escape"
        elif escape_state == "string_escape":
            escape_state = "text" if byte == 92 else "string"
    return result


try:
    tty.setraw(sys.stdin.fileno())
    while True:
        if connection is None:
            # Never carry a command typed during a disconnect into a new boot.
            # In particular, a queued reboot must not execute after reconnect.
            pending, _, _ = select.select([sys.stdin.fileno()], [], [], 0)
            if pending:
                discarded = os.read(sys.stdin.fileno(), 65536)
                if not discarded or discarded == b"\x1d":
                    break
                emit(b'\r\n[serial disconnected; input discarded]\r\n')
            try:
                connection = serial.Serial("/dev/ttyACM0", 115200, timeout=0, write_timeout=3)
                connection.write(b"\r")
                stamp = time.strftime('%Y-%m-%d %H:%M:%S %z')
                emit(f'\r\n[serial connected {stamp}]\r\n'.encode())
            except (OSError, serial.SerialException):
                time.sleep(0.2)
                continue
        ready, _, _ = select.select([sys.stdin.fileno(), connection.fileno()], [], [], 0.5)
        try:
            if connection.fileno() in ready:
                data = os.read(connection.fileno(), 65536)
                if data:
                    emit(plain_terminal(data))
                else:
                    connection.close()
                    connection = None
                    time.sleep(0.2)
                    continue
        except (OSError, serial.SerialException):
            connection.close()
            connection = None
            continue
        if sys.stdin.fileno() in ready:
            data = os.read(sys.stdin.fileno(), 65536)
            if not data or data == b"\x1d":
                break
            try:
                connection.write(data)
            except (OSError, serial.SerialException):
                # A timed-out command may have been partly transmitted. Do not
                # replay it after reconnecting and risk a duplicate mutation.
                emit(b'\r\n[serial write failed; reconnecting, input not replayed]\r\n')
                connection.close()
                connection = None
finally:
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, original)
    if connection is not None:
        connection.close()
    if log is not None:
        log.close()
