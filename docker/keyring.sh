#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_HOME=/home/app
readonly KEYRING_DATA_HOME="${APP_HOME}/.local/share/fastlink-keyring"

# Used both at container startup and for DBus reactivation after a daemon exit.
# Read the persistent unlock key without passing it in arguments or logging it.
exec env HOME="${APP_HOME}" XDG_DATA_HOME="${KEYRING_DATA_HOME}" \
    /usr/bin/gnome-keyring-daemon --foreground --unlock --components=secrets \
    < "${KEYRING_DATA_HOME}/unlock.password"
