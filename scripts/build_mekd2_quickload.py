#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


MAGIC = b"MEK6800D2"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a MAME MEK6800D2 quickload image.")
    parser.add_argument("binary", type=Path, help="Input binary to load into RAM")
    parser.add_argument("output", type=Path, help="Output .d2 file")
    parser.add_argument("--address", default="0x0100", help="Load address (default: 0x0100)")
    parser.add_argument("--ident", default="0x00", help="Quickload ident byte (default: 0x00)")
    args = parser.parse_args()

    address = int(args.address, 0)
    ident = int(args.ident, 0) & 0xFF
    payload = args.binary.read_bytes()

    data = bytearray()
    data.extend(MAGIC)
    data.extend(address.to_bytes(2, "little"))
    data.extend(len(payload).to_bytes(2, "little"))
    data.append(ident)
    data.extend(payload)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bytes(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
