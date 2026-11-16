#!/usr/bin/env bash
set -uo pipefail

readonly APP_EXECUTABLE=/opt/com.flapp.clients.apex/apex-client
readonly CLOSE_DELAY="${FASTLINK_AUTO_CLOSE_DELAY:-10}"

log() {
    echo "Fastlink auto-close: $*"
}

# Configuration or desktop failures must never stop the supervised app.
if [[ ! "${CLOSE_DELAY}" =~ ^(0|[1-9][0-9]{0,3})$ ]]; then
    log "invalid FASTLINK_AUTO_CLOSE_DELAY; leaving the window open."
    exit 0
fi
if [[ "${CLOSE_DELAY}" == 0 ]]; then
    log "disabled."
    exit 0
fi

sleep "${CLOSE_DELAY}"

# A slow startup may not have created the window yet. Never keep watching
# indefinitely: a window reopened by the user later must stay open.
for _ in {1..30}; do
    windows=$(wmctrl -lp 2>/dev/null) || windows=""
    while read -r window_id desktop pid host title; do
        [[ "${window_id}" =~ ^0x[0-9a-fA-F]+$ && "${pid}" =~ ^[1-9][0-9]*$ ]] || continue
        [[ "$(readlink -f "/proc/${pid}/exe" 2>/dev/null)" == "${APP_EXECUTABLE}" ]] || continue

        properties=$(xprop -id "${window_id}" _NET_WM_WINDOW_TYPE WM_TRANSIENT_FOR WM_PROTOCOLS 2>/dev/null) || continue
        [[ "${properties}" == *"_NET_WM_WINDOW_TYPE_NORMAL"* ]] || continue
        [[ "${properties}" != *"_NET_WM_WINDOW_TYPE_DIALOG"* && "${properties}" != *"window id #"* ]] || continue
        # Fluxbox can forcibly close clients without WM_DELETE_WINDOW. Only
        # select clients that explicitly support the graceful close protocol.
        [[ "${properties}" == *"WM_DELETE_WINDOW"* ]] || continue

        # _NET_CLOSE_WINDOW follows the titlebar close path. Do not use
        # xdotool windowclose (XDestroyWindow), windowkill, or process signals.
        if ! wmctrl -ic "${window_id}"; then
            log "could not request window close; leaving Fastlink running."
            exit 0
        fi

        for _ in {1..5}; do
            sleep 1
            if [[ "$(readlink -f "/proc/${pid}/exe" 2>/dev/null)" != "${APP_EXECUTABLE}" ]]; then
                log "WARNING: Fastlink exited after the close request; check its close-to-background setting."
                exit 0
            fi
            if ! windows=$(wmctrl -lp 2>/dev/null); then
                log "cannot verify the window state; no further close requests will be sent."
                exit 0
            fi
            if ! awk -v id="${window_id}" '$1 == id { found = 1 } END { exit !found }' <<< "${windows}"; then
                log "window closed; Fastlink PID ${pid} is still running in the background."
                exit 0
            fi
        done
        log "close requested, but the window remains open; no further close requests will be sent."
        exit 0
    done <<< "${windows}"
    sleep 1
done

log "no eligible Fastlink main window appeared within 30 seconds; leaving the app running."
