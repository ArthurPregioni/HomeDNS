import importlib.util
import io
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check
import install


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
