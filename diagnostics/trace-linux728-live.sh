#!/bin/sh
# Run as root in a RAM-only 7.2.8 diagnostic boot. Stream brief state to USB ACM.
# No command lines, input, credentials, or files on userdata are collected.
set -u
exec >/dev/ttyGS0 2>&1
echo 'TRACE728: live sampling started'
while :; do
    printf '\nTRACE728 time=%s uptime=%s load=' "$(date +%s)" "$(cut -d ' ' -f 1 /proc/uptime)"
    cat /proc/loadavg
    for kind in cpu memory io; do
        printf 'pressure_%s ' "$kind"
        sed -n '1p' "/proc/pressure/$kind" 2>/dev/null || true
    done
    awk '/^(nr_dirty|nr_writeback|pgmajfault|pswpout) / { printf "%s=%s ", $1, $2 } END { print "" }' /proc/vmstat
    ps -eo pid,comm,stat,pcpu,wchan:20 --sort=-pcpu | head -n 9
    sleep 2
done
