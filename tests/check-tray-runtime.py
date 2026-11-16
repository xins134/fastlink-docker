#!/usr/bin/env python3
"""Check real X11 tray ownership in a clean, built Fastlink image.

Run as app under dbus-run-session, with DISPLAY=:0. This starts the image's
Xvfb, Fluxbox and tint2 commands, but never starts Fastlink or uses its account.
It must run in a separate test container with no desktop already running.
"""

import configparser
import ctypes
import ctypes.util
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time


SUPERVISOR_CONFIG = Path("/etc/supervisor/conf.d/fastlink.conf")
CONFIG_TEMPLATE = Path("/etc/fluxbox/fastlink-init")
RUNTIME_CONFIG = Path("/tmp/runtime-app/fluxbox-init")


def command(config, name, environment):
    value = config[f"program:{name}"]["command"]
    value = re.sub(r"%\(ENV_([A-Za-z_][A-Za-z_0-9]*)\)s",
                   lambda match: environment[match[1]], value)
    return shlex.split(value)


def wait_for(predicate, processes, description, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for name, process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited with status {process.returncode}")
        if predicate():
            return
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {description}")


def main():
    processes = []
    logs = {}
    display = None
    x11 = None
    failure = None

    with tempfile.TemporaryDirectory(prefix="fastlink-tray-check-") as directory:
        try:
            if os.geteuid() != pwd.getpwnam("app").pw_uid:
                raise RuntimeError("Run this check with gosu app")
            if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
                raise RuntimeError("Run this check under dbus-run-session")

            environment = dict(os.environ)
            environment.update(HOME="/home/app", USER="app",
                               XDG_RUNTIME_DIR="/tmp/runtime-app")
            environment.setdefault("DISPLAY", ":0")
            environment.setdefault("SCREEN_WIDTH", "1280")
            environment.setdefault("SCREEN_HEIGHT", "800")
            environment.setdefault("SCREEN_DEPTH", "24")

            config = configparser.RawConfigParser()
            if not config.read(SUPERVISOR_CONFIG):
                raise RuntimeError(f"Missing {SUPERVISOR_CONFIG}")
            commands = {name: command(config, name, environment)
                        for name in ("xvfb", "fluxbox", "tint2")}
            if commands["xvfb"][1] != environment["DISPLAY"]:
                raise RuntimeError("DISPLAY must match the image's Xvfb display")

            x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            x11.XCloseDisplay.restype = ctypes.c_int
            x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                       ctypes.c_int]
            x11.XInternAtom.restype = ctypes.c_ulong
            x11.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            x11.XGetSelectionOwner.restype = ctypes.c_ulong

            display_name = environment["DISPLAY"].encode()
            display = x11.XOpenDisplay(display_name)
            if display:
                raise RuntimeError("An X server is already running; use a clean test container")

            RUNTIME_CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(CONFIG_TEMPLATE, RUNTIME_CONFIG)
            RUNTIME_CONFIG.chmod(0o600)

            def start(name):
                log = open(Path(directory) / f"{name}.log", "wb")
                logs[name] = log
                process = subprocess.Popen(commands[name], env=environment,
                                           stdout=log, stderr=subprocess.STDOUT)
                processes.append((name, process))

            start("xvfb")

            def display_ready():
                nonlocal display
                display = x11.XOpenDisplay(display_name)
                return bool(display)

            wait_for(display_ready, processes, "Xvfb")
            tray_atom = x11.XInternAtom(display, b"_NET_SYSTEM_TRAY_S0", 0)

            def tray_owner():
                return x11.XGetSelectionOwner(display, tray_atom)

            start("fluxbox")

            def window_manager_ready():
                result = subprocess.run(
                    ["xprop", "-root", "_NET_SUPPORTING_WM_CHECK"],
                    env=environment, capture_output=True, text=True, timeout=2)
                match = re.search(r"window id # (0x[0-9a-fA-F]+)", result.stdout)
                return result.returncode == 0 and match is not None and int(match[1], 16) != 0

            wait_for(window_manager_ready, processes, "Fluxbox")
            # The EWMH property can appear before toolbar initialization ends.
            # Check a short settled interval so an old hidden toolbar is caught.
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                if tray_owner():
                    raise RuntimeError("Fluxbox claimed _NET_SYSTEM_TRAY_S0")
                for name, process in processes:
                    if process.poll() is not None:
                        raise RuntimeError(f"{name} exited with status {process.returncode}")
                time.sleep(0.1)

            start("tint2")
            wait_for(lambda: tray_owner() != 0, processes, "tint2 tray ownership")
        except Exception as error:
            failure = error
        finally:
            # Close the test's X connection before the server exits, and stop
            # clients completely before terminating Xvfb.
            if display and x11 is not None:
                x11.XCloseDisplay(display)
            for name, process in reversed(processes):
                if process.poll() is None:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=3)
            for log in logs.values():
                log.close()

        if failure is None:
            for name, log in logs.items():
                contents = Path(log.name).read_text(errors="replace").lower()
                for message in ("another systray", "invalid option"):
                    if message in contents:
                        failure = RuntimeError(f"{name} reported {message!r}")

        if failure is not None:
            print(f"FAIL: {failure}", file=sys.stderr)
            for name, log in logs.items():
                contents = Path(log.name).read_text(errors="replace")
                print(f"--- {name} ---\n{contents[-12000:]}", file=sys.stderr)
            return 1
        print("PASS: Fluxbox leaves the tray unclaimed; tint2 owns it without configuration errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
