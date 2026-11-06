#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_USER=app
readonly APP_HOME=/home/app
readonly KEYRING_DATA_HOME="${APP_HOME}/.local/share/fastlink-keyring"
readonly KEYRING_PASSWORD_FILE="${KEYRING_DATA_HOME}/unlock.password"
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR=/tmp/runtime-app

# An empty password disables the noVNC credential prompt. If authentication is
# enabled, require eight characters so x11vnc cannot silently shorten it.
VNC_PASSWORD="${VNC_PASSWORD:-}"
if [[ -n "${VNC_PASSWORD}" && ! "${VNC_PASSWORD}" =~ ^[[:print:]]{8}$ ]]; then
    echo "VNC_PASSWORD must contain exactly 8 printable characters." >&2
    exit 1
fi

install -d -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${APP_HOME}"
install -d -m 0700 -o "${APP_USER}" -g "${APP_USER}" \
    "${APP_HOME}/.config" \
    "${APP_HOME}/.local/share" \
    "${KEYRING_DATA_HOME}" \
    "${KEYRING_DATA_HOME}/keyrings" \
    "${APP_HOME}/.cache" \
    "${XDG_RUNTIME_DIR}"
chown "${APP_USER}:${APP_USER}" "${APP_HOME}"

rm -f /tmp/fastlink-x11vnc.pass
export VNC_AUTH_ARGS="-nopw"
if [[ -n "${VNC_PASSWORD}" ]]; then
    x11vnc -storepasswd "${VNC_PASSWORD}" /tmp/fastlink-x11vnc.pass >/dev/null
    chown "${APP_USER}:${APP_USER}" /tmp/fastlink-x11vnc.pass
    chmod 0600 /tmp/fastlink-x11vnc.pass
    export VNC_AUTH_ARGS="-rfbauth /tmp/fastlink-x11vnc.pass"
fi

# Start DBus after privilege separation. No TUN device or network
# administration capability is needed for ordinary HTTP/SOCKS5 proxy mode.
export DBUS_SESSION_BUS_ADDRESS="unix:path=/tmp/fastlink-dbus.sock"
gosu "${APP_USER}" env HOME="${APP_HOME}" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS}" \
    dbus-daemon --session --nofork --nopidfile \
    --address="${DBUS_SESSION_BUS_ADDRESS}" &
DBUS_PID=$!
KEYRING_PID=""

stop_session_services() {
    if [[ -n "${KEYRING_PID}" ]]; then
        kill "${KEYRING_PID}" 2>/dev/null || true
        wait "${KEYRING_PID}" 2>/dev/null || true
    fi
    kill "${DBUS_PID}" 2>/dev/null || true
    wait "${DBUS_PID}" 2>/dev/null || true
}
trap stop_session_services EXIT

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

# Use a separate persistent keyring so old, password-protected keyrings in the
# home volume cannot trigger an unlock dialog. Leave those old files untouched.
# The unlock key stays in the private home volume and is never printed in logs.
if [[ ! -f "${KEYRING_PASSWORD_FILE}" ]]; then
    umask 077
    head -c 32 /dev/urandom | base64 | tr -d '\n' > "${KEYRING_PASSWORD_FILE}"
fi
if [[ ! -s "${KEYRING_PASSWORD_FILE}" ]]; then
    echo "The Fastlink keyring unlock key is empty." >&2
    exit 1
fi
chown "${APP_USER}:${APP_USER}" "${KEYRING_PASSWORD_FILE}"
chmod 0600 "${KEYRING_PASSWORD_FILE}"

gosu "${APP_USER}" /usr/local/bin/fastlink-keyring &
KEYRING_PID=$!

KEYRING_READY=false
for _ in {1..100}; do
    if ! kill -0 "${KEYRING_PID}" 2>/dev/null; then
        echo "The Fastlink keyring failed to start." >&2
        exit 1
    fi
    if owner=$(gosu "${APP_USER}" dbus-send --session \
        --dest=org.freedesktop.DBus --type=method_call --print-reply \
        /org/freedesktop/DBus org.freedesktop.DBus.NameHasOwner \
        string:org.freedesktop.secrets 2>/dev/null) && [[ "${owner}" == *"boolean true"* ]]; then
        if state=$(gosu "${APP_USER}" dbus-send --session \
            --dest=org.freedesktop.secrets --type=method_call --print-reply \
            /org/freedesktop/secrets/collection/login \
            org.freedesktop.DBus.Properties.Get \
            string:org.freedesktop.Secret.Collection string:Locked 2>/dev/null) && \
            [[ "${state}" == *"boolean false"* ]]; then
            KEYRING_READY=true
            break
        fi
    fi
    sleep 0.1
done
if [[ "${KEYRING_READY}" != true ]]; then
    echo "Timed out waiting for the Fastlink keyring to unlock." >&2
    exit 1
fi

# libsecret uses the default collection. Select the unlocked login collection
# before Fastlink starts, avoiding a separate create/unlock collection prompt.
gosu "${APP_USER}" dbus-send --session --dest=org.freedesktop.secrets \
    --type=method_call --print-reply /org/freedesktop/secrets \
    org.freedesktop.Secret.Service.SetAlias string:default \
    objpath:/org/freedesktop/secrets/collection/login >/dev/null

echo "Fastlink UI: http://SERVER_IP:${FASTLINK_WEB_PORT:-6080}/vnc.html?autoconnect=1&resize=remote&path=websockify"
echo "HTTP/SOCKS5 proxy: SERVER_IP:${FASTLINK_PROXY_PORT:-7890}"
echo "In Fastlink, set Mixed Port to 7890, enable Allow LAN, and leave TUN off."

exec "$@"
