from collections import deque
import io
from pathlib import Path
import signal
import subprocess
import sys
from unittest.mock import patch

import pytest

from scripts.run_harness import (
    CPU6800, Monitor, normalize_command,
    run_repl_session, run_session,
)


ROOT = Path(__file__).resolve().parents[1]
IMAGE = (ROOT / "build/dendai-tiny-basic.bin").read_bytes()


def run(*lines):
    return run_session(IMAGE, [(line + "\r").encode() for line in lines], 1_500_000)


@pytest.mark.parametrize("line", [
    "PRINT $41", "LET #(4096)=7", 'INPUT "A",A,"B",B',
    "10 PRINT 1", '  PRINT "END:$FF"  ', "",
])
def test_transport_does_not_rewrite_basic(line):
    assert normalize_command(line + "\r\n") == (line + "\r").encode()


def test_monitor_input_without_any_basic_prompt_or_entry_address():
    # JSR monitor input; JSR monitor output; JMP monitor exit.
    image = bytes.fromhex("BD E1 AC BD E1 D1 7E E0 D0")
    result = run_session(image, [b"Z"], 20)
    assert result.reason == "monitor_exit"
    assert result.text == "Z"


@pytest.mark.parametrize("value, expected", [
    ("1+2", "3"), ("$41", "65"), ("32768", "-32768"),
])
def test_input_uses_native_expression_evaluation(value, expected):
    result = run("10 INPUT A", "20 PRINT A", "RUN", value)
    assert result.reason == "input_exhausted"
    assert "ERROR" not in result.text
    assert "\r\n" + expected + "\r\n" in result.text


def test_native_parser_accepts_seventeen_parentheses():
    result = run("10 PRINT " + "(" * 17 + "1" + ")" * 17, "RUN")
    assert result.reason == "input_exhausted"
    assert "ERROR" not in result.text
    assert "\r\n1\r\n" in result.text


def test_multi_prompt_extension_is_not_silently_expanded():
    result = run('10 INPUT "A",A,"B",B', "RUN", "5")
    assert result.reason == "input_exhausted"
    assert "ERROR 100" in result.text


def test_direct_end_fix_is_in_image_not_source_transport():
    original = bytearray(IMAGE)
    original[0x02CD - 0x0100:0x02D0 - 0x0100] = bytes.fromhex("08 24 DF")
    bad = run_session(bytes(original), [b"PRINT 4\r"], 500_000)
    good = run("PRINT 4")
    assert "ERROR 180" in bad.text
    assert "\r\n4\r\n" in good.text
    assert "ERROR" not in good.text
    assert good.reason == "input_exhausted"


@pytest.mark.parametrize("line, expected", [
    ("PRINT 1:PRINT 2", "\r\n1\r\n2\r\n"),
    ("LET A=7:PRINT A", "\r\n7\r\n"),
    ("IF 1=1 THEN PRINT 8", "\r\n8\r\n"),
    ("IF 1=0 THEN PRINT 8", "READY"),
])
def test_native_direct_end_preserves_statement_control(line, expected):
    result = run(line)
    assert result.reason == "input_exhausted"
    assert expected in result.text
    assert "ERROR" not in result.text


@pytest.fixture
def small_program_memory():
    original_init = CPU6800.__init__

    def init(cpu, *args, **kwargs):
        original_init(cpu, *args, **kwargs)
        # Keep the monitor stack writable, but make the RAM discovery loop
        # encounter a read-only byte after 60 bytes of program memory.
        original_write = cpu.write8

        def write(addr, value):
            if (addr & 0xFFFF) != 0x0980 + 60:
                original_write(addr, value)

        cpu.write8 = write

    with patch.object(CPU6800, "__init__", init):
        yield


@pytest.mark.parametrize("value", [256, 12345, 32767, -32768, -1])
def test_native_array_preserves_signed_words_and_adjacent_elements(value):
    result = run(
        "10 LET @(0)=99", f"20 LET %(1)={value}", "30 LET @(2)=77",
        "40 PRINT @(0)", "50 PRINT @(1)", "60 PRINT @(2)", "RUN",
    )
    assert result.reason == "input_exhausted"
    assert "ERROR" not in result.text
    assert f"\r\n99\r\n{value}\r\n77\r\n" in result.text


def test_array_subscript_expression_and_memory_are_distinct():
    result = run(
        "10 LET I=1500", "20 LET @(I*2)=12345", "30 #(3000)=7",
        "40 PRINT @(I*2)", "50 PRINT #(3000)", "RUN",
    )
    assert "\r\n12345\r\n7\r\n" in result.text
    assert "ERROR" not in result.text


@pytest.mark.parametrize("operand,expected_x,stop", [
    (0x4E, 0x007E, 0x0859),
    (0x65, 0x1004, 0x0200),
])
def test_array_call_contract_without_source_translation(operand, expected_x, stop):
    """Same initial state as the independent EmulatorKit probe in docs/."""
    image = bytearray(IMAGE)
    image[0x062B - 0x0100] = operand
    cpu = CPU6800(image, Monitor(deque(), []))
    cpu.mem[0x1000:0x100A] = b"@(1)=12345\0"
    for address, value in [(0x10, 0x70), (0x80, 0x80), (0xB8, 0x981),
                           (0xBA, 0x8003), (0x9FFF, 0x200)]:
        cpu.write16(address, value)
    cpu.pc, cpu.x, cpu.sp = 0x0651, 0x1000, 0x9FFE
    source_positions = []
    for _ in range(10000):
        if cpu.pc in {0x062C, 0x062F, 0x0643, 0x065A}:
            source_positions.append(cpu.x)
        if cpu.pc in {0x0200, 0x0859}:
            break
        cpu.step()
    assert source_positions == [expected_x] * 4
    assert cpu.pc == stop
    if operand == 0x4E:
        assert cpu.b == 180
    else:
        assert cpu.x == 0x0984
        assert (cpu.b << 8) | cpu.a == 12345


@pytest.mark.parametrize("index", [-1, 32767])
def test_array_bounds_report_memory_error(index):
    result = run(f"10 LET @({index})=1", "RUN", "PRINT 42")
    assert "ERROR 110" in result.text
    assert "\r\n42\r\n" in result.text


@pytest.mark.parametrize("printed", ["#", "OK? "])
def test_printed_prompt_does_not_consume_input(printed):
    lines = [f'10 PRINT "{printed}"', "20 INPUT A", "30 PRINT A", "40 END", "RUN", "42"]
    result = run(*lines)
    assert "\r\n42\r\n" in result.text
    assert "ERROR" not in result.text
    with patch("sys.stdin", io.StringIO("\n".join(lines) + "\n")), patch("sys.stdout", io.StringIO()):
        result = run_repl_session(IMAGE, 1_500_000)
    assert result.reason == "stdin_eof"
    assert "\r\n42\r\n" in result.text


def test_new_and_replacement_use_accepted_program_size(small_program_memory):
    result = run("10 REM " + "X" * 40, "NEW", "20 REM " + "Y" * 40,
                 "20 PRINT 42", "30 END", "RUN")
    assert "ERROR" not in result.text
    assert "\r\n42\r\n" in result.text


def test_rejected_line_does_not_count_as_stored_program(small_program_memory):
    result = run("10 REM " + "X" * 100, "20 PRINT 42", "RUN")
    assert "ERROR 100" in result.text
    assert "ERROR 110" not in result.text
    assert "\r\n42\r\n" in result.text


def test_capacity_check_also_applies_in_repl(small_program_memory):
    lines = ["10 REM " + "X" * 40, "20 REM " + "Y" * 40, "NEW", "20 PRINT 42", "RUN"]
    with patch("sys.stdin", io.StringIO("\n".join(lines) + "\n")), \
         patch("sys.stdout", io.StringIO()):
        result = run_repl_session(IMAGE, 1_500_000)
    assert result.text.count("ERROR 110") == 1
    assert "\r\n42\r\n" in result.text


def test_rem_is_not_translated_or_validated_as_an_expression():
    comment = "REM @(1)=$FF:" + "(" * 17 + '"'
    assert normalize_command("10 " + comment) == ("10 " + comment + "\r").encode("ascii")
    result = run("10 " + comment, "20 PRINT 42", "LIST", "RUN")
    assert "10 " + comment in result.text
    assert "ERROR" not in result.text
    assert "\r\n42\r\n" in result.text
    assert normalize_command("10 PRINT 1:" + comment) == ("10 PRINT 1:" + comment + "\r").encode("ascii")


@pytest.mark.parametrize("entry", ["indexed", "external_pc"])
def test_monitor_tail_call_returns_and_counts_steps(entry):
    cpu = CPU6800(bytes([0x6E, 0]), Monitor(deque(), []))
    cpu.x = 0xE1D1
    cpu.a = ord("A")
    cpu.push16(0x200)
    if entry == "external_pc":
        cpu.pc = 0xE1D1
    cpu.step()
    assert cpu.pc == 0x200
    assert cpu.steps == 1
    assert cpu.monitor.output == [ord("A")]


@pytest.mark.parametrize("opcode,start,expected,flags", [
    (0x4C, 0x7F, 0x80, (1, 0, 1, 1)),
    (0x4C, 0xFF, 0, (0, 1, 0, 1)),
    (0x4A, 0x80, 0x7F, (0, 0, 1, 1)),
    (0x4A, 1, 0, (0, 1, 0, 1)),
])
def test_accumulator_increment_decrement_flags(opcode, start, expected, flags):
    cpu = CPU6800(bytes([opcode]), Monitor(deque(), []))
    cpu.a, cpu.c = start, 1
    cpu.step()
    assert cpu.a == expected
    assert (cpu.n, cpu.z, cpu.v, cpu.c) == flags


@pytest.mark.parametrize("opcode,expected,flags", [
    (0x64, 0x40, (0, 0, 1, 1)), (0x74, 0x40, (0, 0, 1, 1)),
    (0x67, 0xC0, (1, 0, 0, 1)), (0x77, 0xC0, (1, 0, 0, 1)),
])
def test_memory_shift_result_and_flags(opcode, expected, flags):
    raw = [opcode, 0] if opcode < 0x70 else [opcode, 0x20, 0]
    cpu = CPU6800(bytes(raw), Monitor(deque(), []))
    cpu.x = 0x2000
    cpu.write8(cpu.x, 0x81)
    cpu.step()
    assert cpu.read8(0x2000) == expected
    assert (cpu.n, cpu.z, cpu.v, cpu.c) == flags


@pytest.mark.parametrize("delivery", ["exception", "signal"])
def test_break_during_cpu_execution_returns_to_repl(delivery):
    real_step = CPU6800.step
    interrupted = False
    previous_handler = signal.getsignal(signal.SIGINT)

    def step(cpu):
        nonlocal interrupted
        if cpu.pc == 0x02AF and not interrupted:
            interrupted = True
            if delivery == "exception":
                raise KeyboardInterrupt
            signal.raise_signal(signal.SIGINT)
            assert cpu.pc == 0x02AF
            assert bytes(cpu.monitor.input_bytes) == b"\x03"
        return real_step(cpu)

    with patch.object(CPU6800, "step", step), \
         patch("sys.stdin", io.StringIO("10 GOTO 10\nRUN\nPRINT 42\n")), \
         patch("sys.stdout", io.StringIO()):
        result = run_repl_session(IMAGE, 1_500_000)
    assert interrupted
    assert signal.getsignal(signal.SIGINT) == previous_handler
    assert result.reason == "stdin_eof"
    assert "\r\n42\r\n" in result.text


@pytest.mark.parametrize("arguments,reason", [
    (["--command", "RUN", "--max-steps", "1"], "step_limit"),
    (["--command", "10 #(4096)=25", "--command", "20 PRINT USR(4096)", "--command", "RUN"], "not implemented"),
])
def test_cli_reports_execution_failure(arguments, reason):
    result = subprocess.run(
        [sys.executable, "scripts/run_harness.py", "build/dendai-tiny-basic.bin", *arguments],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 1
    assert reason in result.stdout
