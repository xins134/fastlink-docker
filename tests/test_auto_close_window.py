"""Run the real close helper with isolated X11/process command doubles.

These tests verify window selection, timing, and failure handling without
touching a real desktop or terminating processes. They do not replace a Linux
GUI test of Fastlink's own close-to-background behavior.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "docker" / "auto-close-window.sh"
APP_EXECUTABLE = "/opt/com.flapp.clients.apex/apex-client"
NORMAL_PROPERTIES = """_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_NORMAL
WM_TRANSIENT_FOR:  not found.
WM_PROTOCOLS(ATOM) = WM_DELETE_WINDOW, _NET_WM_PING
"""

MOCK_COMMAND = r'''
import json
import os
from pathlib import Path
import re
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
state_path = Path(os.environ["WINDOW_TEST_STATE"])
state = json.loads(state_path.read_text())
with Path(os.environ["WINDOW_TEST_LOG"]).open("a") as log:
    log.write(json.dumps([name, *args]) + "\n")

def finish(code=0):
    state_path.write_text(json.dumps(state))
    sys.exit(code)

if name == "sleep":
    # Record requested delays without sleeping or speeding up the real app.
    pass
elif name == "readlink":
    match = re.fullmatch(r"/proc/(\d+)/exe", args[-1])
    executable = state["processes"].get(match[1]) if match else None
    if executable is None:
        finish(1)
    print(executable)
elif name == "xprop":
    window = next((window for window in state["windows"]
                   if window["id"] == args[1]), None)
    if window is None or window.get("property_failure"):
        finish(1)
    print(window["properties"])
elif name == "wmctrl" and args == ["-lp"]:
    state["lookups"] = state.get("lookups", 0) + 1
    if state.get("listing_failure") or (state.get("closed")
                                        and state.get("verification_failure")):
        finish(1)
    if state["lookups"] >= state.get("ready_on_lookup", 1):
        for window in state["windows"]:
            hidden = window["id"] in state.get("closed", [])
            reopened = state["lookups"] >= state.get("reopen_on_lookup", 10**6)
            if not hidden or reopened:
                print(window["id"], 0, window["pid"], "desktop", window["title"])
elif name == "wmctrl" and len(args) == 2 and args[0] == "-ic":
    if state.get("reject_close"):
        finish(1)
    window = next(window for window in state["windows"] if window["id"] == args[1])
    if state.get("exit_after_close"):
        state["processes"].pop(str(window["pid"]), None)
    elif not state.get("ignore_close"):
        state.setdefault("closed", []).append(window["id"])
else:
    finish(2)
finish()
'''


class AutoCloseWindowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fastlink window test ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state_file = self.root / "state.json"
        self.log_file = self.root / "commands.jsonl"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.state_file.write_text(json.dumps({"windows": [], "processes": {}}))
        for name in ("wmctrl", "xprop", "readlink", "sleep"):
            command = self.bin / name
            command.write_text("#!" + sys.executable + "\n" + MOCK_COMMAND)
            command.chmod(0o755)

    def state(self, **changes):
        state = json.loads(self.state_file.read_text())
        state.update(changes)
        self.state_file.write_text(json.dumps(state))

    def window(self, window_id="0x01000001", pid=101, title="Fastlink-极速版",
               executable=APP_EXECUTABLE, properties=NORMAL_PROPERTIES, **changes):
        state = json.loads(self.state_file.read_text())
        window = {"id": window_id, "pid": pid, "title": title,
                  "properties": properties, **changes}
        state["windows"].append(window)
        state["processes"][str(pid)] = executable
        self.state_file.write_text(json.dumps(state))
        return window_id

    def run_helper(self, delay=None):
        environment = dict(os.environ,
                           PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                           WINDOW_TEST_STATE=str(self.state_file),
                           WINDOW_TEST_LOG=str(self.log_file))
        environment.pop("FASTLINK_AUTO_CLOSE_DELAY", None)
        if delay is not None:
            environment["FASTLINK_AUTO_CLOSE_DELAY"] = delay
        result = subprocess.run(["bash", str(SCRIPT)], env=environment,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def commands(self, name=None, action=None):
        commands = ([json.loads(line) for line in self.log_file.read_text().splitlines()]
                    if self.log_file.exists() else [])
        return [command for command in commands
                if (name is None or command[0] == name)
                and (action is None or action in command[1:])]

    def test_default_delay_precedes_lookup_and_success_keeps_process_alive(self):
        window_id = self.window()
        result = self.run_helper()
        self.assertEqual(self.commands()[0], ["sleep", "10"])
        self.assertEqual(self.commands("wmctrl", "-ic"), [["wmctrl", "-ic", window_id]])
        self.assertIn("still running in the background", result.stdout)
        self.assertEqual(json.loads(self.state_file.read_text())["processes"]["101"],
                         APP_EXECUTABLE)
        self.assertEqual(len(self.commands("wmctrl", "-lp")), 2)

    def test_custom_delay_is_used(self):
        self.window()
        self.run_helper(delay="25")
        self.assertEqual(self.commands()[0], ["sleep", "25"])

    def test_only_exact_executable_owned_normal_graceful_window_is_closed(self):
        foreign = self.window("0x01000001", pid=201, title="FastlinkTaskbar",
                              executable="/usr/bin/tint2")
        self.window("0x01000002", properties=NORMAL_PROPERTIES.replace(
            "_NET_WM_WINDOW_TYPE_NORMAL", "_NET_WM_WINDOW_TYPE_DIALOG"))
        self.window("0x01000003", properties=NORMAL_PROPERTIES.replace(
            "WM_TRANSIENT_FOR:  not found.",
            "WM_TRANSIENT_FOR(WINDOW): window id # 0x01000005"))
        self.window("0x01000004", properties=NORMAL_PROPERTIES.replace(
            "WM_DELETE_WINDOW, ", ""))
        main = self.window("0x01000005", title="Any localized main-window title")
        self.run_helper()
        self.assertEqual(self.commands("wmctrl", "-ic"), [["wmctrl", "-ic", main]])
        self.assertNotIn(foreign, [command[2] for command in self.commands("xprop")])

    def test_slow_window_is_found_within_bounded_startup_wait(self):
        window_id = self.window()
        self.state(ready_on_lookup=3)
        self.run_helper()
        self.assertEqual(len(self.commands("wmctrl", "-lp")), 4)
        self.assertEqual(self.commands("wmctrl", "-ic"), [["wmctrl", "-ic", window_id]])

    def test_missing_window_stops_after_30_attempts(self):
        result = self.run_helper()
        self.assertEqual(len(self.commands("wmctrl", "-lp")), 30)
        self.assertEqual(self.commands("wmctrl", "-ic"), [])
        self.assertIn("no eligible Fastlink main window", result.stdout)

    def test_disabled_and_invalid_configuration_do_not_touch_the_desktop(self):
        for delay, expected in (("0", "disabled"), ("-1", "invalid"),
                                ("abc", "invalid"), ("01", "invalid")):
            with self.subTest(delay=delay):
                result = self.run_helper(delay=delay)
                self.assertIn(expected, result.stdout)
                self.assertEqual(self.commands(), [])

    def test_rejected_close_is_nonfatal_and_sent_only_once(self):
        self.window()
        self.state(reject_close=True)
        result = self.run_helper()
        self.assertIn("could not request window close", result.stdout)
        self.assertEqual(len(self.commands("wmctrl", "-ic")), 1)
        self.assertEqual(len(self.commands("wmctrl", "-lp")), 1)
        self.assertIn("101", json.loads(self.state_file.read_text())["processes"])

    def test_ignored_close_checks_five_times_without_repeating_the_action(self):
        self.window()
        self.state(ignore_close=True)
        result = self.run_helper()
        self.assertIn("window remains open", result.stdout)
        self.assertNotIn("still running in the background", result.stdout)
        self.assertEqual(len(self.commands("wmctrl", "-ic")), 1)
        self.assertEqual(len(self.commands("wmctrl", "-lp")), 6)
        self.assertIn("101", json.loads(self.state_file.read_text())["processes"])

    def test_app_exit_after_close_is_reported_without_false_background_success(self):
        self.window()
        self.state(exit_after_close=True)
        result = self.run_helper()
        self.assertIn("WARNING: Fastlink exited", result.stdout)
        self.assertNotIn("still running in the background", result.stdout)
        self.assertEqual(len(self.commands("wmctrl", "-ic")), 1)

    def test_verification_failure_does_not_issue_another_close(self):
        self.window()
        self.state(verification_failure=True)
        result = self.run_helper()
        self.assertIn("cannot verify the window state", result.stdout)
        self.assertNotIn("still running in the background", result.stdout)
        self.assertEqual(len(self.commands("wmctrl", "-ic")), 1)

    def test_success_stops_watching_before_a_later_user_reopen(self):
        self.window()
        self.state(reopen_on_lookup=3)
        result = self.run_helper()
        self.assertIn("still running in the background", result.stdout)
        self.assertEqual(len(self.commands("wmctrl", "-lp")), 2)
        self.assertEqual(len(self.commands("wmctrl", "-ic")), 1)


if __name__ == "__main__":
    unittest.main()
