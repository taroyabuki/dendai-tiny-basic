from __future__ import annotations

from pathlib import Path
import unittest

from scripts.run_harness import run_session


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_IMAGE = REPO_ROOT / "build" / "dendai-tiny-basic.bin"


def run_usr_program(*chunks: bytes, max_steps: int = 900_000):
    image = BUILD_IMAGE.read_bytes()
    return run_session(image, list(chunks), max_steps)


def poke_lines(start_line: int, address: int, values: list[int]) -> list[bytes]:
    return [
        f"{start_line + index * 10} #({address + index})={value}\r".encode()
        for index, value in enumerate(values)
    ]


class UsrBasicTests(unittest.TestCase):
    def test_usr_one_argument_calls_machine_code_and_continues_expression(self) -> None:
        chunks = poke_lines(10, 0x1000, [0x86, 42, 0x5F, 0x39])
        chunks.extend([b"50 PRINT USR(4096)+5\r", b"60 END\r", b"RUN\r"])
        result = run_usr_program(*chunks)

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("\r\n47\r\n", result.text)
        self.assertIn("READY", result.text)
        self.assertNotIn("ERROR", result.text)

    def test_usr_two_arguments_passes_index_register(self) -> None:
        chunks = poke_lines(10, 0x1010, [0xA6, 0x01, 0xE6, 0x00, 0x39])
        chunks.extend(poke_lines(60, 0x1100, [0x12, 0x34]))
        chunks.extend([b"80 PRINT USR(4112,4352)\r", b"90 END\r", b"RUN\r"])
        result = run_usr_program(*chunks)

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("\r\n4660\r\n", result.text)
        self.assertNotIn("ERROR", result.text)

    def test_usr_three_arguments_passes_accumulators(self) -> None:
        chunks = poke_lines(10, 0x1020, [0x39])
        chunks.extend([b"20 PRINT USR(4128,4352,$1234)\r", b"30 END\r", b"RUN\r"])
        result = run_usr_program(*chunks)

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("\r\n4660\r\n", result.text)
        self.assertNotIn("ERROR", result.text)


if __name__ == "__main__":
    unittest.main()
