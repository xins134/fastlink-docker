# syntax=docker/dockerfile:1
FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DISPLAY=:0 \
    XDG_RUNTIME_DIR=/tmp/runtime-app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    dbus-x11 \
    fonts-noto-cjk \
    gnome-keyring \
    gosu \
    libayatana-appindicator3-1 \
    libgtk-3-0t64 \
    libjavascriptcoregtk-4.1-0 \
    libkeybinder-3.0-0 \
    libsecret-1-0 \
    libsoup-3.0-0 \
    libwebkit2gtk-4.1-0 \
    fluxbox \
    tint2 \
    novnc \
    supervisor \
    tigervnc-standalone-server \
    tigervnc-tools \
    websockify \
    x11vnc \
    xauth \
    xdg-utils \
    xvfb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY fastlinkapp-linux-speed-*-amd64.deb /tmp/
RUN set -- /tmp/fastlinkapp-linux-speed-*-amd64.deb; \
    if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then \
        echo "Expected exactly one fastlinkapp-linux-speed-*-amd64.deb package" >&2; \
        exit 1; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends "$1" && \
    rm -f "$1" && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --home-dir /home/app app \
    && mkdir -p /var/log/supervisor /tmp/runtime-app \
    && chown -R app:app /home/app /tmp/runtime-app

COPY docker/supervisord.conf /etc/supervisor/conf.d/fastlink.conf
COPY docker/fluxbox-init /etc/skel/.fluxbox/init
COPY docker/tint2rc /etc/xdg/tint2/tint2rc
COPY docker/entrypoint.sh /usr/local/bin/fastlink-entrypoint
COPY docker/keyring.sh /usr/local/bin/fastlink-keyring
COPY docker/org.freedesktop.secrets.service /usr/share/dbus-1/services/org.freedesktop.secrets.service
RUN chmod 0755 /usr/local/bin/fastlink-entrypoint /usr/local/bin/fastlink-keyring

STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/fastlink-entrypoint"]
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
