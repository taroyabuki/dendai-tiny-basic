#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = REPO_ROOT / "build"


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"required tool not found: {name}")


def run_command(command: list[str], *, stdout_path: Path | None = None) -> None:
    kwargs: dict[str, object] = {
        "cwd": REPO_ROOT,
        "check": True,
        "text": True,
    }
    if stdout_path is not None:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        with stdout_path.open("w") as handle:
            subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, **kwargs)
        return
    subprocess.run(command, **kwargs)


def assert_same_bytes(left: Path, right: Path) -> None:
    if left.read_bytes() != right.read_bytes():
        raise SystemExit(f"artifact mismatch: {left} != {right}")


def assert_same_text(left: Path, right: Path) -> None:
    if left.read_text() != right.read_text():
        raise SystemExit(f"artifact mismatch: {left} != {right}")


def verify_quickload_wrapper(bin_path: Path, d2_path: Path) -> None:
    d2_image = d2_path.read_bytes()
    bin_image = bin_path.read_bytes()
    if d2_image[:9] != b"MEK6800D2":
        raise SystemExit(f"artifact mismatch: {d2_path} has invalid magic")
    if d2_image[9:11] != bytes([0x00, 0x01]):
        raise SystemExit(f"artifact mismatch: {d2_path} has unexpected load address")
    if int.from_bytes(d2_image[11:13], 'little') != len(bin_image):
        raise SystemExit(f"artifact mismatch: {d2_path} has unexpected payload length")
    if d2_image[13] != 0x00:
        raise SystemExit(f"artifact mismatch: {d2_path} has unexpected ident")
    if d2_image[14:] != bin_image:
        raise SystemExit(f"artifact mismatch: {d2_path} payload does not match {bin_path}")


def rebuild() -> None:
    require_tool("crasm")
    require_tool("objcopy")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            sys.executable,
            "scripts/normalize_dump.py",
            "dendai-tiny-basic.dump",
            "build/dendai-tiny-basic.bin",
        ]
    )
    run_command([sys.executable, "scripts/disassemble.py", "build/dendai-tiny-basic.bin", "dendai-tiny-basic.asm"])
    run_command(
        [
            sys.executable,
            "scripts/build_mekd2_quickload.py",
            "build/dendai-tiny-basic.bin",
            "build/dendai-tiny-basic.d2",
        ]
    )
    with tempfile.TemporaryDirectory(dir=BUILD_DIR) as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        temp_srec = temp_dir / "reassembled.srec"
        temp_rawbin = temp_dir / "reassembled.rawbin"
        run_command(["crasm", "-x", "-o", str(temp_srec), "dendai-tiny-basic.asm"])
        run_command(["objcopy", "-I", "srec", "-O", "binary", str(temp_srec), str(temp_rawbin)])
        assert_same_bytes(BUILD_DIR / "dendai-tiny-basic.bin", temp_rawbin)


def check() -> None:
    required = [
        REPO_ROOT / "dendai-tiny-basic.dump",
        REPO_ROOT / "dendai-tiny-basic.asm",
        BUILD_DIR / "dendai-tiny-basic.bin",
        BUILD_DIR / "dendai-tiny-basic.d2",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise SystemExit(f"missing artifacts: {missing_text}")

    with tempfile.TemporaryDirectory() as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        temp_bin = temp_dir / "normalized.bin"
        temp_asm = temp_dir / "disassembled.asm"
        run_command([sys.executable, "scripts/normalize_dump.py", "dendai-tiny-basic.dump", str(temp_bin)])
        run_command([sys.executable, "scripts/disassemble.py", str(temp_bin), str(temp_asm)])
        assert_same_bytes(BUILD_DIR / "dendai-tiny-basic.bin", temp_bin)
        assert_same_text(REPO_ROOT / "dendai-tiny-basic.asm", temp_asm)
    verify_quickload_wrapper(BUILD_DIR / "dendai-tiny-basic.bin", BUILD_DIR / "dendai-tiny-basic.d2")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild and verify generated Tiny BASIC artifacts.")
    parser.add_argument("--check", action="store_true", help="Verify artifact consistency without rebuilding.")
    parser.add_argument("--test", action="store_true", help="Run pytest -q after rebuilding or checking.")
    args = parser.parse_args()

    if args.check:
        check()
    else:
        rebuild()
        check()

    if args.test:
        run_command([sys.executable, "-m", "pytest", "-q"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
