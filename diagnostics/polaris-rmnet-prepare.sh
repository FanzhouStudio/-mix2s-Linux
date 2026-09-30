#!/bin/sh
# The 6.1-sdm845 IPA data port needs the matching RMNET link driver.
set -eu

if [ "$(uname -r)" != '6.1-sdm845' ]; then
    echo 'Polaris RMNET: unsupported kernel; skipping'
    exit 0
fi

if [ -d /sys/module/rmnet ]; then
    echo 'Polaris RMNET: already loaded'
    exit 0
fi

path=/lib/modules/6.1-sdm845/polaris/rmnet.ko
expected=1f05cf63b86178cb7eba6dd84ec4ad2d8a8a581716dcc2d72723b2a653b6b135
[ -r "$path" ] || { echo "Polaris RMNET: missing $path" >&2; exit 1; }
actual=$(sha256sum "$path")
actual=${actual%% *}
[ "$actual" = "$expected" ] || {
    echo "Polaris RMNET: checksum mismatch for $path" >&2
    exit 1
}

insmod "$path"
echo 'Polaris RMNET: loaded'
