from __future__ import annotations

from pathlib import Path
import re
import unittest

from scripts.run_harness import build_input, run_session


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_IMAGE = REPO_ROOT / "build" / "dendai-tiny-basic.bin"
DEMOS_DIR = REPO_ROOT / "demos"


def run_basic_file(path: Path, *commands: str, max_steps: int = 2_000_000) -> str:
    return run_basic_file_result(path, *commands, max_steps=max_steps).text


def run_basic_file_result(path: Path, *commands: str, max_steps: int = 2_000_000):
    image = BUILD_IMAGE.read_bytes()
    script = build_input(path.read_text(), list(commands) if commands else ["LIST"])
    result = run_session(image, script, max_steps)
    if result.reason != "input_exhausted":
        raise AssertionError(f"{path.name} stopped with {result.reason}")
    if "ERROR" in result.text:
        raise AssertionError(f"{path.name} reported ERROR:\n{result.text}")
    return result


def extract_numeric_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip().isdigit()]


def extract_pi_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if re.fullmatch(r"[0-9.]+", line.strip())]


class BigIntBasicTests(unittest.TestCase):
    def test_support_program_files_exist(self) -> None:
        for name in [
            "mp_array.bas",
            "mp_addsub.bas",
            "mp_scale.bas",
            "mp_div_small.bas",
            "pi-010.bas",
            "pi-050.bas",
            "pi-100.bas",
        ]:
            with self.subTest(program=name):
                path = DEMOS_DIR / name
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)

    def test_mp_array_runs_and_prints_expected_values(self) -> None:
        text = run_basic_file(DEMOS_DIR / "mp_array.bas", "RUN", max_steps=800_000)
        self.assertEqual(extract_numeric_lines(text), ["5", "6", "7", "8", "9"])

    def test_mp_scale_runs_and_prints_expected_values(self) -> None:
        text = run_basic_file(DEMOS_DIR / "mp_scale.bas", "RUN", max_steps=8_000_000)
        self.assertEqual(extract_numeric_lines(text), ["1", "2500", "0", "2", "5000", "0", "10", "0", "0"])

    def test_mp_div_small_runs_and_prints_expected_values(self) -> None:
        text = run_basic_file(DEMOS_DIR / "mp_div_small.bas", "RUN", max_steps=8_000_000)
        self.assertEqual(
            extract_numeric_lines(text),
            ["0", "2000", "0", "0", "0", "0", "400", "0", "0", "0", "0", "41", "8410", "418", "4100", "0", "6", "8540", "959", "5613"],
        )

    def test_mp_addsub_runs_and_prints_expected_values(self) -> None:
        text = run_basic_file(DEMOS_DIR / "mp_addsub.bas", "RUN", max_steps=8_000_000)
        self.assertEqual(extract_numeric_lines(text), ["1", "0", "0", "0", "0", "9999", "9999", "9999"])

    def test_pi_010_runs_and_prints_expected_digits(self) -> None:
        text = run_basic_file(DEMOS_DIR / "pi-010.bas", "RUN", max_steps=10_000_000)
        self.assertEqual(extract_pi_lines(text), ["3.", "1415926535"])

    def test_two_byte_group_encoding_smoke(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        result = run_session(
            image,
            [
                b"10 LET X=4096\r",
                b"20 #(X)=62\r",
                b"30 #(X+1)=50\r",
                b"40 PRINT #(X)*100+#(X+1)\r",
                b"RUN\r",
            ],
            800_000,
        )

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("\r\n6250\r\n", result.text)
        self.assertNotIn("ERROR", result.text)

    def test_two_byte_group_addition_smoke(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        result = run_session(
            image,
            [
                b"10 LET X=4096\r",
                b"20 LET Y=4104\r",
                b"30 #(X)=99\r",
                b"40 #(X+1)=99\r",
                b"50 #(Y)=0\r",
                b"60 #(Y+1)=1\r",
                b"70 LET L=#(X+1)+#(Y+1)\r",
                b"80 LET C=0\r",
                b"90 IF L<100 THEN 120\r",
                b"100 LET L=L-100\r",
                b"110 LET C=1\r",
                b"120 LET H=#(X)+#(Y)+C\r",
                b"130 IF H<100 THEN 150\r",
                b"140 LET H=H-100\r",
                b"150 PRINT H*100+L\r",
                b"RUN\r",
            ],
            1_200_000,
        )

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("\r\n0\r\n", result.text)
        self.assertNotIn("ERROR", result.text)
