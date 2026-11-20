import contextlib
import importlib.util
import io
import ipaddress
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check
import control
import install

# The build script has a hyphen in its name, as the README calls it.
spec = importlib.util.spec_from_file_location("build_android", SCRIPTS / "build-android.py")
build_android = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_android)


class InstallerDefaultsTests(unittest.TestCase):
    def test_first_configuration_is_private_and_limited_to_the_lan(self):
        lan = ipaddress.ip_network("192.168.1.0/24")
        seed = install.seed_config("admin", "$2a$12$hash", ipaddress.IPv4Address("192.168.1.10"), lan, 1053)
        self.assertEqual(seed["http"], {"address": "127.0.0.1:13000"})
        self.assertEqual(seed["users"], [{"name": "admin", "password": "$2a$12$hash"}])
        self.assertEqual(seed["dns"]["bind_hosts"], ["127.0.0.1", "192.168.1.10"])
        self.assertEqual(seed["dns"]["allowed_clients"], ["127.0.0.0/8", "192.168.1.0/24"])
        self.assertEqual(seed["dns"]["port"], 1053)
        self.assertEqual(seed["querylog"], {"enabled": False})
        self.assertTrue(all(server.startswith("https://") for server in seed["dns"]["upstream_dns"]))
        json.dumps(seed)

    def test_cache_defaults_reach_both_the_first_configuration_and_every_reinstall(self):
        seed = install.seed_config("admin", "hash", "192.168.1.10", "192.168.1.0/24", 1053)["dns"]
        settings = install.dns_settings()
        for target in (seed, settings):
            self.assertIs(target["cache_enabled"], True)
            self.assertIs(target["cache_optimistic"], True)
            self.assertEqual(target["cache_size"], 16 * 1024 * 1024)
        self.assertEqual(settings["upstream_dns"], seed["upstream_dns"])
        self.assertEqual(settings["fallback_dns"], [])
        self.assertIs(settings["resolve_clients"], False)


class BuildTests(unittest.TestCase):
    def test_only_the_shim_may_be_added_to_the_upstream_sources(self):
        self.assertEqual(build_android.stray_go_files("homedns_android_argv.go\n"), [])
        self.assertEqual(build_android.stray_go_files(""), [])
        self.assertEqual(build_android.stray_go_files("homedns_android_argv.go\ninternal/home/extra.go\nmain_extra.go\n"),
                         ["internal/home/extra.go", "main_extra.go"])


class ControlTests(unittest.TestCase):
    def action(self, name, outcome=None):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "runtime.json").write_text(json.dumps({"dns_port": 1053}))
            calls = []

            def fake(server, port):
                calls.append((server, port))
                if outcome:
                    raise outcome
            output = io.StringIO()
            with mock.patch.object(control, "CONFIG", Path(temporary)), mock.patch.object(check, "check", fake), \
                    mock.patch.object(sys, "argv", ["control.py", name]), mock.patch.dict(os.environ, {"PREFIX": "/data/data/com.termux/files/usr"}), \
                    contextlib.redirect_stderr(output):
                try:
                    control.main()
                    code = 0
                except SystemExit as stop:
                    code = stop.code
            return code, calls, output.getvalue()

    def test_check_queries_the_local_listener_and_reports_a_failure_plainly(self):
        self.assertEqual(self.action("check")[:2], (0, [("127.0.0.1", 1053)]))
        code, calls, output = self.action("check", RuntimeError("UDP: ad domain not blocked: 0, ['203.0.113.9']"))
        self.assertEqual((code, calls), (1, [("127.0.0.1", 1053)]))
        self.assertIn("FAIL: UDP: ad domain not blocked", output)
        self.assertNotIn("Traceback", output)

    def test_tune_sends_only_the_cache_settings_to_the_running_service(self):
        calls = []

        def fake(path, data=None, **options):
            calls.append((path, data))
            return {"cache_enabled": True, "cache_size": 16777216, "cache_optimistic": True, "upstream_dns": ["kept"]}
        output = io.StringIO()
        with mock.patch.object(control, "api", fake), mock.patch.object(sys, "argv", ["control.py", "tune"]), \
                mock.patch.dict(os.environ, {"PREFIX": "/data/data/com.termux/files/usr"}), contextlib.redirect_stdout(output):
            control.main()
        self.assertEqual(calls, [("/dns_config", {"cache_enabled": True, "cache_size": 16 * 1024 * 1024, "cache_optimistic": True}),
                                 ("/dns_info", None)])
        self.assertEqual(json.loads(output.getvalue()), {"cache_enabled": True, "cache_size": 16777216, "cache_optimistic": True})

    def test_outside_termux_nothing_is_attempted(self):
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["control.py", "status"]), mock.patch.dict(os.environ, {}, clear=True), \
                contextlib.redirect_stderr(output), self.assertRaises(SystemExit) as stop:
            control.main()
        self.assertEqual(stop.exception.code, 2)
        self.assertIn("Termux", output.getvalue())


class CheckCommandTests(unittest.TestCase):
    def test_no_answer_is_one_line_and_a_failing_status(self):
        output = io.StringIO()
        with mock.patch.object(check, "check", side_effect=OSError("timed out")), contextlib.redirect_stdout(output):
            self.assertEqual(check.main(["192.168.1.10", "--port", "1053"]), 1)
        self.assertEqual(output.getvalue().strip(), "FAIL: timed out")
        with mock.patch.object(check, "check", return_value=None) as called:
            self.assertEqual(check.main(["192.168.1.10"]), 0)
        called.assert_called_once_with("192.168.1.10", 1053)


class BindingsTests(unittest.TestCase):
    def test_only_dns_binding_changes(self):
        config = "http:\n  address: 127.0.0.1:13000\ndns:\n  bind_hosts:\n    - 127.0.0.1\n  port: 1053\n"
        result = install.expose_dns(config, "192.168.1.10")
        self.assertIn("address: 127.0.0.1:13000", result)
        self.assertIn("    - 192.168.1.10", result)
        self.assertEqual(install.expose_dns(result, "192.168.1.10"), result)

    def test_unknown_bindings_refused(self):
        for config in ("", "dns:\n  bind_hosts: [127.0.0.1]\n", "  bind_hosts:\n    - ::1\n",
                       "  bind_hosts:\n    - 127.0.0.1\n    - 10.0.0.1\n    - 10.0.0.2\n  port: 1053\n"):
            with self.assertRaises(ValueError):
                install.expose_dns(config, "192.168.1.10")


class DNSResponseTests(unittest.TestCase):
    def packet(self, flags=0x8180, txid=1234, payload=b"\x00\x00\x00\x00"):
        q = check.question("doubleclick.net")
        answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + payload
        return struct.pack("!HHHHHH", txid, flags, 1, 1, 0, 0) + q + answer

    def test_real_blocking_answer(self):
        self.assertEqual(check.addresses(self.packet(), 1234, check.question("doubleclick.net")), (0, ["0.0.0.0"]))

    def test_wrong_txid_question_or_truncated_response_refused(self):
        for packet, txid, q in ((self.packet(), 1235, check.question("doubleclick.net")),
                                 (self.packet(), 1234, check.question("example.org")),
                                 (self.packet(flags=0x8380), 1234, check.question("doubleclick.net")),
                                 (self.packet()[:-1], 1234, check.question("doubleclick.net"))):
            with self.assertRaises(ValueError):
                check.addresses(packet, txid, q)

    def test_short_packets_and_names_refused(self):
        with self.assertRaises(ValueError):
            check.addresses(b"\x00", 1234, check.question("example.org"))
        with self.assertRaises(ValueError):
            check.skip_name(b"\xc0", 0)
        with self.assertRaises(ValueError):
            check.question("a" * 64 + ".org")

    def test_tcp_partial_reads_and_disconnect(self):
        class Sock:
            def __init__(self, value): self.value = io.BytesIO(value)
            def recv(self, size): return self.value.read(min(size, 2))
        self.assertEqual(check.receive(Sock(b"hello"), 5), b"hello")
        with self.assertRaises(ValueError):
            check.receive(Sock(b"hi"), 5)


if __name__ == "__main__":
    unittest.main()
