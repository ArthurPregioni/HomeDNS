#!/usr/bin/env python3
"""Check real DNS responses over UDP/TCP without external Python packages."""
import argparse
import ipaddress
import secrets
import socket
import struct


def question(domain, qtype=1):
    labels = domain.rstrip(".").encode("idna").split(b".")
    if any(not label or len(label) > 63 for label in labels):
        raise ValueError("Invalid DNS name")
    wire = b"".join(bytes([len(label)]) + label for label in labels) + b"\0"
    if len(wire) > 255:
        raise ValueError("DNS name too long")
    return wire + struct.pack("!HH", qtype, 1)


def skip_name(data, offset):
    for _ in range(128):
        if offset >= len(data):
            raise ValueError("Truncated DNS name")
        length = data[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(data):
                raise ValueError("Truncated DNS pointer")
            return offset + 2
        if length & 0xC0:
            raise ValueError("Invalid DNS label")
        offset += 1
        if length == 0:
            return offset
        offset += length
    raise ValueError("DNS name too long")


def addresses(data, txid, expected_question):
    if len(data) < 12:
        raise ValueError("Truncated DNS header")
    reply_id, flags, qd, an, _, _ = struct.unpack_from("!HHHHHH", data)
    if reply_id != txid or not flags & 0x8000 or flags & 0x0200 or qd != 1:
        raise ValueError("Unexpected or truncated DNS reply")
    offset = skip_name(data, 12) + 4
    if data[12:offset].lower() != expected_question.lower():
        raise ValueError("Unexpected DNS question")
    found = []
    for _ in range(an):
        offset = skip_name(data, offset)
        if offset + 10 > len(data):
            raise ValueError("Truncated DNS answer")
        rtype, rclass, _, length = struct.unpack_from("!HHIH", data, offset)
        offset += 10
        payload = data[offset:offset + length]
        if len(payload) != length:
            raise ValueError("Truncated DNS data")
        if rclass == 1 and ((rtype == 1 and length == 4) or (rtype == 28 and length == 16)):
            found.append(str(ipaddress.ip_address(payload)))
        offset += length
    return flags & 15, found


def receive(sock, length):
    result = bytearray()
    while len(result) < length:
        chunk = sock.recv(length - len(result))
        if not chunk:
            raise ValueError("Incomplete DNS TCP response")
        result.extend(chunk)
    return bytes(result)


def query(server, port, domain, tcp=False, qtype=1):
    ipaddress.IPv4Address(server)
    txid = secrets.randbelow(65536)
    q = question(domain, qtype)
    packet = struct.pack("!HHHHHH", txid, 0x0100, 1, 0, 0, 0) + q
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM) as sock:
        sock.settimeout(8)
        sock.connect((server, port))
        if tcp:
            sock.sendall(struct.pack("!H", len(packet)) + packet)
            data = receive(sock, struct.unpack("!H", receive(sock, 2))[0])
        else:
            sock.send(packet)
            data = sock.recv(65535)
    return addresses(data, txid, q)


def check(server, port):
    for tcp in (False, True):
        protocol = "TCP" if tcp else "UDP"
        rcode, answer = query(server, port, "example.org", tcp)
        if rcode != 0 or not answer or not all(ipaddress.ip_address(a).is_global for a in answer):
            raise RuntimeError(f"{protocol}: ordinary domain did not resolve: {rcode}, {answer}")
        for qtype in (1, 28):
            rcode, answer = query(server, port, "doubleclick.net", tcp, qtype)
            if not (rcode == 3 or (rcode == 0 and answer and all(ipaddress.ip_address(a).is_unspecified for a in answer))):
                raise RuntimeError(f"{protocol}: ad domain not blocked: {rcode}, {answer}")
        print(f"{protocol}: ordinary domain resolves; ad domain blocked (A and AAAA)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server", help="IPv4 address of the DNS server")
    parser.add_argument("--port", type=int, default=1053)
    args = parser.parse_args()
    check(args.server, args.port)
