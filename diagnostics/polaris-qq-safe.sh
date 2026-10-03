#!/bin/sh
# Keep QQ's Chromium renderer off the phone's unstable GPU path.
exec /opt/QQ/qq --disable-gpu --disable-features=Vulkan "$@"
