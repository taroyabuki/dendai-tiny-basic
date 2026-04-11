#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize dendai-tiny-basic dump into a raw binary image.")
    parser.add_argument("dump", type=Path, help="Input dump text file")
    parser.add_argument("output", type=Path, help="Output raw binary")
    parser.add_argument(
        "--base",
        default="0x0100",
        help="Load base address used for reporting and correction addresses (default: 0x0100)",
    )
    parser.add_argument(
        "--corrections",
        type=Path,
        help="Optional JSON file mapping absolute addresses to replacement byte values",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report path",
    )
    return parser.parse_args()


def parse_u8(value: str) -> int:
    return int(value, 0) & 0xFF


ADDRESS_PREFIX = re.compile(r"^\s*([0-9A-Fa-f]{4}):\s*(.*)$")


AUTO_FIX_PATCHES = {
    0x019F: 0xBD,
    0x01A0: 0x09,
    0x01A1: 0x50,
    0x0950: 0xBD,
    0x0951: 0x06,
    0x0952: 0x9E,
    0x0953: 0x6D,
    0x0954: 0x00,
    0x0955: 0x26,
    0x0956: 0x0B,
    0x0957: 0x80,
    0x0958: 0x0A,
    0x0959: 0xC2,
    0x095A: 0x00,
    0x095B: 0x97,
    0x095C: 0x09,
    0x095D: 0xD7,
    0x095E: 0x08,
    0x095F: 0x7E,
    0x0960: 0x01,
    0x0961: 0xDC,
    0x0962: 0x39,
}


def parse_tokens(text: str, base: int) -> list[int]:
    values: list[int] = []
    index = 0
    cursor = 0
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        match = ADDRESS_PREFIX.match(raw_line)
        if match:
            address = int(match.group(1), 16)
            cursor = address - base
            if cursor < 0:
                raise ValueError(f"line {line_no} address before base: {address:#06x} < {base:#06x}")
            line = match.group(2).strip()
            if not line:
                continue

        if cursor > len(values):
            raise ValueError(f"line {line_no} introduces a gap before offset {cursor:#06x}")

        for token in line.split():
            if len(token) != 2:
                raise ValueError(f"line {line_no} token {index} has invalid width: {token!r}")
            try:
                value = int(token, 16)
            except ValueError as exc:
                raise ValueError(f"line {line_no} token {index} is not hex: {token!r}") from exc
            if cursor == len(values):
                values.append(value)
            else:
                values[cursor] = value
            cursor += 1
            index += 1
    return values


def load_corrections(path: Path | None) -> dict[int, int]:
    if path is None:
        return {}
    raw = json.loads(path.read_text())
    corrections: dict[int, int] = {}
    for key, value in raw.items():
        corrections[int(key, 0)] = parse_u8(str(value))
    return corrections


def apply_patch_bytes(values: list[int], base: int, patch: dict[int, int]) -> list[dict[str, str]]:
    applied: list[dict[str, str]] = []
    for address, replacement in sorted(patch.items()):
        offset = address - base
        if offset < 0:
            raise ValueError(f"patch address before base: {address:#06x}")
        while offset >= len(values):
            values.append(0)
        old = values[offset]
        values[offset] = replacement
        applied.append(
            {
                "address": f"{address:#06x}",
                "old": f"{old:#04x}",
                "new": f"{replacement:#04x}",
            }
        )
    return applied


def main() -> int:
    args = parse_args()
    base = int(args.base, 0)
    values = parse_tokens(args.dump.read_text(), base)
    corrections = load_corrections(args.corrections)
    applied: list[dict[str, str]] = []
    applied.extend(apply_patch_bytes(values, base, AUTO_FIX_PATCHES))
    if corrections:
        for address, replacement in sorted(corrections.items()):
            offset = address - base
            if offset < 0 or offset >= len(values):
                raise ValueError(f"correction address out of range: {address:#06x}")
            old = values[offset]
            values[offset] = replacement
            applied.append(
                {
                    "address": f"{address:#06x}",
                    "old": f"{old:#04x}",
                    "new": f"{replacement:#04x}",
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bytes(values))

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "dump": str(args.dump),
                    "output": str(args.output),
                    "base": f"{base:#06x}",
                    "size": len(values),
                    "end": f"{base + len(values) - 1:#06x}",
                    "applied_corrections": applied,
                },
                indent=2,
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
