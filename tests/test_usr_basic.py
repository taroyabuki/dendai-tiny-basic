from __future__ import annotations

from pathlib import Path
import unittest

from scripts.run_harness import CompatibilityOptions, run_session


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_IMAGE = REPO_ROOT / "build" / "dendai-tiny-basic.bin"


def run_usr_program(*chunks: bytes, max_steps: int = 900_000, compatibility: CompatibilityOptions | None = None):
    image = BUILD_IMAGE.read_bytes()
    return run_session(image, list(chunks), max_steps, compatibility=compatibility)


class UsrBasicTests(unittest.TestCase):
    def test_usr_stub_returns_zero_for_documented_argument_counts(self) -> None:
        cases = [
            [b"10 PRINT USR(0)\r", b"RUN\r"],
            [b"10 PRINT USR(0,1)\r", b"RUN\r"],
            [b"10 PRINT USR(0,1,2)\r", b"RUN\r"],
        ]

        for chunks in cases:
            with self.subTest(chunks=chunks):
                result = run_usr_program(*chunks)

                self.assertEqual(result.reason, "input_exhausted")
                self.assertIn("\r\n0\r\n", result.text)
                self.assertIn("READY", result.text)
                self.assertNotIn("ERROR", result.text)

    def test_usr_stub_can_continue_arithmetic_expression(self) -> None:
        result = run_usr_program(b"10 PRINT USR(0)+5\r", b"RUN\r")

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("\r\n5\r\n", result.text)
        self.assertNotIn("ERROR", result.text)

    def test_usr_stub_skips_nested_argument_expressions(self) -> None:
        result = run_usr_program(
            b"10 PRINT USR((1+2),(3+4),MOD(5,2))+9\r",
            b"RUN\r",
        )

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("\r\n9\r\n", result.text)
        self.assertNotIn("ERROR", result.text)

    def test_usr_raw_rom_path_still_reaches_missing_machine_code_entry_without_stub(self) -> None:
        result = run_usr_program(
            b"10 PRINT USR(0)\r",
            b"RUN\r",
            max_steps=700_000,
            compatibility=CompatibilityOptions(usr_stub=False),
        )

        self.assertEqual(result.reason, "Opcode $00 not implemented at $1836")
        self.assertNotIn("\r\n0\r\n", result.text)


if __name__ == "__main__":
    unittest.main()
