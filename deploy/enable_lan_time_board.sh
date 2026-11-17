#!/bin/bash
# Run once with sudo; subsequent boot/network recovery uses systemd-timesyncd.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
    echo 'Run this installer with sudo.' >&2
    exit 1
fi
config_directory=/etc/systemd/timesyncd.conf.d
config_file="$config_directory/70-dnb26-lan.conf"
backup_directory=/var/lib/dnb26-time-setup
expected_content='[Time]
NTP=192.168.137.1
FallbackNTP=
RootDistanceMaxSec=20
PollIntervalMinSec=32
PollIntervalMaxSec=64'

# Refuse to replace another configuration under this dedicated name.
if [ -e "$config_file" ] && ! cmp -s "$config_file" <(printf '%s\n' "$expected_content"); then
    echo 'The DnB26 time configuration already contains different settings; inspect it first.' >&2
    exit 1
fi
install -d -m 0755 "$config_directory" "$backup_directory"
if [ ! -e "$backup_directory/before.txt" ]; then
    {
        date -u --iso-8601=seconds
        timedatectl show -p NTP -p NTPSynchronized -p Timezone
        systemctl is-enabled systemd-timesyncd || true
        systemctl is-active systemd-timesyncd || true
    } > "$backup_directory/before.txt"
    chmod 0600 "$backup_directory/before.txt"
fi
printf '%s\n' "$expected_content" > "$config_file"
chmod 0644 "$config_file"
timedatectl set-ntp true
systemctl enable --now systemd-timesyncd
systemctl restart systemd-timesyncd

for attempt in $(seq 1 30); do
    if systemctl is-active --quiet systemd-timesyncd &&
        [ "$(timedatectl show -p NTPSynchronized --value)" = yes ] &&
        [ "$(timedatectl show-timesync -p ServerAddress --value)" = 192.168.137.1 ] &&
        busctl --json=short get-property org.freedesktop.timesync1 \
            /org/freedesktop/timesync1 org.freedesktop.timesync1.Manager NTPMessage |
            python3 -c 'import json,sys; v=json.load(sys.stdin)["data"]; sys.exit(0 if v[13] > 0 and not v[12] and v[2] == 4 and 1 <= v[3] <= 15 else 1)'; then
        timedatectl timesync-status --no-pager
        timedatectl status
        {
            date -u --iso-8601=seconds
            timedatectl show -p NTP -p NTPSynchronized -p Timezone
            timedatectl show-timesync --all
        } > "$backup_directory/after.txt"
        chmod 0600 "$backup_directory/after.txt"
        echo 'Automatic LAN time synchronization succeeded; enabled for subsequent boots.'
        exit 0
    fi
    sleep 2
done
echo 'The service is enabled but has not synchronized yet. Check Windows Time and UDP 123 on the dedicated Ethernet link.' >&2
timedatectl timesync-status --no-pager || true
exit 1
