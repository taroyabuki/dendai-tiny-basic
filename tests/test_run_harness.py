from __future__ import annotations

from collections import deque
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from scripts.run_harness import (
    CPU6800,
    DEFAULT_MONITOR_STACK,
    MONITOR_STACK_SLOT,
    Monitor,
    build_input,
    format_memory,
    format_transcript_for_display,
    normalize_command,
    parse_memory_ranges,
    render_output,
    run_repl_session,
    run_session,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_IMAGE = REPO_ROOT / "build" / "dendai-tiny-basic.bin"
SOURCE_DUMP = REPO_ROOT / "dendai-tiny-basic.dump"
MEKD2_QUICKLOAD = REPO_ROOT / "build" / "dendai-tiny-basic.d2"
RUN_HARNESS = REPO_ROOT / "scripts" / "run_harness.py"
UPDATE_ARTIFACTS = REPO_ROOT / "scripts" / "update_artifacts.py"
PDF_KEYWORDS = {
    "LIST",
    "LOAD",
    "RUN",
    "EX",
    "AUTO",
    "NEW",
    "LET",
    "IF",
    "GOTO",
    "GOSUB",
    "RET",
    "NEXT",
    "FOR",
    "THEN",
    "REM",
    "PRINT",
    "INPUT",
    "PR",
    "IN",
    "STOP",
    "END",
    "RND(",
    "ABS(",
    "MOD(",
    "USR(",
    "TO",
    "STEP",
    "CHR(",
    "TAB(",
}


def read_dump_byte(address: int) -> int:
    for line in SOURCE_DUMP.read_text().splitlines():
        if not line:
            continue
        base_text, data_text = line.split(":", 1)
        base = int(base_text, 16)
        values = [int(token, 16) for token in data_text.split()]
        offset = address - base
        if 0 <= offset < len(values):
            return values[offset]
    raise AssertionError(f"address ${address:04X} not found in {SOURCE_DUMP}")


class RunHarnessTests(unittest.TestCase):
    def patched_image(self, replacements: dict[int, int]) -> bytes:
        image = bytearray(BUILD_IMAGE.read_bytes())
        for addr, value in replacements.items():
            image[addr - 0x0100] = value
        return bytes(image)

    def assert_numeric_result(self, text: str) -> None:
        self.assertRegex(text, r"\r\n[0-9]+\r\n\r\nREADY\r\n#$")

    def test_monitor_reads_only_when_requested(self) -> None:
        provider = mock.Mock(side_effect=[b"AB", b"C"])
        monitor = Monitor(deque(), list(b"arbitrary output"), input_provider=provider)
        provider.assert_not_called()
        self.assertEqual(monitor.get_char(), ord("A"))
        self.assertEqual(monitor.get_char(), ord("B"))
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(monitor.get_char(), ord("C"))
        self.assertEqual(provider.call_count, 2)

    def test_build_input_uses_default_commands_after_program_lines(self) -> None:
        script = build_input("10 PRINT 1\n20 END\n")

        self.assertEqual(script, [b"10 PRINT 1\r", b"20 END\r", b"LIST\r", b"RUN\r"])

    def test_build_input_accepts_explicit_commands_without_program_lines(self) -> None:
        script = build_input("", ["AUTO 10", "LIST"])

        self.assertEqual(script, [b"AUTO 10\r", b"LIST\r"])

    def test_normalize_command_preserves_immediate_statement(self) -> None:
        self.assertEqual(normalize_command("PRINT 2+2"), b"PRINT 2+2\r")
        self.assertEqual(normalize_command("LET A=1:PRINT A"), b"LET A=1:PRINT A\r")

    def test_normalize_command_leaves_direct_commands_and_numbered_lines_unchanged(self) -> None:
        self.assertEqual(normalize_command("LIST"), b"LIST\r")
        self.assertEqual(normalize_command("10 PRINT 1"), b"10 PRINT 1\r")

    def test_render_output_strips_padding_and_nonprinting_controls(self) -> None:
        text = render_output([0x0D, 0x0A, 0xFF, 0x7F, 0x02, ord("A"), 0x03, 0x07, ord("#")])

        self.assertEqual(text, "\r\nA#")

    def test_format_transcript_for_display_hides_hash_prompt_lines(self) -> None:
        self.assertEqual(
            format_transcript_for_display("\r\nREADY\r\n#\r\n#\r\n1\r\n\r\nREADY\r\n#"),
            "\r\nREADY\r\n1\r\n\r\nREADY",
        )

    def test_format_transcript_for_display_keeps_inline_hash_text(self) -> None:
        self.assertEqual(format_transcript_for_display("\r\n10 LET A=#(1)\r\n"), "\r\n10 LET A=#(1)\r\n")

    def test_parse_memory_ranges_accepts_hex_and_decimal(self) -> None:
        self.assertEqual(parse_memory_ranges(["0x00FA:8", "16:4"]), [(0x00FA, 8), (16, 4)])

    def test_format_memory_renders_hex_bytes(self) -> None:
        cpu = CPU6800(bytes([0x12, 0x34, 0x56]), Monitor(input_bytes=deque(), output=[]))

        self.assertEqual(format_memory(cpu, 0x0100, 3), "12 34 56")

    def test_run_session_can_stop_before_executing_requested_pc(self) -> None:
        result = run_session(bytes([0x01, 0x01]), [], 10, stop_pcs={0x0101})

        self.assertEqual(result.reason, "stopped_at_pc $0101")
        self.assertEqual(result.cpu.pc, 0x0101)

    def test_run_session_can_watch_writes_to_specific_addresses(self) -> None:
        result = run_session(bytes([0x86, 0x12, 0x97, 0x13]), [], 2, watch_addrs={0x0013})

        self.assertEqual(result.reason, "step_limit")
        self.assertEqual(result.watch_log, ["pc=0102 addr=0013 00->12"])

    def test_tpa_sets_bits_7_and_6(self) -> None:
        cpu = CPU6800(bytes([0x07]), Monitor(input_bytes=deque(), output=[]))
        cpu.c = 1
        cpu.z = 1

        cpu.step()

        self.assertEqual(cpu.a, 0xC5)

    def test_bsr_stack_layout_matches_rts_expectation(self) -> None:
        cpu = CPU6800(bytes([0x8D, 0x01, 0x01]), Monitor(input_bytes=deque(), output=[]))

        cpu.step()

        self.assertEqual(cpu.pc, 0x0103)
        self.assertEqual(cpu.sp, 0xA045)
        self.assertEqual(cpu.read8(cpu.sp + 1), 0x01)
        self.assertEqual(cpu.read8(cpu.sp + 2), 0x0102 & 0xFF)

    def test_monitor_stack_slot_starts_with_default_pointer(self) -> None:
        cpu = CPU6800(bytes([0x01]), Monitor(input_bytes=deque(), output=[]))

        self.assertEqual(cpu.read16(MONITOR_STACK_SLOT), DEFAULT_MONITOR_STACK)

    def test_current_rom_stop_handler_calls_internal_l067b(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x01AB - 0x0100 : 0x01B3 - 0x0100], bytes([0xBD, 0x03, 0x2C, 0xBD, 0x06, 0x7B, 0x20, 0x1D]))

    def test_current_rom_auto_handler_jumps_through_helper(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x019F - 0x0100 : 0x01A2 - 0x0100], bytes([0xBD, 0x09, 0x50]))
        self.assertEqual(
            image[0x0950 - 0x0100 : 0x0963 - 0x0100],
            bytes([0xBD, 0x06, 0x9E, 0x6D, 0x00, 0x26, 0x0B, 0x80, 0x0A, 0xC2, 0x00, 0x97, 0x09, 0xD7, 0x08, 0x7E, 0x01, 0xDC, 0x39]),
        )

    def test_current_rom_auto_prompt_uses_0008_as_line_seed(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x0116 - 0x0100 : 0x011F - 0x0100], bytes([0x86, 0x0A, 0x5F, 0xCE, 0x00, 0x08, 0xBD, 0x04, 0x93]))

    def test_source_dump_has_fixed_auto_prompt_seed_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x011B), 0x08)

    def test_source_dump_has_fixed_division_branch_offset_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x03B3), 0x08)

    def test_source_dump_has_fixed_stack_restore_opcode_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x01DC), 0x8E)

    def test_source_dump_has_fixed_line_replace_bytes(self) -> None:
        self.assertEqual(read_dump_byte(0x01FC), 0x04)
        self.assertEqual(read_dump_byte(0x01FD), 0x58)

    def test_source_dump_has_fixed_compare_sbc_operand_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x02A6), 0xB8)

    def test_source_dump_has_fixed_shift_sequence_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x02DD), 0x48)

    def test_source_dump_has_fixed_branch_helper_call_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x02E6), 0x8D)

    def test_source_dump_has_fixed_error_code_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x0392), 0x82)

    def test_source_dump_has_fixed_shift_operand_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x03B6), 0x6C)

    def test_source_dump_has_fixed_eorb_operand_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x03D6), 0xE8)

    def test_source_dump_usr_argument_branch_uses_bsr(self) -> None:
        self.assertEqual(read_dump_byte(0x05F7), 0x8D)

    def test_source_dump_has_fixed_for_keyword_length_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x0736), 0x08)

    def test_source_dump_has_fixed_for_error_operand_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x0743), 0x00)

    def test_source_dump_has_fixed_monitor_output_call_byte(self) -> None:
        self.assertEqual(read_dump_byte(0x0850), 0x8D)

    def test_current_rom_ready_banner_contains_ff_padding_bytes(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x0933 - 0x0100 : 0x093B - 0x0100], bytes([0x0D, 0x0A, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00]))

    def test_current_rom_has_fixed_stack_restore_opcode_and_line_replace_bytes(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x01DC - 0x0100 : 0x01DF - 0x0100], bytes([0x8E, 0xA0, 0x47]))
        self.assertEqual(image[0x01FC - 0x0100 : 0x01FE - 0x0100], bytes([0x04, 0x58]))

    def test_current_rom_has_fixed_compare_sbc_operand_byte(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x02A6 - 0x0100], 0xB8)

    def test_current_rom_has_fixed_shift_sequence_byte(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x02DD - 0x0100], 0x48)

    def test_current_rom_has_fixed_branch_helper_call_byte(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x02E6 - 0x0100], 0x8D)

    def test_current_rom_has_fixed_error_code_byte(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x0392 - 0x0100], 0x82)

    def test_current_rom_has_fixed_shift_operand_byte(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x03B6 - 0x0100], 0x6C)

    def test_current_rom_has_fixed_eorb_operand_byte(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x03D6 - 0x0100], 0xE8)

    def test_current_rom_usr_argument_branch_uses_bsr(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x05F7 - 0x0100 : 0x05F9 - 0x0100], bytes([0x8D, 0x18]))

    def test_current_rom_has_fixed_for_keyword_length_byte(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x0736 - 0x0100], 0x08)

    def test_current_rom_has_fixed_for_error_operand_byte(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x0743 - 0x0100], 0x00)

    def test_current_rom_has_fixed_monitor_output_call_byte(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(image[0x0850 - 0x0100], 0x8D)

    def test_mekd2_quickload_wraps_current_binary_image(self) -> None:
        quickload = MEKD2_QUICKLOAD.read_bytes()
        image = BUILD_IMAGE.read_bytes()

        self.assertEqual(quickload[:9], b"MEK6800D2")
        self.assertEqual(quickload[9:11], bytes([0x00, 0x01]))
        self.assertEqual(int.from_bytes(quickload[11:13], "little"), len(image))
        self.assertEqual(quickload[13], 0x00)
        self.assertEqual(quickload[14:], image)

    def test_update_artifacts_check_mode_succeeds(self) -> None:
        result = subprocess.run(
            [sys.executable, str(UPDATE_ARTIFACTS), "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_batch_mode_still_prints_summary_and_transcript(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RUN_HARNESS), str(BUILD_IMAGE), "--command", "10 PRINT 1", "--command", "RUN"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("reason: input_exhausted", result.stdout)
        self.assertIn("--- transcript start ---", result.stdout)
        self.assertIn("READY", result.stdout)
        self.assertIn("1", result.stdout)
        self.assertNotRegex(result.stdout, r"(?m)^#$")

    def test_cli_without_program_or_commands_enters_repl_mode(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RUN_HARNESS), str(BUILD_IMAGE)],
            cwd=REPO_ROOT,
            input="10 PRINT 1\nRUN\n",
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("READY", result.stdout)
        self.assertIn("#", result.stdout)
        self.assertIn("1", result.stdout)
        self.assertNotIn("reason:", result.stdout)
        self.assertNotIn("--- transcript start ---", result.stdout)

    def test_cli_repl_runs_immediate_print_without_error_180(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RUN_HARNESS), str(BUILD_IMAGE)],
            cwd=REPO_ROOT,
            input="PRINT 2+2\n",
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("4", result.stdout)
        self.assertIn("READY", result.stdout)
        self.assertNotIn("ERROR 180", result.stdout)
        self.assertNotIn("reason:", result.stdout)

    def test_cli_repl_handles_input_prompt_from_stdin(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RUN_HARNESS), str(BUILD_IMAGE)],
            cwd=REPO_ROOT,
            input="10 INPUT A\n20 PRINT A\nRUN\n5\n",
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("? ", result.stdout)
        self.assertIn("5", result.stdout)
        self.assertIn("READY", result.stdout)
        self.assertNotIn("reason:", result.stdout)

    def test_cli_repl_exits_cleanly_on_eof_after_prompt(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RUN_HARNESS), str(BUILD_IMAGE)],
            cwd=REPO_ROOT,
            input="",
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("READY", result.stdout)
        self.assertIn("#", result.stdout)
        self.assertNotIn("reason:", result.stdout)
        self.assertNotIn("--- transcript start ---", result.stdout)

    def test_repl_keyboard_interrupt_sends_break_and_keeps_repl_alive(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        class InterruptThenEof:
            def __init__(self) -> None:
                self.calls = 0

            def readline(self) -> str:
                self.calls += 1
                if self.calls == 1:
                    raise KeyboardInterrupt
                return ""

        stdin = InterruptThenEof()
        stdout = io.StringIO()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout):
            result = run_repl_session(image, 500_000)

        self.assertEqual(result.reason, "stdin_eof")
        self.assertGreaterEqual(result.text.count("READY"), 2)
        self.assertTrue(result.text.rstrip().endswith("#"))

    def test_auto_single_argument_enters_numbered_prompt_without_error(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        result = run_session(image, [b"AUTO 10\r", b"PRINT 1\r"], 500_000)

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("\r\n10 ", result.text)
        self.assertIn("\r\n20 ", result.text)
        self.assertNotIn("ERROR", result.text)

    def test_unpatched_auto_single_argument_still_returns_early_at_01aa(self) -> None:
        image = bytearray(BUILD_IMAGE.read_bytes())
        image[0x019F - 0x0100 : 0x01A2 - 0x0100] = bytes([0xBD, 0x06, 0x9E])

        result = run_session(
            bytes(image),
            [b"AUTO 10\r"],
            300_000,
            stop_pcs={0x01AA},
        )

        self.assertEqual(result.reason, "stopped_at_pc $01AA")
        self.assertEqual(result.cpu.x, 0x0037)
        self.assertEqual(format_memory(result.cpu, result.cpu.x, 4), "00 00 00 00")

    def test_for_next_raw_rom_runs_loop_body_and_documented_variants(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "default_step",
                "chunks": [b"10 FOR I=1 TO 2\r", b"20 PRINT I\r", b"30 NEXT I\r", b"40 END\r", b"RUN\r"],
                "contains": ["\r\n1\r\n", "\r\n2\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "following_line",
                "chunks": [
                    b"10 FOR I=1 TO 2 STEP 1\r",
                    b"20 PRINT I\r",
                    b"30 NEXT I\r",
                    b"40 PRINT 9\r",
                    b"50 END\r",
                    b"RUN\r",
                ],
                "contains": ["\r\n1\r\n", "\r\n2\r\n", "\r\n9\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "negative_step",
                "chunks": [b"10 FOR I=2 TO 1 STEP -1\r", b"20 PRINT I\r", b"30 NEXT I\r", b"40 END\r", b"RUN\r"],
                "contains": ["\r\n2\r\n", "\r\n1\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "nested_loops",
                "chunks": [
                    b"10 FOR I=1 TO 2\r",
                    b"20 FOR J=1 TO 2\r",
                    b"30 PRINT I*10+J\r",
                    b"40 NEXT J\r",
                    b"50 NEXT I\r",
                    b"60 END\r",
                    b"RUN\r",
                ],
                "contains": ["\r\n11\r\n", "\r\n12\r\n", "\r\n21\r\n", "\r\n22\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "nested_across_gosub",
                "chunks": [
                    b"10 FOR I=1 TO 2\r",
                    b"20 GOSUB 100\r",
                    b"30 NEXT I\r",
                    b"40 END\r",
                    b"100 FOR J=1 TO 2\r",
                    b"110 PRINT I*10+J\r",
                    b"120 NEXT J\r",
                    b"130 RETURN\r",
                    b"RUN\r",
                ],
                "contains": ["\r\n11\r\n", "\r\n12\r\n", "\r\n21\r\n", "\r\n22\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "variable_bound_expressions",
                "chunks": [
                    b"10 LET A=1\r",
                    b"20 LET B=1\r",
                    b"30 FOR I=A+B TO A+B+2 STEP 1\r",
                    b"40 PRINT I\r",
                    b"50 NEXT I\r",
                    b"60 END\r",
                    b"RUN\r",
                ],
                "contains": ["\r\n2\r\n", "\r\n3\r\n", "\r\n4\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "next_without_variable",
                "chunks": [b"10 FOR I=1 TO 2\r", b"20 PRINT I\r", b"30 NEXT\r", b"40 END\r", b"RUN\r"],
                "contains": ["\r\n1\r\n", "\r\n2\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "next_wrong_variable",
                "chunks": [b"10 FOR I=1 TO 2\r", b"20 NEXT J\r", b"RUN\r"],
                "contains": ["ERROR 220", "READY"],
                "not_contains": ["\r\n1\r\n", "\r\n2\r\n"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], 1_500_000)

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)
                for value in case["not_contains"]:
                    self.assertNotIn(value, result.text)

    def test_incb_updates_register_and_overflow_flag(self) -> None:
        cpu = CPU6800(bytes([0x5C]), Monitor(input_bytes=deque(), output=[]))
        cpu.b = 0x7F

        cpu.step()

        self.assertEqual(cpu.b, 0x80)
        self.assertEqual(cpu.v, 1)
        self.assertEqual(cpu.n, 1)
        self.assertEqual(cpu.z, 0)

    def test_lsrd_shifts_16bit_d_register(self) -> None:
        cpu = CPU6800(bytes([0x04]), Monitor(input_bytes=deque(), output=[]))
        cpu.a = 0x12
        cpu.b = 0x35

        cpu.step()

        self.assertEqual(cpu.a, 0x09)
        self.assertEqual(cpu.b, 0x1A)
        self.assertEqual(cpu.c, 1)
        self.assertEqual(cpu.n, 0)
        self.assertEqual(cpu.z, 0)
        self.assertEqual(cpu.v, 1)

    def test_asld_shifts_16bit_d_register(self) -> None:
        cpu = CPU6800(bytes([0x05]), Monitor(input_bytes=deque(), output=[]))
        cpu.a = 0x80
        cpu.b = 0x01

        cpu.step()

        self.assertEqual(cpu.a, 0x00)
        self.assertEqual(cpu.b, 0x02)
        self.assertEqual(cpu.c, 1)
        self.assertEqual(cpu.n, 0)
        self.assertEqual(cpu.z, 0)
        self.assertEqual(cpu.v, 1)

    def test_rora_rotates_a_through_carry(self) -> None:
        cpu = CPU6800(bytes([0x46]), Monitor(input_bytes=deque(), output=[]))
        cpu.a = 0x81
        cpu.c = 1

        cpu.step()

        self.assertEqual(cpu.a, 0xC0)
        self.assertEqual(cpu.c, 1)
        self.assertEqual(cpu.n, 1)
        self.assertEqual(cpu.z, 0)
        self.assertEqual(cpu.v, 0)

    def test_bvc_branches_when_overflow_clear(self) -> None:
        cpu = CPU6800(bytes([0x28, 0x01, 0x01]), Monitor(input_bytes=deque(), output=[]))
        cpu.v = 0

        cpu.step()

        self.assertEqual(cpu.pc, 0x0103)

    def test_bvs_branches_when_overflow_set(self) -> None:
        cpu = CPU6800(bytes([0x29, 0x01, 0x01]), Monitor(input_bytes=deque(), output=[]))
        cpu.v = 1

        cpu.step()

        self.assertEqual(cpu.pc, 0x0103)

    def test_unknown_jsr_target_in_ram_is_executed_not_treated_as_external(self) -> None:
        image = bytes([0xBD, 0x16, 0xDF])

        result = run_session(image, [], 10)

        self.assertEqual(result.reason, "Opcode $00 not implemented at $16DF")

    def test_jump_to_monitor_output_returns_through_callers_stack_frame(self) -> None:
        image = bytes(
            [
                0x8D,
                0x02,  # bsr $0104
                0x01,  # nop: return target after monitor RTS
                0x01,  # nop
                0x86,
                0x41,  # ldaa #'A'
                0x7E,
                0xE1,
                0xD1,  # jmp MON_E1D1
            ]
        )
        cpu = CPU6800(image, Monitor(input_bytes=deque(), output=[]))

        cpu.step()
        cpu.step()
        cpu.step()

        self.assertEqual(bytes(cpu.monitor.output), b"A")
        self.assertEqual(cpu.pc, 0x0102)
        self.assertEqual(cpu.sp, 0xA047)

    def test_list_command_works_with_image_verified_direct_mode_table(self) -> None:
        image = bytearray(BUILD_IMAGE.read_bytes())

        result = run_session(bytes(image), [b"10 PRINT 1\r", b"LIST\r"], 400_000)

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("10 PRINT 1", result.text)
        self.assertNotIn("ERROR 0", result.text)
        self.assertNotIn("\x7f", result.text)
        self.assertNotIn("\x02", result.text)
        self.assertNotIn("\x03", result.text)

    def test_run_command_reaches_expression_evaluator_after_run_pointer_fix(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        result = run_session(image, [b"10 PRINT 1\r", b"RUN\r"], 400_000)

        self.assertEqual(result.reason, "input_exhausted")
        self.assertNotIn("ERROR 0", result.text)
        self.assertIn("1", result.text)

    def test_print_handles_multibyte_numbers_with_screen_verified_03c1_fix(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        result = run_session(image, [b"10 PRINT 258\r", b"RUN\r"], 700_000)

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("258", result.text)
        self.assertNotIn("\r\n18\r\n", result.text)

    def test_abs_chr_and_tab_functions_work(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "abs",
                "chunks": [b"10 PRINT ABS(-3)\r", b"RUN\r"],
                "contains": ["\r\n3\r\n", "READY"],
            },
            {
                "name": "chr",
                "chunks": [b"10 PRINT CHR(65)\r", b"RUN\r"],
                "contains": ["\r\nA\r\n", "READY"],
            },
            {
                "name": "tab",
                "chunks": [b"10 PRINT TAB(3),1\r", b"RUN\r"],
                "contains": ["\r\n        1\r\n", "READY"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], 700_000)

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)
                self.assertNotIn("ERROR", result.text)

    def test_arithmetic_operators_work(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "multiply",
                "chunks": [b"10 PRINT 8*2\r", b"RUN\r"],
                "contains": ["\r\n16\r\n", "READY"],
            },
            {
                "name": "add",
                "chunks": [b"10 PRINT 8+2\r", b"RUN\r"],
                "contains": ["\r\n10\r\n", "READY"],
            },
            {
                "name": "subtract",
                "chunks": [b"10 PRINT 8-2\r", b"RUN\r"],
                "contains": ["\r\n6\r\n", "READY"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], 700_000)

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)
                self.assertNotIn("ERROR", result.text)

    def test_truthiness_equality_character_literal_and_colon_separator_work(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "one_is_true",
                "chunks": [b"10 IF 1 THEN PRINT 1\r", b"RUN\r"],
                "contains": ["\r\n1\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "zero_is_false",
                "chunks": [b"10 IF 0 THEN PRINT 1\r", b"20 PRINT 2\r", b"RUN\r"],
                "contains": ["\r\n2\r\n", "READY"],
                "not_contains": ["\r\n1\r\n", "ERROR"],
            },
            {
                "name": "equal_relation",
                "chunks": [b"10 IF 1=1 THEN PRINT 3\r", b"RUN\r"],
                "contains": ["\r\n3\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "character_literal",
                "chunks": [b"10 PRINT 'A'\r", b"RUN\r"],
                "contains": ["\r\nA\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "colon_separator",
                "chunks": [b"10 PRINT 1:PRINT 2\r", b"RUN\r"],
                "contains": ["\r\n1\r\n", "\r\n2\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], 900_000)

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)
                for value in case["not_contains"]:
                    self.assertNotIn(value, result.text)

    def test_hash_paren_memory_access_supports_peek_and_poke_style_operations(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "peek_style_read",
                "chunks": [b"10 PRINT #(0)\r", b"RUN\r"],
                "contains": ["\r\n0\r\n", "READY"],
            },
            {
                "name": "poke_style_write_then_read",
                "chunks": [b"10 #(0)=7\r", b"20 PRINT #(0)\r", b"RUN\r"],
                "contains": ["\r\n7\r\n", "READY"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], 900_000)

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)
                self.assertNotIn("ERROR", result.text)

    def test_print_dollar_stop_literal_and_input_prompt_work(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "print_dollar",
                "chunks": [b"PRINT$:END\r"],
                "contains": ["READY"],
                "numeric_output": True,
                "not_contains": ["ERROR"],
            },
            {
                "name": "stop_literal",
                "chunks": [b"10 STOP 'HI'\r", b"RUN\r"],
                "contains": ["HI", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "input_with_literal_prompt",
                "chunks": [b'10 INPUT "A",A\r', b"20 PRINT A\r", b"RUN\r", b"5\r"],
                "contains": ["A? ", "\r\n5\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], 900_000)

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)
                for value in case.get("not_contains", []):
                    self.assertNotIn(value, result.text)
                if case.get("numeric_output"):
                    self.assert_numeric_result(result.text)

    def test_hex_literals_array_variables_and_multi_prompt_input_work(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "hex_literal_one_byte",
                "chunks": [b"10 PRINT $41\r", b"RUN\r"],
                "contains": ["\r\n65\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "hex_literal_two_byte",
                "chunks": [b"10 PRINT $1234\r", b"RUN\r"],
                "contains": ["\r\n4660\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "hex_literal_in_chr",
                "chunks": [b"10 PRINT CHR($41)\r", b"RUN\r"],
                "contains": ["\r\nA\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "array_variable_assignment",
                "chunks": [b"10 LET @(1)=7\r", b"20 PRINT @(1)\r", b"RUN\r"],
                "contains": ["\r\n7\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "input_multiple_literal_prompts",
                "chunks": [b'10 INPUT "A",A:INPUT "B",B\r', b"20 PRINT A\r", b"30 PRINT B\r", b"RUN\r", b"5\r", b"6\r"],
                "contains": ["A? ", "B? ", "\r\n5\r\n", "\r\n6\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], 1_500_000)

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)
                for value in case["not_contains"]:
                    self.assertNotIn(value, result.text)

    def test_direct_goto_then_line_number_and_control_keys_work(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "direct_goto",
                "chunks": [b"10 PRINT 1\r", b"20 PRINT 2\r", b"GOTO 20:END\r"],
                "contains": ["\r\n2\r\n", "READY"],
                "not_contains": ["\r\n1\r\n", "ERROR"],
            },
            {
                "name": "if_then_line_number",
                "chunks": [b"10 IF 1=1 THEN 30\r", b"20 PRINT 9\r", b"30 PRINT 1\r", b"RUN\r"],
                "contains": ["\r\n1\r\n", "READY"],
                "not_contains": ["\r\n9\r\n", "ERROR"],
            },
            {
                "name": "ctrl_o",
                "chunks": [b"10 PRIN\x0fT 2\r", b"LIST\r"],
                "contains": ["10 PRI 2", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "ctrl_c_break",
                "chunks": [b"10 PRINT 1\r", b"RUN\x03"],
                "contains": ["READY"],
                "not_contains": ["\r\n1\r\n", "ERROR"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], 900_000)

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)
                for value in case["not_contains"]:
                    self.assertNotIn(value, result.text)

    def test_ctrl_x_clears_current_input_line(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "program_line_reentry",
                "chunks": [b"10 PRI\x18 10 PRINT 2\r", b"LIST\r"],
                "contains": ["ERROR 180", "READY"],
                "not_contains": ["10 PRINT 2", "10 PRI\r"],
            },
            {
                "name": "direct_mode_reentry",
                "chunks": [b"PRINT 9\x18 PRINT 3:END\r"],
                "contains": ["READY"],
                "not_contains": ["\r\n9\r\n", "\r\n3\r\n", "ERROR"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], 900_000)

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)
                for value in case["not_contains"]:
                    self.assertNotIn(value, result.text)

    def test_let_assignment_runs_without_error_with_current_dump_and_corrections(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        result = run_session(image, [b"10 LET A=1\r", b"RUN\r"], 500_000)

        self.assertEqual(result.reason, "input_exhausted")
        self.assertNotIn("ERROR 0", result.text)

    def test_list_then_run_no_longer_leaves_error_zero(self) -> None:
        image = BUILD_IMAGE.read_bytes()

        result = run_session(image, [b"10 PRINT 1\r", b"LIST\r", b"RUN\r"], 500_000)

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("10 PRINT 1", result.text)
        self.assertIn("1", result.text)
        self.assertNotIn("ERROR 0", result.text)
        self.assertNotIn("\x7f", result.text)

    def test_default_program_commands_still_run_after_listing_hash_memory_syntax(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        script = build_input("10 LET A=#(1)\n20 PRINT 7\n30 END\n")

        result = run_session(image, script, 700_000)

        self.assertEqual(result.reason, "input_exhausted")
        self.assertIn("10 LET A=#(1)", result.text)
        self.assertIn("\r\n7\r\n", result.text)
        self.assertNotIn("ERROR", result.text)

    def test_gosub_rem_stop_and_new_work_in_documented_forms(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "gosub_ret",
                "chunks": [b"10 GOSUB 30\r", b"20 END\r", b"30 PRINT 1\r", b"40 RET\r", b"RUN\r"],
                "contains": ["\r\n1\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "rem",
                "chunks": [b"10 REM HI\r", b"20 PRINT 1\r", b"RUN\r"],
                "contains": ["\r\n1\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "stop",
                "chunks": [b"10 PRINT 1\r", b"20 STOP\r", b"30 PRINT 2\r", b"RUN\r"],
                "contains": ["\r\n1\r\n", "READY"],
                "not_contains": ["\r\n2\r\n", "ERROR"],
            },
            {
                "name": "new",
                "chunks": [b"10 PRINT 1\r", b"NEW\r", b"LIST\r"],
                "contains": ["READY"],
                "not_contains": ["10 PRINT 1", "ERROR"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], 700_000)

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)
                for value in case["not_contains"]:
                    self.assertNotIn(value, result.text)

    def test_pdf_ocr_errors_are_reproducible_by_restoring_bad_bytes(self) -> None:
        cases = [
            {
                "name": "0x01fc_line_replace_path",
                "patches": {0x01FC: 0xC4, 0x01FD: 0x5B},
                "chunks": [b"10 PRINT 1\r", b"10 PRINT 2\r", b"LIST\r"],
                "max_steps": 700_000,
                "reason": "Opcode $5B not implemented at $01FD",
            },
            {
                "name": "0x02be_run_pointer",
                "patches": {0x02BE: 0x2A},
                "chunks": [b"10 PRINT 1\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["ERROR 180"],
                "not_contains": ["\r\n1\r\n"],
            },
            {
                "name": "0x03c1_0x03df_decimal_print_pair",
                "patches": {0x03C1: 0xBD, 0x03DF: 0x80},
                "chunks": [b"10 PRINT 258\r", b"RUN\r"],
                "max_steps": 900_000,
                "reason": "Opcode $00 not implemented at $0D49",
                "not_contains": ["\r\n258\r\n"],
            },
            {
                "name": "0x0333_print_string_branch_offset",
                "patches": {0x0333: 0x0B},
                "chunks": [b"10 PRINT \"HI\"\r", b"RUN\r"],
                "max_steps": 500_000,
                "reason": "Opcode $13 not implemented at $033F",
                "contains": ["HI"],
            },
            {
                "name": "0x04c2_monitor_tail_call",
                "patches": {0x04C2: 0xBD},
                "chunks": [b"10 PRINT 1\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "Opcode $00 not implemented at $F626",
            },
            {
                "name": "0x0627_let_assignment",
                "patches": {0x0627: 0x0B},
                "chunks": [b"10 LET A=1\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["ERROR 180"],
            },
            {
                "name": "0x069e_jsr_to_bad_ram_target",
                "patches": {0x069E: 0xBD},
                "chunks": [b"10 PRINT 1\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "Opcode $00 not implemented at $16DF",
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(
                    self.patched_image(case["patches"]),
                    case["chunks"],
                    case["max_steps"],
                )

                self.assertEqual(result.reason, case["reason"])
                for value in case.get("contains", []):
                    self.assertIn(value, result.text)
                for value in case.get("not_contains", []):
                    self.assertNotIn(value, result.text)

    def test_pdf_keyword_program_smoke_cases(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "let",
                "keywords": {"LET", "RUN"},
                "chunks": [b"10 LET A=1\r", b"RUN\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "if_then",
                "keywords": {"IF", "THEN", "PRINT", "RUN"},
                "chunks": [b"10 IF 1=1 THEN PRINT 1\r", b"RUN\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "goto",
                "keywords": {"GOTO", "PRINT", "RUN"},
                "chunks": [b"10 GOTO 30\r", b"20 PRINT 9\r", b"30 PRINT 1\r", b"RUN\r"],
                "max_steps": 600_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["9", "ERROR"],
            },
            {
                "name": "gosub_ret_end",
                "keywords": {"GOSUB", "RET", "END", "PRINT", "RUN"},
                "chunks": [b"10 GOSUB 30\r", b"20 END\r", b"30 PRINT 1\r", b"40 RET\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "for_next_step_to",
                "keywords": {"FOR", "NEXT", "TO", "STEP", "PRINT", "END", "RUN"},
                "chunks": [b"10 FOR I=1 TO 2 STEP 1\r", b"20 PRINT I\r", b"30 NEXT I\r", b"40 END\r", b"RUN\r"],
                "max_steps": 1_200_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n", "\r\n2\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "rem",
                "keywords": {"REM", "PRINT", "RUN"},
                "chunks": [b"10 REM TEST\r", b"20 PRINT 1\r", b"RUN\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "input",
                "keywords": {"INPUT", "PRINT", "RUN"},
                "chunks": [b"10 INPUT A\r", b"20 PRINT A\r", b"RUN\r", b"5\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["? ", "\r\n5\r\n", "READY"],
                "not_contains": ["ERROR", "Opcode $00"],
            },
            {
                "name": "in_pr",
                "keywords": {"IN", "PR", "RUN"},
                "chunks": [b"10 IN A\r", b"20 PR A\r", b"RUN\r", b"5\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["? ", "\r\n5\r\n", "READY"],
                "not_contains": ["ERROR", "Opcode $00"],
            },
            {
                "name": "stop",
                "keywords": {"STOP", "PRINT", "RUN"},
                "chunks": [b"10 PRINT 1\r", b"20 STOP\r", b"30 PRINT 2\r", b"RUN\r"],
                "max_steps": 600_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n", "READY"],
                "not_contains": ["\r\n2\r\n", "ERROR"],
            },
            {
                "name": "rnd",
                "keywords": {"RND(", "PRINT", "RUN"},
                "chunks": [b"10 PRINT RND(1)\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "numeric_output": True,
                "not_contains": ["ERROR"],
            },
            {
                "name": "abs",
                "keywords": {"ABS(", "PRINT", "RUN"},
                "chunks": [b"10 PRINT ABS(-1)\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "mod",
                "keywords": {"MOD(", "PRINT", "RUN"},
                "chunks": [b"10 PRINT MOD(5,2)\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "numeric_output": True,
                "not_contains": ["ERROR"],
            },
            {
                "name": "division",
                "keywords": {"PRINT", "RUN"},
                "chunks": [b"10 PRINT 8/2\r", b"20 PRINT 7/2\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["\r\n4\r\n", "\r\n3\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "usr",
                "keywords": {"USR(", "PRINT", "RUN"},
                "chunks": [
                    b"10 #(4096)=134\r",
                    b"20 #(4097)=42\r",
                    b"30 #(4098)=95\r",
                    b"40 #(4099)=57\r",
                    b"50 PRINT USR(4096)\r",
                    b"RUN\r",
                ],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["\r\n42\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "chr_tab",
                "keywords": {"CHR(", "TAB(", "PRINT", "RUN"},
                "chunks": [b"10 PRINT TAB(3),CHR(65)\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["A"],
                "not_contains": ["ERROR"],
            },
        ]

        covered = set()
        for case in cases:
            covered.update(case["keywords"])
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], case["max_steps"])

                self.assertEqual(result.reason, case["reason"])
                for value in case.get("contains", []):
                    self.assertIn(value, result.text)
                for value in case.get("not_contains", []):
                    self.assertNotIn(value, result.text)
                if case.get("numeric_output"):
                    self.assert_numeric_result(result.text)

        self.assertEqual(covered, PDF_KEYWORDS - {"LIST", "LOAD", "EX", "AUTO", "NEW"})

    def test_pdf_keyword_direct_mode_smoke_cases(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "list",
                "keywords": {"LIST"},
                "chunks": [b"10 PRINT 1\r", b"LIST\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["10 PRINT 1"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "load",
                "keywords": {"LOAD"},
                "chunks": [b"LOAD\r"],
                "max_steps": 400_000,
                "reason": "input_exhausted",
                "contains": ["READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "ex",
                "keywords": {"EX"},
                "chunks": [b"EX\r"],
                "max_steps": 500_000,
                "reason": "monitor_exit",
                "contains": ["READY"],
                "not_contains": ["ERROR 0"],
            },
            {
                "name": "new",
                "keywords": {"NEW"},
                "chunks": [b"10 PRINT 1\r", b"NEW\r", b"LIST\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["READY"],
                "not_contains": ["10 PRINT 1", "ERROR"],
            },
        ]

        covered = set()
        for case in cases:
            covered.update(case["keywords"])
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], case["max_steps"])

                self.assertEqual(result.reason, case["reason"])
                for value in case.get("contains", []):
                    self.assertIn(value, result.text)
                for value in case.get("not_contains", []):
                    self.assertNotIn(value, result.text)

        self.assertEqual(covered, {"LIST", "LOAD", "EX", "NEW"})

    def test_pdf_documented_syntax_cases(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "list_single_line",
                "chunks": [b"10 PRINT 1\r", b"20 PRINT 2\r", b"LIST 20\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["20 PRINT 2"],
                "not_contains": ["10 PRINT 1", "ERROR"],
            },
            {
                "name": "list_range",
                "chunks": [b"10 PRINT 1\r", b"20 PRINT 2\r", b"30 PRINT 3\r", b"LIST 20,30\r"],
                "max_steps": 800_000,
                "reason": "input_exhausted",
                "contains": ["20 PRINT 2", "30 PRINT 3"],
                "not_contains": ["10 PRINT 1", "ERROR"],
            },
            {
                "name": "if_less_than",
                "chunks": [b"10 IF 1<2 THEN PRINT 1\r", b"RUN\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "if_greater_than",
                "chunks": [b"10 IF 2>1 THEN PRINT 1\r", b"RUN\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "if_less_equal",
                "chunks": [b"10 IF 1<=1 THEN PRINT 1\r", b"RUN\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "if_greater_equal",
                "chunks": [b"10 IF 1>=1 THEN PRINT 1\r", b"RUN\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "if_not_equal",
                "chunks": [b"10 IF 1<>2 THEN PRINT 1\r", b"RUN\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "return_alias",
                "chunks": [b"10 GOSUB 30\r", b"20 END\r", b"30 PRINT 1\r", b"40 RETURN\r", b"RUN\r"],
                "max_steps": 800_000,
                "reason": "input_exhausted",
                "contains": ["\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "line_number_min",
                "chunks": [b"1 PRINT 1\r", b"LIST\r", b"RUN\r"],
                "max_steps": 800_000,
                "reason": "input_exhausted",
                "contains": ["1 PRINT 1", "\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "line_number_max",
                "chunks": [b"32767 PRINT 1\r", b"LIST\r", b"RUN\r"],
                "max_steps": 900_000,
                "reason": "input_exhausted",
                "contains": ["32767 PRINT 1", "\r\n1\r\n"],
                "not_contains": ["ERROR"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], case["max_steps"])

                self.assertEqual(result.reason, case["reason"])
                for value in case.get("contains", []):
                    self.assertIn(value, result.text)
                for value in case.get("not_contains", []):
                    self.assertNotIn(value, result.text)

    def test_documented_error_codes_are_reported_for_supported_cases(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "input_error",
                "chunks": [b"10 INPUT A\r", b"20 PRINT A\r", b"RUN\r", b"X" * 71 + b"\r"],
                "contains": ["ERROR 100", "READY"],
            },
            {
                "name": "memory_size_over",
                # Constrain BASIC's discovered memory end ($BA/$BB), then
                # exceed it with a line within the 70-character input limit.
                "chunks": [b"#(186)=9:#(187)=160:END\r", f'10 PRINT "{"X" * 50}"\r'.encode()],
                "contains": ["ERROR 110", "READY"],
            },
            {
                "name": "invalid_line_number_zero",
                "chunks": [b"0 PRINT 1\r"],
                "contains": ["ERROR 120", "READY"],
            },
            {
                "name": "invalid_line_number_too_large",
                "chunks": [b"32768 PRINT 1\r"],
                "contains": ["ERROR 120", "READY"],
            },
            {
                "name": "print_error",
                "chunks": [b'10 PRINT "A\r', b"RUN\r"],
                "contains": ["ERROR 130", "READY"],
            },
            {
                "name": "zero_divide",
                "chunks": [b"10 PRINT 1/0\r", b"RUN\r"],
                "contains": ["ERROR 140", "READY"],
            },
            {
                "name": "illegal_arithmetic",
                "chunks": [b"10 PRINT 1+\r", b"RUN\r"],
                "contains": ["ERROR 160", "READY"],
            },
            {
                "name": "mod_error",
                "chunks": [b"10 PRINT MOD(1)\r", b"RUN\r"],
                "contains": ["ERROR 170", "READY"],
            },
            {
                "name": "unrecognized_statement",
                "chunks": [b"10 FOO\r", b"RUN\r"],
                "contains": ["ERROR 180", "READY"],
            },
            {
                "name": "subroutine_error",
                "chunks": [b"10 RETURN\r", b"RUN\r"],
                "contains": ["ERROR 190", "READY"],
            },
            {
                "name": "line_number_not_found",
                "chunks": [b"10 GOTO 99\r", b"RUN\r"],
                "contains": ["ERROR 200", "READY"],
            },
            {
                "name": "for_error",
                "chunks": [b"10 FOR I=1 STEP 1\r", b"RUN\r"],
                "contains": ["ERROR 210", "READY"],
            },
            {
                "name": "next_error",
                "chunks": [b"10 NEXT I\r", b"RUN\r"],
                "contains": ["ERROR 220", "READY"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], case.get("max_steps", 900_000))

                self.assertEqual(result.reason, "input_exhausted")
                for value in case["contains"]:
                    self.assertIn(value, result.text)

    def test_pdf_documented_known_limitations(self) -> None:
        image = BUILD_IMAGE.read_bytes()
        cases = [
            {
                "name": "division_by_zero",
                "chunks": [b"10 PRINT 8/0\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["ERROR 140", "READY"],
            },
            {
                "name": "input_multiple_variables",
                "chunks": [b"10 INPUT A,B\r", b"20 PRINT A\r", b"30 PRINT B\r", b"RUN\r", b"5,6\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["? ", "\r\n5\r\n", "\r\n6\r\n", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "exit_alias",
                "chunks": [b"EXIT\r"],
                "max_steps": 500_000,
                "reason": "monitor_exit",
                "contains": ["READY"],
            },
            {
                "name": "print_string_literal",
                "chunks": [b"10 PRINT \"HI\"\r", b"RUN\r"],
                "max_steps": 500_000,
                "reason": "input_exhausted",
                "contains": ["HI", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "print_string_with_comma",
                "chunks": [b"10 PRINT \"HI\",\"JK\"\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["HI      JK", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "print_string_with_semicolon",
                "chunks": [b"10 PRINT \"HI\";\"JK\"\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["HIJK", "READY"],
                "not_contains": ["ERROR"],
            },
            {
                "name": "print_string_with_number",
                "chunks": [b"10 PRINT \"HI\",1\r", b"RUN\r"],
                "max_steps": 700_000,
                "reason": "input_exhausted",
                "contains": ["HI      1", "READY"],
                "not_contains": ["ERROR"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_session(image, case["chunks"], case["max_steps"])

                self.assertEqual(result.reason, case["reason"])
                for value in case.get("contains", []):
                    self.assertIn(value, result.text)
                for value in case.get("not_contains", []):
                    self.assertNotIn(value, result.text)


if __name__ == "__main__":
    unittest.main()
