#!/bin/sh
# Load the battery drivers extracted from the exact Kali 6.1-sdm845 rootfs.
# A different kernel must use its own matching modules.
set -eu

if [ "$(uname -r)" != '6.1-sdm845' ]; then
    echo 'Polaris battery: unsupported kernel; leaving power drivers alone'
    exit 0
fi

base=/lib/modules/6.1-sdm845/polaris

load_one() {
    module=$1
    file=$2
    expected=$3
    if [ -d "/sys/module/$module" ]; then
        echo "Polaris battery: $module already loaded"
        return 0
    fi
    path="$base/$file"
    [ -r "$path" ] || { echo "Polaris battery: missing $path" >&2; return 1; }
    actual=$(sha256sum "$path")
    actual=${actual%% *}
    [ "$actual" = "$expected" ] || {
        echo "Polaris battery: checksum mismatch for $path" >&2
        return 1
    }
    insmod "$path"
    echo "Polaris battery: loaded $module"
}

# The charger consumes RRADC channels, and the fuel gauge references the
# charger power-supply node. Keep this order for the deferred probes.
load_one qcom_spmi_rradc qcom-spmi-rradc.ko f45cf4053188d1678f0d22694ffe162a85a69ca471feee40e9511bc7f1d9aec4
load_one qcom_pmi8998_charger qcom_pmi8998_charger.ko 05bc9bfd4e0fb2c186c4dc7985ad4362d76d5c40245c9a72a9c93523544a26e3
load_one qcom_fg qcom_fg.ko 29ea66ae9711dda27406facbee487bf3b315a5d696e24c134635e22bbba898e2
