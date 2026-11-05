#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_USER=app
readonly APP_HOME=/home/app
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR=/tmp/runtime-app

# VNC passwords contain at most eight characters. Require all eight so the
# configured password cannot be silently shortened by x11vnc.
VNC_PASSWORD="${VNC_PASSWORD:-fastlink}"
if [[ ! "${VNC_PASSWORD}" =~ ^[[:print:]]{8}$ ]]; then
    echo "VNC_PASSWORD must contain exactly 8 printable characters." >&2
    exit 1
fi

install -d -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${APP_HOME}"
install -d -m 0700 -o "${APP_USER}" -g "${APP_USER}" \
    "${APP_HOME}/.config" \
    "${APP_HOME}/.local/share" \
    "${APP_HOME}/.cache" \
    "${XDG_RUNTIME_DIR}"
chown "${APP_USER}:${APP_USER}" "${APP_HOME}"

rm -f /tmp/fastlink-x11vnc.pass
x11vnc -storepasswd "${VNC_PASSWORD}" /tmp/fastlink-x11vnc.pass >/dev/null
chown "${APP_USER}:${APP_USER}" /tmp/fastlink-x11vnc.pass
chmod 0600 /tmp/fastlink-x11vnc.pass

# Start DBus after privilege separation. No TUN device or network
# administration capability is needed for ordinary HTTP/SOCKS5 proxy mode.
export DBUS_SESSION_BUS_ADDRESS="unix:path=/tmp/fastlink-dbus.sock"
gosu "${APP_USER}" env DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS}" \
    dbus-daemon --session --nofork --nopidfile \
    --address="${DBUS_SESSION_BUS_ADDRESS}" &
DBUS_PID=$!

for _ in {1..50}; do
    [[ -S /tmp/fastlink-dbus.sock ]] && break
    if ! kill -0 "${DBUS_PID}" 2>/dev/null; then
        echo "The Fastlink desktop DBus session failed to start." >&2
        exit 1
    fi
    sleep 0.1
done
[[ -S /tmp/fastlink-dbus.sock ]] || {
    echo "Timed out waiting for the Fastlink desktop DBus session." >&2
    exit 1
}

stop_dbus() {
    kill "${DBUS_PID}" 2>/dev/null || true
    wait "${DBUS_PID}" 2>/dev/null || true
}
trap stop_dbus EXIT

echo "Fastlink UI: http://SERVER_IP:${FASTLINK_WEB_PORT:-6080}/vnc.html?autoconnect=1&resize=remote&path=websockify"
echo "HTTP/SOCKS5 proxy: SERVER_IP:${FASTLINK_PROXY_PORT:-7890}"
echo "In Fastlink, set Mixed Port to 7890, enable Allow LAN, and leave TUN off."

exec "$@"
