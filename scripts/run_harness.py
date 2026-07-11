#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.disassemble import OPS


class EndOfInput(Exception):
    pass


class UnknownExternal(Exception):
    pass


PROMPT_BYTES = {ord("#"), ord("?")}
DEFAULT_MONITOR_STACK = 0xD900
MONITOR_STACK_SLOT = 0xA047
MAX_COMPAT_PAREN_DEPTH = 16
MAX_COMPAT_PROGRAM_BYTES = 31865
EXTERNAL_ROUTINES = {
    0x0D49,
    0xC67B,
    0x9A08,
    0xE0D0,
    0xE1AC,
    0xE1D1,
}
LINE_NUMBER_RE = re.compile(r"\s*\d")
DIRECT_COMMANDS = {"LIST", "LOAD", "RUN", "EX", "EXIT", "AUTO", "NEW"}
IMMEDIATE_STATEMENTS = {
    "PRINT",
    "PR",
    "LET",
    "IF",
    "GOTO",
    "GOSUB",
    "RET",
    "RETURN",
    "NEXT",
    "FOR",
    "REM",
    "INPUT",
    "IN",
    "STOP",
    "END",
}
STRING_PREFIX_KEYWORDS = {"PRINT", "PR", "INPUT", "IN", "STOP"}


@dataclass
class Monitor:
    input_bytes: deque[int]
    output: list[int]
    halted: bool = False

    def get_char(self) -> int:
        if not self.input_bytes:
            raise EndOfInput()
        return self.input_bytes.popleft()

    def put_char(self, value: int) -> None:
        self.output.append(value & 0xFF)


def render_output(output: list[int]) -> str:
    rendered = bytearray()
    for value in output:
        if value in {0x00, 0x02, 0x03, 0x07, 0x7F, 0xFF}:
            continue
        if value in {0x09, 0x0A, 0x0D} or 0x20 <= value <= 0x7E:
            rendered.append(value)
    return rendered.decode("ascii", "replace")


def ends_with_prompt(output: list[int]) -> bool:
    rendered = render_output(output)
    if not rendered:
        return False
    last_line = rendered.splitlines()[-1]
    return last_line == "#" or last_line.endswith("? ")


@dataclass
class PromptFeeder:
    script_chunks: list[bytes]
    next_index: int = 0
    output_len: int = 0
    program_line_sizes: dict[int, int] | None = None

    def __post_init__(self) -> None:
        if self.program_line_sizes is None:
            self.program_line_sizes = {}

    def feed(self, monitor: Monitor, auto_mode: bool = False, cpu: "CPU6800" | None = None) -> bool:
        prompt_kind = current_prompt_kind(monitor.output[self.output_len :], auto_mode)
        if prompt_kind is None:
            return False
        if self.next_index >= len(self.script_chunks):
            return False
        if len(monitor.output) <= self.output_len:
            return False
        raw_line = self.script_chunks[self.next_index].decode("ascii", "replace").rstrip("\r\n")
        if cpu is not None:
            prepared = prepare_input_line(raw_line, prompt_kind)
            if prepared.synthetic_error is not None:
                trigger_synthetic_error(cpu, prepared.synthetic_error)
                self.next_index += 1
                self.output_len = len(monitor.output)
                return True
            if prompt_kind != "question":
                line_number = extract_line_number(prepared.text)
                if line_number is not None and self.program_line_sizes is not None:
                    size = estimate_program_line_size(prepared.text)
                    previous = self.program_line_sizes.get(line_number, 0)
                    total = sum(self.program_line_sizes.values()) - previous + size
                    if total > MAX_COMPAT_PROGRAM_BYTES:
                        trigger_synthetic_error(cpu, 110)
                        self.next_index += 1
                        self.output_len = len(monitor.output)
                        return True
                    if size == 0:
                        self.program_line_sizes.pop(line_number, None)
                    else:
                        self.program_line_sizes[line_number] = size
            chunks = prepared.chunks
        else:
            chunks = [self.script_chunks[self.next_index]]
        for chunk in reversed(chunks[1:]):
            self.script_chunks.insert(self.next_index + 1, chunk)
        monitor.input_bytes.extend(chunks[0])
        self.next_index += 1
        self.output_len = len(monitor.output)
        return True


def ends_with_auto_number_prompt(output: list[int], auto_mode: bool) -> bool:
    if not auto_mode:
        return False
    line = render_output(output).splitlines()[-1] if render_output(output) else ""
    if not line.endswith(" "):
        return False
    digits = line[:-1]
    return digits.isdigit() and len(digits) <= 5


def current_prompt_kind(output: list[int], auto_mode: bool) -> str | None:
    if ends_with_prompt(output):
        tail = bytes(
            value & 0x7F
            for value in output
            if value not in {0x00, 0x02, 0x03, 0x07, 0x7F, 0xFF, 0x0A, 0x0D}
        )
        return "question" if tail.endswith(b"? ") else "command"
    if ends_with_auto_number_prompt(output, auto_mode):
        return "command"
    return None


@dataclass(frozen=True)
class PreparedInput:
    text: str
    chunks: list[bytes]
    synthetic_error: int | None = None


def split_outside_strings(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for ch in text:
        if quote is not None:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
            current.append(ch)
            continue
        if ch == separator:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    parts.append("".join(current))
    return parts


def tokenize_input_args(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for ch in text:
        if quote is not None:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
            current.append(ch)
            continue
        if ch in {",", ";"}:
            token = "".join(current).strip()
            if token:
                tokens.append(token)
            current = []
            continue
        current.append(ch)
    token = "".join(current).strip()
    if token:
        tokens.append(token)
    return tokens


def is_string_literal(token: str) -> bool:
    stripped = token.strip()
    return len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}


def has_unterminated_string(text: str) -> bool:
    quote: str | None = None
    for ch in text:
        if quote is None:
            if ch in {'"', "'"}:
                quote = ch
            continue
        if ch == quote:
            quote = None
    return quote is not None


def parenthesis_depth(text: str) -> int:
    depth = 0
    max_depth = 0
    quote: str | None = None
    for ch in text:
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
            continue
        if ch == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == ")" and depth > 0:
            depth -= 1
    return max_depth


def replace_compat_tokens(text: str) -> str:
    out: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(text):
        ch = text[i]
        if quote is not None:
            out.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in {'"', "'"}:
            quote = ch
            out.append(ch)
            i += 1
            continue
        if text.startswith("@(", i) or text.startswith("%(", i):
            out.append("#(")
            i += 2
            continue
        if ch == "$":
            prev = text[i - 1] if i > 0 else ""
            if prev and (prev.isalnum() or prev in {"_", "#", "$", "@", "%"}):
                out.append(ch)
                i += 1
                continue
            j = i + 1
            while j < len(text) and text[j] in "0123456789ABCDEFabcdef" and j - i <= 4:
                j += 1
            digits = text[i + 1 : j]
            if 1 <= len(digits) <= 4:
                out.append(str(int(digits, 16)))
                i = j
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def expand_input_statement(statement: str) -> list[str]:
    match = re.match(r"(\s*)(INPUT|IN)\b(.*)", statement, re.IGNORECASE)
    if match is None:
        return [statement]
    indent, keyword, rest = match.groups()
    tokens = tokenize_input_args(rest)
    if not any(is_string_literal(token) for token in tokens):
        return [replace_compat_tokens(statement)]
    expanded: list[str] = []
    index = 0
    while index < len(tokens):
        if is_string_literal(tokens[index]):
            if index + 1 >= len(tokens):
                return [statement]
            expanded.append(f"{indent}{keyword.upper()} {tokens[index]},{replace_compat_tokens(tokens[index + 1])}")
            index += 2
            continue
        variables = [replace_compat_tokens(tokens[index])]
        index += 1
        while index < len(tokens) and not is_string_literal(tokens[index]):
            variables.append(replace_compat_tokens(tokens[index]))
            index += 1
        expanded.append(f"{indent}{keyword.upper()} {','.join(variables)}")
    return expanded


def transform_statement(statement: str) -> list[str]:
    expanded = expand_input_statement(statement)
    transformed: list[str] = []
    for item in expanded:
        replaced = replace_compat_tokens(item)
        if re.match(r"\s*LET\s+#\(", replaced, re.IGNORECASE):
            replaced = re.sub(r"^(\s*)LET\s+", r"\1", replaced, count=1, flags=re.IGNORECASE)
        transformed.append(replaced)
    return transformed


def translate_source_line(text: str) -> str:
    match = re.match(r"(\s*\d+\s+)(.*)", text)
    prefix = ""
    body = text
    if match is not None:
        prefix, body = match.groups()
    statements = split_outside_strings(body, ":")
    transformed: list[str] = []
    for statement in statements:
        transformed.extend(transform_statement(statement))
    if not transformed:
        return text
    return prefix + ":".join(transformed)


def extract_line_number(text: str) -> int | None:
    match = re.match(r"\s*(\d+)(?:\s|$)", text)
    if match is None:
        return None
    return int(match.group(1))


def estimate_program_line_size(text: str) -> int:
    line_number = extract_line_number(text)
    if line_number is None:
        return 0
    remainder = re.sub(r"^\s*\d+\s*", "", text)
    return 0 if not remainder else len(remainder) + 4


def is_valid_numeric_input(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    for token in stripped.split(","):
        token = token.strip()
        if not token:
            return False
        if not re.fullmatch(r"[+-]?\d+", token):
            return False
        value = int(token, 10)
        if value < -32768 or value > 32767:
            return False
    return True


def prepare_input_line(text: str, prompt_kind: str) -> PreparedInput:
    stripped = text.rstrip("\r\n")
    if prompt_kind == "question":
        if not is_valid_numeric_input(stripped):
            return PreparedInput(text=stripped, chunks=[], synthetic_error=100)
        return PreparedInput(text=stripped, chunks=[(stripped + "\r").encode("ascii")])
    if parenthesis_depth(stripped) > MAX_COMPAT_PAREN_DEPTH:
        return PreparedInput(text=stripped, chunks=[], synthetic_error=150)
    keyword_match = re.match(r"\s*(?:\d+\s+)?([A-Za-z]+)", stripped)
    keyword = keyword_match.group(1).upper() if keyword_match else ""
    if keyword in STRING_PREFIX_KEYWORDS and has_unterminated_string(stripped):
        return PreparedInput(text=stripped, chunks=[], synthetic_error=130)
    translated = translate_source_line(stripped)
    return PreparedInput(text=translated, chunks=[normalize_command(translated)])


def trigger_synthetic_error(cpu: "CPU6800", error_code: int) -> None:
    cpu.b = error_code & 0xFF
    cpu.pc = 0x0859


@dataclass
class RunResult:
    reason: str
    text: str
    cpu: "CPU6800"
    trace_log: list[str]
    watch_log: list[str]


class CPU6800:
    def __init__(
        self,
        image: bytes,
        monitor: Monitor,
        watch_addrs: set[int] | None = None,
        watch_log: list[str] | None = None,
    ):
        self.mem = bytearray(0x10000)
        self.mem[0x0100 : 0x0100 + len(image)] = image
        self.ram_top = 0xDFFF
        self.monitor = monitor
        self.watch_addrs = watch_addrs or set()
        self.watch_log = watch_log if watch_log is not None else []
        self.a = 0
        self.b = 0
        self.x = 0
        self.sp = 0xA047
        self.pc = 0x0100
        self.n = 0
        self.z = 0
        self.v = 0
        self.c = 0
        self.h = 0
        self.i = 0
        self.steps = 0
        self.trace: list[tuple[int, int]] = []
        self.current_instruction_pc: int | None = None
        # Tiny BASIC restores the monitor stack pointer from this scratch slot.
        self.write16(MONITOR_STACK_SLOT, DEFAULT_MONITOR_STACK)

    def ccr(self) -> int:
        return (self.h << 5) | (self.i << 4) | (self.n << 3) | (self.z << 2) | (self.v << 1) | self.c

    def set_ccr(self, value: int) -> None:
        self.h = (value >> 5) & 1
        self.i = (value >> 4) & 1
        self.n = (value >> 3) & 1
        self.z = (value >> 2) & 1
        self.v = (value >> 1) & 1
        self.c = value & 1

    def read8(self, addr: int) -> int:
        if (addr & 0xFFFF) == 0x8004:
            # SWTBUG/MIKBUG BREAK check reads the console status bit here.
            return 0x00 if self.monitor.input_bytes else 0x80
        return self.mem[addr & 0xFFFF]

    def write8(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        if addr <= self.ram_top:
            old = self.mem[addr]
            new = value & 0xFF
            self.mem[addr] = new
            if addr in self.watch_addrs and old != new:
                pc = self.current_instruction_pc if self.current_instruction_pc is not None else self.pc
                self.watch_log.append(f"pc={pc:04X} addr={addr:04X} {old:02X}->{new:02X}")

    def read16(self, addr: int) -> int:
        hi = self.read8(addr)
        lo = self.read8(addr + 1)
        return (hi << 8) | lo

    def write16(self, addr: int, value: int) -> None:
        self.write8(addr, (value >> 8) & 0xFF)
        self.write8(addr + 1, value & 0xFF)

    def push8(self, value: int) -> None:
        self.write8(self.sp, value)
        self.sp = (self.sp - 1) & 0xFFFF

    def pull8(self) -> int:
        self.sp = (self.sp + 1) & 0xFFFF
        return self.read8(self.sp)

    def push16(self, value: int) -> None:
        # 6800 stack layout must leave the high byte at TSX+0.
        self.push8(value & 0xFF)
        self.push8((value >> 8) & 0xFF)

    def pull16(self) -> int:
        hi = self.pull8()
        lo = self.pull8()
        return (hi << 8) | lo

    def set_nz8(self, value: int) -> int:
        value &= 0xFF
        self.n = 1 if value & 0x80 else 0
        self.z = 1 if value == 0 else 0
        return value

    def set_nz16(self, value: int) -> int:
        value &= 0xFFFF
        self.n = 1 if value & 0x8000 else 0
        self.z = 1 if value == 0 else 0
        return value

    def add8(self, left: int, right: int, carry: int = 0) -> int:
        total = left + right + carry
        result = total & 0xFF
        self.h = 1 if ((left & 0x0F) + (right & 0x0F) + carry) > 0x0F else 0
        self.c = 1 if total > 0xFF else 0
        self.v = 1 if (~(left ^ right) & (left ^ result) & 0x80) != 0 else 0
        return self.set_nz8(result)

    def sub8(self, left: int, right: int, carry: int = 0) -> int:
        total = left - right - carry
        result = total & 0xFF
        self.c = 1 if total < 0 else 0
        self.v = 1 if ((left ^ right) & (left ^ result) & 0x80) != 0 else 0
        return self.set_nz8(result)

    def sub16(self, left: int, right: int) -> int:
        total = left - right
        result = total & 0xFFFF
        self.c = 1 if total < 0 else 0
        self.v = 1 if ((left ^ right) & (left ^ result) & 0x8000) != 0 else 0
        return self.set_nz16(result)

    def branch(self, condition: bool, offset: int) -> None:
        if condition:
            if offset & 0x80:
                offset -= 0x100
            self.pc = (self.pc + offset) & 0xFFFF

    def ea(self, mode: str, raw: bytes) -> int:
        if mode == "dir":
            return raw[1]
        if mode == "idx":
            return (self.x + raw[1]) & 0xFFFF
        if mode == "ext":
            return (raw[1] << 8) | raw[2]
        raise ValueError(mode)

    def call_external(self, addr: int, jump: bool) -> None:
        if addr == 0x0D49:
            # Shift the packed BCD work area used by the decimal conversion loop.
            ea = (self.x + 3) & 0xFFFF
            old = self.read8(ea)
            self.c = 1 if old & 0x80 else 0
            result = self.set_nz8((old << 1) & 0xFF)
            self.v = self.n ^ self.c
            self.write8(ea, result)

            ea = (self.x + 2) & 0xFFFF
            old = self.read8(ea)
            new_c = 1 if old & 0x80 else 0
            result = self.set_nz8(((old << 1) | self.c) & 0xFF)
            self.v = self.n ^ new_c
            self.c = new_c
            self.write8(ea, result)

            old = self.a
            new_c = 1 if old & 0x80 else 0
            self.a = self.set_nz8(((old << 1) | self.c) & 0xFF)
            self.v = self.n ^ new_c
            self.c = new_c
            return
        if addr == 0xC67B:
            # Compatibility helper for dump variants explored during OCR repair.
            # The current ROM no longer calls this address for STOP.
            self.b = self.set_nz8(0x7B)
            self.v = 0
            return
        if addr == 0x9A08:
            self.monitor.put_char(self.a)
            self.x = (self.x + 1) & 0xFFFF
            return
        if addr == 0xE1AC:
            self.a = self.monitor.get_char()
            return
        if addr == 0xE0D0:
            # EX/EXIT returns control to the monitor rather than back into BASIC.
            self.monitor.halted = True
            return
        if addr == 0xE1D1:
            self.monitor.put_char(self.a)
            if jump:
                # Tiny BASIC tail-calls the monitor output routine with JMP.
                # That monitor entry eventually RTSes to our caller.
                self.pc = self.pull16()
            return
        raise UnknownExternal(f"Unhandled external {'jmp' if jump else 'jsr'} to ${addr:04X}")

    def step(self) -> None:
        self.current_instruction_pc = self.pc
        if self.pc in EXTERNAL_ROUTINES:
            self.call_external(self.pc, jump=False)
            return
        opcode = self.read8(self.pc)
        self.trace.append((self.pc, opcode))
        if len(self.trace) > 64:
            self.trace.pop(0)
        op = OPS.get(opcode)
        if op is None:
            raise NotImplementedError(f"Opcode ${opcode:02X} not implemented at ${self.pc:04X}")
        raw = bytes(self.read8(self.pc + i) for i in range(op.size))
        self.pc = (self.pc + op.size) & 0xFFFF
        self.steps += 1

        if op.mode == "imm8":
            imm8 = raw[1]
        elif op.mode == "imm16":
            imm16 = (raw[1] << 8) | raw[2]
        elif op.mode in {"dir", "idx", "ext"}:
            ea = self.ea(op.mode, raw)
            val8 = self.read8(ea)
            val16 = self.read16(ea)
        elif op.mode == "rel":
            rel = raw[1]

        m = op.mnemonic

        if m == "nop":
            return
        if m == "tap":
            self.set_ccr(self.a)
            return
        if m == "tpa":
            # 6800 TPA forces bits 7 and 6 high in the copied status byte.
            self.a = 0xC0 | self.ccr()
            return
        if m == "inx":
            self.x = (self.x + 1) & 0xFFFF
            self.z = 1 if self.x == 0 else 0
            return
        if m == "dex":
            self.x = (self.x - 1) & 0xFFFF
            self.z = 1 if self.x == 0 else 0
            return
        if m == "clv":
            self.v = 0
            return
        if m == "sev":
            self.v = 1
            return
        if m == "clc":
            self.c = 0
            return
        if m == "sec":
            self.c = 1
            return
        if m == "cli":
            self.i = 0
            return
        if m == "sei":
            self.i = 1
            return
        if m == "sba":
            self.a = self.sub8(self.a, self.b)
            return
        if m == "cba":
            _ = self.sub8(self.a, self.b)
            return
        if m == "tab":
            self.b = self.set_nz8(self.a)
            self.v = 0
            return
        if m == "tba":
            self.a = self.set_nz8(self.b)
            self.v = 0
            return
        if m == "aba":
            self.a = self.add8(self.a, self.b)
            return
        if m == "bra":
            self.branch(True, rel)
            return
        if m == "bhi":
            self.branch((self.c | self.z) == 0, rel)
            return
        if m == "bls":
            self.branch((self.c | self.z) != 0, rel)
            return
        if m == "bcc":
            self.branch(self.c == 0, rel)
            return
        if m == "bcs":
            self.branch(self.c == 1, rel)
            return
        if m == "bne":
            self.branch(self.z == 0, rel)
            return
        if m == "beq":
            self.branch(self.z == 1, rel)
            return
        if m == "bvc":
            self.branch(self.v == 0, rel)
            return
        if m == "bvs":
            self.branch(self.v == 1, rel)
            return
        if m == "bpl":
            self.branch(self.n == 0, rel)
            return
        if m == "bmi":
            self.branch(self.n == 1, rel)
            return
        if m == "blt":
            self.branch((self.n ^ self.v) == 1, rel)
            return
        if m == "bge":
            self.branch((self.n ^ self.v) == 0, rel)
            return
        if m == "bgt":
            self.branch((self.z | (self.n ^ self.v)) == 0, rel)
            return
        if m == "ble":
            self.branch((self.z | (self.n ^ self.v)) == 1, rel)
            return
        if m == "bsr":
            self.push16(self.pc)
            self.branch(True, rel)
            return
        if m == "tsx":
            self.x = (self.sp + 1) & 0xFFFF
            return
        if m == "ins":
            self.sp = (self.sp + 1) & 0xFFFF
            return
        if m == "pula":
            self.a = self.pull8()
            return
        if m == "pulb":
            self.b = self.pull8()
            return
        if m == "des":
            self.sp = (self.sp - 1) & 0xFFFF
            return
        if m == "txs":
            self.sp = (self.x - 1) & 0xFFFF
            return
        if m == "psha":
            self.push8(self.a)
            return
        if m == "pshb":
            self.push8(self.b)
            return
        if m == "rts":
            self.pc = self.pull16()
            return
        if m == "rti":
            self.set_ccr(self.pull8())
            self.b = self.pull8()
            self.a = self.pull8()
            self.x = self.pull16()
            self.pc = self.pull16()
            return
        if m == "nega":
            self.a = self.sub8(0, self.a)
            return
        if m == "coma":
            self.a = self.set_nz8(~self.a)
            self.v = 0
            self.c = 1
            return
        if m == "lsra":
            old = self.a
            self.c = old & 1
            self.a = self.set_nz8((old >> 1) & 0xFF)
            self.n = 0
            self.v = self.n ^ self.c
            return
        if m == "rora":
            old = self.a
            new_c = old & 1
            self.a = self.set_nz8(((self.c << 7) | (old >> 1)) & 0xFF)
            self.v = self.n ^ new_c
            self.c = new_c
            return
        if m == "asra":
            old = self.a
            self.c = old & 1
            self.a = self.set_nz8(((old & 0x80) | (old >> 1)) & 0xFF)
            self.v = self.n ^ self.c
            return
        if m == "lsrd":
            value = ((self.a << 8) | self.b) & 0xFFFF
            self.c = value & 1
            value >>= 1
            self.a = (value >> 8) & 0xFF
            self.b = value & 0xFF
            self.n = 0
            self.z = 1 if value == 0 else 0
            self.v = self.n ^ self.c
            return
        if m == "asld":
            value = ((self.a << 8) | self.b) & 0xFFFF
            self.c = 1 if value & 0x8000 else 0
            value = (value << 1) & 0xFFFF
            self.a = (value >> 8) & 0xFF
            self.b = value & 0xFF
            self.n = 1 if value & 0x8000 else 0
            self.z = 1 if value == 0 else 0
            self.v = self.n ^ self.c
            return
        if m == "asla":
            old = self.a
            self.c = 1 if old & 0x80 else 0
            self.a = self.set_nz8((old << 1) & 0xFF)
            self.v = self.n ^ self.c
            return
        if m == "rola":
            old = self.a
            new_c = 1 if old & 0x80 else 0
            self.a = self.set_nz8(((old << 1) | self.c) & 0xFF)
            self.v = self.n ^ new_c
            self.c = new_c
            return
        if m == "asrb":
            old = self.b
            self.c = old & 1
            self.b = self.set_nz8(((old & 0x80) | (old >> 1)) & 0xFF)
            self.v = self.n ^ self.c
            return
        if m == "negb":
            self.b = self.sub8(0, self.b)
            return
        if m == "comb":
            self.b = self.set_nz8(~self.b)
            self.v = 0
            self.c = 1
            return
        if m == "lsrb":
            old = self.b
            self.c = old & 1
            self.b = self.set_nz8((old >> 1) & 0xFF)
            self.n = 0
            self.v = self.n ^ self.c
            return
        if m == "tsta":
            _ = self.set_nz8(self.a)
            self.v = 0
            self.c = 0
            return
        if m == "clra":
            self.a = 0
            self.set_nz8(0)
            self.v = 0
            self.c = 0
            return
        if m == "rorb":
            old = self.b
            new_c = old & 1
            self.b = self.set_nz8(((self.c << 7) | (old >> 1)) & 0xFF)
            self.v = self.n ^ new_c
            self.c = new_c
            return
        if m == "aslb":
            old = self.b
            self.c = 1 if old & 0x80 else 0
            self.b = self.set_nz8((old << 1) & 0xFF)
            self.v = self.n ^ self.c
            return
        if m == "rolb":
            old = self.b
            new_c = 1 if old & 0x80 else 0
            self.b = self.set_nz8(((old << 1) | self.c) & 0xFF)
            self.v = self.n ^ new_c
            self.c = new_c
            return
        if m == "decb":
            self.b = self.set_nz8((self.b - 1) & 0xFF)
            self.v = 1 if self.b == 0x7F else 0
            return
        if m == "incb":
            self.b = self.set_nz8((self.b + 1) & 0xFF)
            self.v = 1 if self.b == 0x80 else 0
            return
        if m == "clrb":
            self.b = 0
            self.set_nz8(0)
            self.v = 0
            self.c = 0
            return
        if m == "tstb":
            _ = self.set_nz8(self.b)
            self.v = 0
            self.c = 0
            return
        if m == "neg":
            result = self.sub8(0, val8)
            self.write8(ea, result)
            return
        if m == "com":
            result = self.set_nz8(~val8)
            self.v = 0
            self.c = 1
            self.write8(ea, result)
            return
        if m == "rol":
            old = val8
            new_c = 1 if old & 0x80 else 0
            result = self.set_nz8(((old << 1) | self.c) & 0xFF)
            self.v = self.n ^ new_c
            self.c = new_c
            self.write8(ea, result)
            return
        if m == "asl":
            old = val8
            self.c = 1 if old & 0x80 else 0
            result = self.set_nz8((old << 1) & 0xFF)
            self.v = self.n ^ self.c
            self.write8(ea, result)
            return
        if m == "ror":
            old = val8
            new_c = old & 1
            result = self.set_nz8(((self.c << 7) | (old >> 1)) & 0xFF)
            self.v = self.n ^ new_c
            self.c = new_c
            self.write8(ea, result)
            return
        if m == "dec":
            result = self.set_nz8((val8 - 1) & 0xFF)
            self.v = 1 if result == 0x7F else 0
            self.write8(ea, result)
            return
        if m == "tst":
            _ = self.set_nz8(val8)
            self.v = 0
            self.c = 0
            return
        if m == "jmp":
            if op.mode == "ext" and ea in EXTERNAL_ROUTINES:
                self.call_external(ea, jump=True)
            else:
                self.pc = ea
            return
        if m == "clr":
            self.write8(ea, 0)
            self.set_nz8(0)
            self.v = 0
            self.c = 0
            return
        if m == "inc":
            result = self.set_nz8((val8 + 1) & 0xFF)
            self.v = 1 if result == 0x80 else 0
            self.write8(ea, result)
            return
        if m == "suba":
            rhs = imm8 if op.mode == "imm8" else val8
            self.a = self.sub8(self.a, rhs)
            return
        if m == "cmpa":
            rhs = imm8 if op.mode == "imm8" else val8
            _ = self.sub8(self.a, rhs)
            return
        if m == "sbca":
            rhs = imm8 if op.mode == "imm8" else val8
            self.a = self.sub8(self.a, rhs, self.c)
            return
        if m == "anda":
            rhs = imm8 if op.mode == "imm8" else val8
            self.a = self.set_nz8(self.a & rhs)
            self.v = 0
            return
        if m == "bita":
            rhs = imm8 if op.mode == "imm8" else val8
            _ = self.set_nz8(self.a & rhs)
            self.v = 0
            return
        if m == "ldaa":
            rhs = imm8 if op.mode == "imm8" else val8
            self.a = self.set_nz8(rhs)
            self.v = 0
            return
        if m == "staa":
            self.write8(ea, self.a)
            self.set_nz8(self.a)
            self.v = 0
            return
        if m == "eora":
            rhs = imm8 if op.mode == "imm8" else val8
            self.a = self.set_nz8(self.a ^ rhs)
            self.v = 0
            return
        if m == "oraa":
            rhs = imm8 if op.mode == "imm8" else val8
            self.a = self.set_nz8(self.a | rhs)
            self.v = 0
            return
        if m == "adda":
            rhs = imm8 if op.mode == "imm8" else val8
            self.a = self.add8(self.a, rhs)
            return
        if m == "adca":
            rhs = imm8 if op.mode == "imm8" else val8
            self.a = self.add8(self.a, rhs, self.c)
            return
        if m == "cpx":
            rhs = imm16 if op.mode == "imm16" else val16
            _ = self.sub16(self.x, rhs)
            return
        if m == "lds":
            rhs = imm16 if op.mode == "imm16" else val16
            self.sp = self.set_nz16(rhs)
            self.v = 0
            return
        if m == "sts":
            self.write16(ea, self.sp)
            self.set_nz16(self.sp)
            self.v = 0
            return
        if m == "std":
            value = ((self.a << 8) | self.b) & 0xFFFF
            self.write16(ea, value)
            self.set_nz16(value)
            self.v = 0
            return
        if m == "subb":
            self.b = self.sub8(self.b, val8 if op.mode != "imm8" else imm8)
            return
        if m == "cmpb":
            _ = self.sub8(self.b, val8 if op.mode != "imm8" else imm8)
            return
        if m == "sbcb":
            self.b = self.sub8(self.b, val8 if op.mode != "imm8" else imm8, self.c)
            return
        if m == "andb":
            self.b = self.set_nz8(self.b & (val8 if op.mode != "imm8" else imm8))
            self.v = 0
            return
        if m == "bitb":
            _ = self.set_nz8(self.b & (val8 if op.mode != "imm8" else imm8))
            self.v = 0
            return
        if m == "ldab":
            self.b = self.set_nz8(val8 if op.mode != "imm8" else imm8)
            self.v = 0
            return
        if m == "stab":
            self.write8(ea, self.b)
            self.set_nz8(self.b)
            self.v = 0
            return
        if m == "eorb":
            self.b = self.set_nz8(self.b ^ (val8 if op.mode != "imm8" else imm8))
            self.v = 0
            return
        if m == "adcb":
            self.b = self.add8(self.b, val8 if op.mode != "imm8" else imm8, self.c)
            return
        if m == "orab":
            self.b = self.set_nz8(self.b | (val8 if op.mode != "imm8" else imm8))
            self.v = 0
            return
        if m == "addb":
            self.b = self.add8(self.b, val8 if op.mode != "imm8" else imm8)
            return
        if m == "ldx":
            rhs = imm16 if op.mode == "imm16" else val16
            self.x = self.set_nz16(rhs)
            self.v = 0
            return
        if m == "stx":
            self.write16(ea, self.x)
            self.set_nz16(self.x)
            self.v = 0
            return
        if m == "jsr":
            if op.mode == "dir":
                target = raw[1]
            else:
                target = ea
            if target in EXTERNAL_ROUTINES:
                self.call_external(target, jump=False)
            else:
                self.push16(self.pc)
                self.pc = target
            return

        raise NotImplementedError(f"Mnemonic {m} not implemented at ${self.pc - op.size:04X}")


def build_input(program_text: str, commands: list[str] | None = None) -> list[bytes]:
    lines = [line.rstrip("\n") for line in program_text.splitlines() if line.strip()]
    script = [(line + "\r").encode("ascii") for line in lines]
    for command in commands or ["LIST", "RUN", "5"]:
        script.append(normalize_command(command))
    return script


def parse_trace_addresses(values: list[str]) -> set[int]:
    return {int(value, 0) & 0xFFFF for value in values}


def parse_memory_ranges(values: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for value in values:
        start_text, sep, count_text = value.partition(":")
        if not sep:
            raise ValueError(f"memory range must look like <start>:<count>, got {value!r}")
        start = int(start_text, 0) & 0xFFFF
        count = int(count_text, 0)
        if count <= 0:
            raise ValueError(f"memory range count must be positive, got {value!r}")
        ranges.append((start, count))
    return ranges


def format_stack(cpu: CPU6800, count: int) -> str:
    return " ".join(f"{cpu.read8((cpu.sp + 1 + i) & 0xFFFF):02X}" for i in range(count))


def format_memory(cpu: CPU6800, start: int, count: int) -> str:
    return " ".join(f"{cpu.read8((start + i) & 0xFFFF):02X}" for i in range(count))


def normalize_command(command: str) -> bytes:
    normalized = command.rstrip("\r\n")
    stripped = normalized.strip()
    if not stripped:
        return b"\r"
    if LINE_NUMBER_RE.match(normalized):
        return (normalized + "\r").encode("ascii")
    keyword_match = re.match(r"[A-Za-z]+", stripped)
    if keyword_match is None:
        return (normalized + "\r").encode("ascii")
    keyword = keyword_match.group(0).upper()
    if keyword in DIRECT_COMMANDS:
        return (normalized + "\r").encode("ascii")
    if keyword not in IMMEDIATE_STATEMENTS:
        return (normalized + "\r").encode("ascii")
    if re.search(r"(?i)(?:^|:)\s*END\s*$", stripped):
        return (normalized + "\r").encode("ascii")
    if normalized.rstrip().endswith(":"):
        return (normalized + "END\r").encode("ascii")
    return (normalized + ":END\r").encode("ascii")


def run_session(
    image: bytes,
    script_chunks: list[bytes],
    max_steps: int,
    trace_pcs: set[int] | None = None,
    trace_stack_bytes: int = 8,
    stop_pcs: set[int] | None = None,
    watch_addrs: set[int] | None = None,
) -> RunResult:
    monitor = Monitor(input_bytes=deque(), output=[])
    watch_log: list[str] = []
    cpu = CPU6800(
        image,
        monitor,
        watch_addrs=watch_addrs,
        watch_log=watch_log,
    )
    feeder = PromptFeeder(script_chunks)
    trace_log: list[str] = []
    reason = "step_limit"

    try:
        while cpu.steps < max_steps and not monitor.halted:
            if stop_pcs and cpu.pc in stop_pcs:
                reason = f"stopped_at_pc ${cpu.pc:04X}"
                break
            if trace_pcs and cpu.pc in trace_pcs:
                trace_log.append(
                    f"pc={cpu.pc:04X} sp={cpu.sp:04X} x={cpu.x:04X} "
                    f"a={cpu.a:02X} b={cpu.b:02X} stack={format_stack(cpu, trace_stack_bytes)}"
                )
            cpu.step()
            feeder.feed(monitor, auto_mode=cpu.read8(0x13) != 0, cpu=cpu)
    except EndOfInput:
        reason = "input_exhausted"
    except UnknownExternal as exc:
        reason = str(exc)
    except NotImplementedError as exc:
        reason = str(exc)
    else:
        if monitor.halted:
            reason = "monitor_exit"

    text = render_output(monitor.output)
    return RunResult(reason=reason, text=text, cpu=cpu, trace_log=trace_log, watch_log=watch_log)


def prompt_needs_input(new_output: list[int], auto_mode: bool) -> bool:
    return ends_with_prompt(new_output) or ends_with_auto_number_prompt(new_output, auto_mode)


def run_repl_session(
    image: bytes,
    max_steps: int,
    trace_pcs: set[int] | None = None,
    trace_stack_bytes: int = 8,
    stop_pcs: set[int] | None = None,
    watch_addrs: set[int] | None = None,
) -> RunResult:
    monitor = Monitor(input_bytes=deque(), output=[])
    watch_log: list[str] = []
    cpu = CPU6800(
        image,
        monitor,
        watch_addrs=watch_addrs,
        watch_log=watch_log,
    )
    trace_log: list[str] = []
    reason = "step_limit"
    rendered_len = 0
    prompt_window_start = 0

    try:
        while cpu.steps < max_steps and not monitor.halted:
            if stop_pcs and cpu.pc in stop_pcs:
                reason = f"stopped_at_pc ${cpu.pc:04X}"
                break
            if trace_pcs and cpu.pc in trace_pcs:
                trace_log.append(
                    f"pc={cpu.pc:04X} sp={cpu.sp:04X} x={cpu.x:04X} "
                    f"a={cpu.a:02X} b={cpu.b:02X} stack={format_stack(cpu, trace_stack_bytes)}"
                )
            cpu.step()
            if len(monitor.output) <= rendered_len:
                continue
            new_output = monitor.output[rendered_len:]
            new_text = render_output(new_output)
            if new_text:
                sys.stdout.write(new_text)
                sys.stdout.flush()
            rendered_len = len(monitor.output)
            prompt_output = monitor.output[prompt_window_start:]
            if not prompt_needs_input(prompt_output, auto_mode=cpu.read8(0x13) != 0):
                continue
            try:
                line = sys.stdin.readline()
            except KeyboardInterrupt:
                monitor.input_bytes.append(0x03)
                prompt_window_start = len(monitor.output)
                continue
            if line == "":
                reason = "stdin_eof"
                break
            prepared = prepare_input_line(line.rstrip("\r\n"), prompt_kind="question" if prompt_output and current_prompt_kind(prompt_output, cpu.read8(0x13) != 0) == "question" else "command")
            if prepared.synthetic_error is not None:
                trigger_synthetic_error(cpu, prepared.synthetic_error)
                prompt_window_start = len(monitor.output)
                continue
            for chunk in prepared.chunks:
                monitor.input_bytes.extend(chunk)
            prompt_window_start = len(monitor.output)
    except EndOfInput:
        reason = "input_exhausted"
    except UnknownExternal as exc:
        reason = str(exc)
    except NotImplementedError as exc:
        reason = str(exc)
    else:
        if monitor.halted:
            reason = "monitor_exit"

    text = render_output(monitor.output)
    return RunResult(reason=reason, text=text, cpu=cpu, trace_log=trace_log, watch_log=watch_log)


def print_result_summary(
    result: RunResult,
    trace_on_stop: int,
    dump_memory_ranges: list[tuple[int, int]],
    include_transcript: bool,
) -> None:
    if result.trace_log:
        print("trace-pc log:")
        for line in result.trace_log:
            print(f"  {line}")
    if result.watch_log:
        print("watch-write log:")
        for line in result.watch_log:
            print(f"  {line}")
    print(f"reason: {result.reason}")
    print(f"steps: {result.cpu.steps}")
    print(
        f"pc: {result.cpu.pc:04X} sp: {result.cpu.sp:04X} "
        f"x: {result.cpu.x:04X} a: {result.cpu.a:02X} b: {result.cpu.b:02X}"
    )
    print("trace:")
    for pc, opcode in result.cpu.trace[-trace_on_stop:]:
        print(f"  {pc:04X}: {opcode:02X}")
    if dump_memory_ranges:
        print("memory:")
        for start, count in dump_memory_ranges:
            print(f"  {start:04X}: {format_memory(result.cpu, start, count)}")
    if include_transcript:
        print("--- transcript start ---")
        print(format_transcript_for_display(result.text))
        print("--- transcript end ---")


def format_transcript_for_display(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if not lines:
        return text
    filtered_lines = [line for line in lines if line.rstrip("\r\n") != "#"]
    if len(filtered_lines) == len(lines):
        return text
    return "".join(filtered_lines).rstrip("\r\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Tiny BASIC under a minimal 6800 console harness.")
    parser.add_argument("binary", type=Path, help="Normalized Tiny BASIC binary")
    parser.add_argument(
        "program",
        type=Path,
        nargs="?",
        help="Optional BASIC program file to type in before any --command values.",
    )
    parser.add_argument("--max-steps", type=int, default=120_000_000, help="Instruction limit")
    parser.add_argument("--output", type=Path, help="Optional transcript path")
    parser.add_argument(
        "--command",
        action="append",
        default=[],
        help="Extra command to feed after typing the BASIC program. Defaults to LIST, RUN, 5.",
    )
    parser.add_argument(
        "--trace-pc",
        action="append",
        default=[],
        help="Record CPU state whenever one of these PCs is about to execute. Accepts hex like 0x577.",
    )
    parser.add_argument(
        "--trace-stack-bytes",
        type=int,
        default=8,
        help="Number of stack bytes to include in each trace-pc record.",
    )
    parser.add_argument(
        "--trace-on-stop",
        type=int,
        default=20,
        help="Number of trailing executed PCs/opcodes to print when the run stops.",
    )
    parser.add_argument(
        "--stop-at-pc",
        action="append",
        default=[],
        help="Stop before executing one of these PCs. Accepts hex like 0x750.",
    )
    parser.add_argument(
        "--dump-memory",
        action="append",
        default=[],
        help="Print memory after the run using <start>:<count>, for example 0x00FA:8.",
    )
    parser.add_argument(
        "--watch-write",
        action="append",
        default=[],
        help="Log writes to one of these addresses. Accepts hex like 0x13.",
    )
    args = parser.parse_args()

    image = args.binary.read_bytes()
    trace_pcs = parse_trace_addresses(args.trace_pc)
    stop_pcs = parse_trace_addresses(args.stop_at_pc)
    watch_addrs = parse_trace_addresses(args.watch_write)
    dump_memory_ranges = parse_memory_ranges(args.dump_memory)
    if args.program is not None:
        script_chunks = build_input(args.program.read_text(), args.command or None)
        result = run_session(
            image,
            script_chunks,
            args.max_steps,
            trace_pcs,
            args.trace_stack_bytes,
            stop_pcs,
            watch_addrs,
        )
        if args.output:
            args.output.write_text(result.text)
        print_result_summary(result, args.trace_on_stop, dump_memory_ranges, include_transcript=True)
        return 0
    if args.command:
        script_chunks = [normalize_command(command) for command in args.command]
        result = run_session(
            image,
            script_chunks,
            args.max_steps,
            trace_pcs,
            args.trace_stack_bytes,
            stop_pcs,
            watch_addrs,
        )
        if args.output:
            args.output.write_text(result.text)
        print_result_summary(result, args.trace_on_stop, dump_memory_ranges, include_transcript=True)
        return 0

    result = run_repl_session(
        image,
        args.max_steps,
        trace_pcs,
        args.trace_stack_bytes,
        stop_pcs,
        watch_addrs,
    )
    if args.output:
        args.output.write_text(result.text)
    if result.reason not in {"stdin_eof", "monitor_exit"}:
        print_result_summary(result, args.trace_on_stop, dump_memory_ranges, include_transcript=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
