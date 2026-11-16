"""Exercise startup synchronization without modifying the host package database.

Run with ``python3 -m unittest discover -s tests -v``. The actual Bash script
runs with temporary dpkg/APT command doubles; this is not a Docker integration
test or a test of Debian's own dependency resolver.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "docker" / "sync-package.sh"
PACKAGE = "com.flapp.clients.apex"

MOCK_COMMAND = r'''
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
state_path = Path(os.environ["PACKAGE_TEST_STATE"])
state = json.loads(state_path.read_text())
log_path = Path(os.environ["PACKAGE_TEST_LOG"])
with log_path.open("a") as log:
    log.write(json.dumps([name, *args]) + "\n")

def finish(code=0):
    state_path.write_text(json.dumps(state))
    sys.exit(code)

def package_metadata(path):
    try:
        return json.loads(Path(path).read_text())
    except (ValueError, OSError):
        print("invalid deb archive", file=sys.stderr)
        finish(2)

if name == "dpkg-deb":
    file_index = next(i for i, value in enumerate(args) if value.endswith(".deb"))
    metadata = package_metadata(args[file_index])
    fields = args[file_index + 1:]
    if len(fields) == 1:
        print(metadata.get(fields[0], ""))
    else:
        for field in fields or metadata:
            print(field + ": " + metadata.get(field, ""))
elif name == "dpkg-query":
    installed = state.get("installed")
    if not installed:
        finish(1)
    format_value = next((arg.split("=", 1)[1] for arg in args
                         if arg.startswith(("--showformat=", "-f="))), None)
    if format_value is None:
        for flag in ("--showformat", "-f"):
            if flag in args:
                format_value = args[args.index(flag) + 1]
                break
    format_value = format_value or "${db:Status-Status}\\t${Version}\\t${Architecture}"
    status = installed["status"]
    values = {"db:Status-Status": status,
              "Status": "install ok " + status,
              "Version": installed["version"],
              "Architecture": installed["architecture"]}
    for key, value in values.items():
        format_value = format_value.replace("${" + key + "}", value)
    print(format_value.replace(r"\t", "\t").replace(r"\n", "\n"), end="")
elif name == "dpkg":
    if "--print-architecture" in args:
        print(state.get("architecture", "amd64"))
    elif "--compare-versions" in args:
        index = args.index("--compare-versions")
        left, operator, right = args[index + 1:index + 4]
        # These fixtures only need equality; Debian version ordering belongs
        # to dpkg, not to this test double.
        normalize = lambda version: version.removeprefix("0:").removesuffix("-0")
        finish(0 if operator == "eq" and normalize(left) == normalize(right) else 1)
    else:
        finish(2)
elif name == "apt-get":
    if "install" in args:
        state["install_attempts"] = state.get("install_attempts", 0) + 1
        if state.get("install_failure") or (state.get("fail_first_install")
                                           and state["install_attempts"] == 1):
            finish(100)
        if not state.get("leave_wrong_version"):
            metadata = package_metadata(next(arg for arg in args if arg.endswith(".deb")))
            state["installed"] = {"status": "installed",
                                  "version": metadata["Version"],
                                  "architecture": metadata["Architecture"]}
    elif "update" in args and state.get("update_failure"):
        finish(100)
elif name == "rm":
    # The cleanup targets the container's APT directory; never touch the host.
    pass
else:
    finish(2)
finish()
'''


class PackageSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fastlink package test ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.download = self.root / "Download with spaces"
        self.download.mkdir()
        self.state_file = self.root / "state.json"
        self.log_file = self.root / "commands.jsonl"
        self.state_file.write_text(json.dumps({"installed": {
            "status": "installed", "version": "7.3.1", "architecture": "amd64"}}))
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("dpkg-deb", "dpkg-query", "dpkg", "apt-get", "rm"):
            command = self.bin / name
            command.write_text("#!" + sys.executable + "\n" + MOCK_COMMAND)
            command.chmod(0o755)

    def state(self, **changes):
        state = json.loads(self.state_file.read_text())
        state.update(changes)
        self.state_file.write_text(json.dumps(state))

    def deb(self, version="7.3.1", filename="Fastlink release.deb", package=PACKAGE,
            architecture="amd64"):
        path = self.download / filename
        path.write_text(json.dumps({"Package": package, "Version": version,
                                    "Architecture": architecture}))
        return path

    def run_sync(self, expected_code=0):
        environment = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                           PACKAGE_TEST_STATE=str(self.state_file),
                           PACKAGE_TEST_LOG=str(self.log_file))
        result = subprocess.run(["bash", str(SCRIPT), str(self.download)],
                                env=environment, capture_output=True, text=True)
        if expected_code == 0:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def commands(self, name=None, action=None):
        commands = ([json.loads(line) for line in self.log_file.read_text().splitlines()]
                    if self.log_file.exists() else [])
        return [command for command in commands
                if (name is None or command[0] == name)
                and (action is None or action in command[1:])]

    def test_same_version_and_second_start_do_not_install_or_refresh(self):
        self.deb()
        self.run_sync()
        self.run_sync()
        self.assertEqual(self.commands("apt-get"), [])

    def test_upgrade_and_downgrade_install_exact_local_file_without_network_refresh(self):
        for version in ("7.4.0", "7.2.0"):
            with self.subTest(version=version):
                path = self.deb(version)
                self.run_sync()
                install = self.commands("apt-get", "install")[-1]
                self.assertIn(str(path), install)
                self.assertIn("--allow-downgrades", install)
                self.assertEqual(json.loads(self.state_file.read_text())["installed"]["version"],
                                 version)
                self.run_sync()
        self.assertEqual(len(self.commands("apt-get", "install")), 2)
        self.assertEqual(self.commands("apt-get", "update"), [])

    def test_missing_or_empty_directory_keeps_installed_package(self):
        self.run_sync()
        self.download.rmdir()
        self.run_sync()
        self.assertEqual(self.commands("apt-get"), [])

    def test_download_path_must_be_a_directory(self):
        self.download.rmdir()
        self.download.write_text("not a directory")
        self.run_sync(expected_code=1)
        self.assertEqual(self.commands("apt-get"), [])

    def test_no_local_package_and_not_installed_fails(self):
        self.state(installed=None)
        self.run_sync(expected_code=1)
        self.assertEqual(self.commands("apt-get"), [])

    def test_not_installed_or_unconfigured_is_installed_even_at_same_version(self):
        self.deb()
        for installed in (None, {"status": "unpacked", "version": "7.3.1",
                                 "architecture": "amd64"}):
            with self.subTest(installed=installed):
                self.state(installed=installed)
                self.run_sync()
        self.assertEqual(len(self.commands("apt-get", "install")), 2)

    def test_other_packages_are_ignored(self):
        self.deb("9.0", "unrelated.deb", package="another-package")
        self.run_sync()
        self.assertEqual(self.commands("apt-get"), [])
        self.deb("7.4.0")
        self.run_sync()
        self.assertEqual(len(self.commands("apt-get", "install")), 1)

    def test_multiple_fastlink_packages_fail_before_installation(self):
        self.deb("7.4.0", "first.deb")
        self.deb("7.2.0", "second.deb")
        self.run_sync(expected_code=1)
        self.assertEqual(self.commands("apt-get"), [])

    def test_corrupt_deb_fails_before_installation(self):
        (self.download / "broken.deb").write_bytes(b"incomplete upload")
        self.run_sync(expected_code=1)
        self.assertEqual(self.commands("apt-get"), [])

    def test_wrong_package_architecture_fails_before_installation(self):
        self.deb("7.4.0", architecture="arm64")
        self.run_sync(expected_code=1)
        self.assertEqual(self.commands("apt-get"), [])

    def test_missing_version_or_architecture_fails_before_installation(self):
        for field in ("Version", "Architecture"):
            with self.subTest(field=field):
                path = self.deb()
                metadata = json.loads(path.read_text())
                del metadata[field]
                path.write_text(json.dumps(metadata))
                self.run_sync(expected_code=1)
        self.assertEqual(self.commands("apt-get"), [])

    def test_same_version_but_wrong_installed_architecture_is_reinstalled(self):
        self.deb()
        self.state(installed={"status": "installed", "version": "7.3.1",
                              "architecture": "arm64"})
        self.run_sync()
        install = self.commands("apt-get", "install")
        self.assertEqual(len(install), 1)
        self.assertIn("--reinstall", install[0])

    def test_failed_install_refreshes_then_retries_same_local_package(self):
        path = self.deb("7.4.0")
        self.state(fail_first_install=True)
        self.run_sync()
        installs = self.commands("apt-get", "install")
        self.assertEqual(len(installs), 2)
        self.assertTrue(all(str(path) in command for command in installs))
        self.assertEqual(len(self.commands("apt-get", "update")), 1)

    def test_install_or_dependency_refresh_failure_stops_startup(self):
        self.deb("7.4.0")
        self.state(install_failure=True)
        self.run_sync(expected_code=1)
        self.assertEqual(len(self.commands("apt-get", "install")), 2)
        self.state(install_failure=False, fail_first_install=True,
                   install_attempts=0, update_failure=True)
        self.run_sync(expected_code=1)
        self.assertEqual(len(self.commands("apt-get", "install")), 3)

    def test_successful_apt_exit_with_wrong_installed_version_fails(self):
        self.deb("7.4.0")
        self.state(leave_wrong_version=True)
        self.run_sync(expected_code=1)
        self.assertEqual(len(self.commands("apt-get", "install")), 1)


if __name__ == "__main__":
    unittest.main()
