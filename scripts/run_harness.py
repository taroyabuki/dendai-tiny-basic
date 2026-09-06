#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import signal
import sys
import threading
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.disassemble import OPS


class EndOfInput(Exception):
    pass


class UnknownExternal(Exception):
    pass


DEFAULT_MONITOR_STACK = 0xD900
MONITOR_STACK_SLOT = 0xA047
EXTERNAL_ROUTINES = {0xE0D0, 0xE1AC, 0xE1D1}


@dataclass
class Monitor:
    input_bytes: deque[int]
    output: list[int]
    halted: bool = False
    input_provider: Callable[[], bytes | None] | None = None

    def get_char(self) -> int:
        if not self.input_bytes and self.input_provider is not None:
            self.input_bytes.extend(self.input_provider() or b"")
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
            target = self.pc
            self.steps += 1
            self.call_external(target, jump=True)
            if not self.monitor.halted and target != 0xE1D1:
                self.pc = self.pull16()
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
        if m in {"inca", "deca"}:
            delta = 1 if m == "inca" else -1
            self.a = self.set_nz8(self.a + delta)
            self.v = int(self.a == (0x80 if delta == 1 else 0x7F))
            return
        if m in {"lsr", "asr"}:
            self.c = val8 & 1
            result = (val8 >> 1) | (val8 & 0x80 if m == "asr" else 0)
            self.write8(ea, self.set_nz8(result))
            self.v = self.n ^ self.c
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
            if ea in EXTERNAL_ROUTINES:
                self.call_external(ea, jump=True)
                if not self.monitor.halted and ea != 0xE1D1:
                    self.pc = self.pull16()
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
    script = [normalize_command(line) for line in program_text.splitlines()]
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
    """Convert host line endings only; BASIC parses the unchanged source."""
    return (command.rstrip("\r\n") + "\r").encode("ascii")


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
    chunks = iter(script_chunks)
    monitor.input_provider = lambda: next(chunks, None)
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
    reading_stdin = False

    def read_line() -> bytes | None:
        nonlocal reading_stdin
        try:
            reading_stdin = True
            line = sys.stdin.readline()
            return normalize_command(line) if line else None
        except KeyboardInterrupt:
            return b"\x03"
        finally:
            reading_stdin = False

    def request_break(signum: int, frame: object) -> None:
        if reading_stdin:
            raise KeyboardInterrupt
        monitor.input_bytes.clear()
        monitor.input_bytes.append(0x03)

    monitor.input_provider = read_line
    previous_handler = None
    if threading.current_thread() is threading.main_thread():
        previous_handler = signal.signal(signal.SIGINT, request_break)

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
            try:
                new_text = render_output(monitor.output[rendered_len:])
                if new_text:
                    sys.stdout.write(new_text)
                    sys.stdout.flush()
                rendered_len = len(monitor.output)
                cpu.step()
            except KeyboardInterrupt:
                monitor.input_bytes.clear()
                monitor.input_bytes.append(0x03)
                continue
    except EndOfInput:
        reason = "stdin_eof"
    except UnknownExternal as exc:
        reason = str(exc)
    except NotImplementedError as exc:
        reason = str(exc)
    else:
        if monitor.halted:
            reason = "monitor_exit"

    finally:
        if previous_handler is not None:
            signal.signal(signal.SIGINT, previous_handler)

    sys.stdout.write(render_output(monitor.output[rendered_len:]))
    sys.stdout.flush()
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


def result_exit_code(result: RunResult) -> int:
    if result.reason in {"input_exhausted", "stdin_eof", "monitor_exit"} or result.reason.startswith("stopped_at_pc "):
        return 0
    return 1


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
        return result_exit_code(result)
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
        return result_exit_code(result)

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
    return result_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
