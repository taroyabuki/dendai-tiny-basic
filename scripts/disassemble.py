#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


BASE = 0x0100
MANUAL_DATA_RANGES = [
    (0x087E, 0x093B),
]
NAMED_LABELS = {
    0x0100: "ENTRY",
    0x087E: "KEYWORD_TABLE",
    0x0927: "ERROR_MSG",
    0x092E: "READY_MSG",
    0x0950: "AUTO_HELPER",
    0x0963: "DIRECT_END_HELPER",
}


@dataclass(frozen=True)
class Op:
    mnemonic: str
    mode: str
    size: int
    valid: bool = True


OPS: dict[int, Op] = {
    0x01: Op("nop", "inh", 1),
    0x04: Op("lsrd", "inh", 1),
    0x05: Op("asld", "inh", 1),
    0x06: Op("tap", "inh", 1),
    0x07: Op("tpa", "inh", 1),
    0x08: Op("inx", "inh", 1),
    0x09: Op("dex", "inh", 1),
    0x0A: Op("clv", "inh", 1),
    0x0B: Op("sev", "inh", 1),
    0x0C: Op("clc", "inh", 1),
    0x0D: Op("sec", "inh", 1),
    0x0E: Op("cli", "inh", 1),
    0x0F: Op("sei", "inh", 1),
    0x10: Op("sba", "inh", 1),
    0x11: Op("cba", "inh", 1),
    0x16: Op("tab", "inh", 1),
    0x17: Op("tba", "inh", 1),
    0x19: Op("daa", "inh", 1),
    0x1B: Op("aba", "inh", 1),
    0x20: Op("bra", "rel", 2),
    0x22: Op("bhi", "rel", 2),
    0x23: Op("bls", "rel", 2),
    0x24: Op("bcc", "rel", 2),
    0x25: Op("bcs", "rel", 2),
    0x26: Op("bne", "rel", 2),
    0x27: Op("beq", "rel", 2),
    0x28: Op("bvc", "rel", 2),
    0x29: Op("bvs", "rel", 2),
    0x2A: Op("bpl", "rel", 2),
    0x2B: Op("bmi", "rel", 2),
    0x2C: Op("bge", "rel", 2),
    0x2D: Op("blt", "rel", 2),
    0x2E: Op("bgt", "rel", 2),
    0x2F: Op("ble", "rel", 2),
    0x30: Op("tsx", "inh", 1),
    0x31: Op("ins", "inh", 1),
    0x32: Op("pula", "inh", 1),
    0x33: Op("pulb", "inh", 1),
    0x34: Op("des", "inh", 1),
    0x35: Op("txs", "inh", 1),
    0x36: Op("psha", "inh", 1),
    0x37: Op("pshb", "inh", 1),
    0x39: Op("rts", "inh", 1),
    0x3B: Op("rti", "inh", 1),
    0x3F: Op("swi", "inh", 1),
    0x40: Op("nega", "inh", 1),
    0x43: Op("coma", "inh", 1),
    0x44: Op("lsra", "inh", 1),
    0x46: Op("rora", "inh", 1),
    0x47: Op("asra", "inh", 1),
    0x48: Op("asla", "inh", 1),
    0x49: Op("rola", "inh", 1),
    0x4A: Op("deca", "inh", 1),
    0x4C: Op("inca", "inh", 1),
    0x4D: Op("tsta", "inh", 1),
    0x4F: Op("clra", "inh", 1),
    0x50: Op("negb", "inh", 1),
    0x53: Op("comb", "inh", 1),
    0x54: Op("lsrb", "inh", 1),
    0x56: Op("rorb", "inh", 1),
    0x57: Op("asrb", "inh", 1),
    0x58: Op("aslb", "inh", 1),
    0x59: Op("rolb", "inh", 1),
    0x5A: Op("decb", "inh", 1),
    0x5C: Op("incb", "inh", 1),
    0x5D: Op("tstb", "inh", 1),
    0x5F: Op("clrb", "inh", 1),
    0x60: Op("neg", "idx", 2),
    0x63: Op("com", "idx", 2),
    0x64: Op("lsr", "idx", 2),
    0x66: Op("ror", "idx", 2),
    0x67: Op("asr", "idx", 2),
    0x68: Op("asl", "idx", 2),
    0x69: Op("rol", "idx", 2),
    0x6A: Op("dec", "idx", 2),
    0x6C: Op("inc", "idx", 2),
    0x6D: Op("tst", "idx", 2),
    0x6E: Op("jmp", "idx", 2),
    0x6F: Op("clr", "idx", 2),
    0x70: Op("neg", "ext", 3),
    0x73: Op("com", "ext", 3),
    0x74: Op("lsr", "ext", 3),
    0x76: Op("ror", "ext", 3),
    0x77: Op("asr", "ext", 3),
    0x78: Op("asl", "ext", 3),
    0x79: Op("rol", "ext", 3),
    0x7A: Op("dec", "ext", 3),
    0x7C: Op("inc", "ext", 3),
    0x7D: Op("tst", "ext", 3),
    0x7E: Op("jmp", "ext", 3),
    0x7F: Op("clr", "ext", 3),
    0x80: Op("suba", "imm8", 2),
    0x81: Op("cmpa", "imm8", 2),
    0x82: Op("sbca", "imm8", 2),
    0x84: Op("anda", "imm8", 2),
    0x85: Op("bita", "imm8", 2),
    0x86: Op("ldaa", "imm8", 2),
    0x88: Op("eora", "imm8", 2),
    0x89: Op("adca", "imm8", 2),
    0x8A: Op("oraa", "imm8", 2),
    0x8B: Op("adda", "imm8", 2),
    0x8C: Op("cpx", "imm16", 3),
    0x8D: Op("bsr", "rel", 2),
    0x8E: Op("lds", "imm16", 3),
    0x90: Op("suba", "dir", 2),
    0x91: Op("cmpa", "dir", 2),
    0x92: Op("sbca", "dir", 2),
    0x94: Op("anda", "dir", 2),
    0x95: Op("bita", "dir", 2),
    0x96: Op("ldaa", "dir", 2),
    0x97: Op("staa", "dir", 2),
    0x98: Op("eora", "dir", 2),
    0x99: Op("adca", "dir", 2),
    0x9A: Op("oraa", "dir", 2),
    0x9B: Op("adda", "dir", 2),
    0x9C: Op("cpx", "dir", 2),
    0x9D: Op("jsr", "dir", 2),
    0x9E: Op("lds", "dir", 2),
    0x9F: Op("sts", "dir", 2),
    0xA0: Op("suba", "idx", 2),
    0xA1: Op("cmpa", "idx", 2),
    0xA2: Op("sbca", "idx", 2),
    0xA4: Op("anda", "idx", 2),
    0xA5: Op("bita", "idx", 2),
    0xA6: Op("ldaa", "idx", 2),
    0xA7: Op("staa", "idx", 2),
    0xA8: Op("eora", "idx", 2),
    0xA9: Op("adca", "idx", 2),
    0xAA: Op("oraa", "idx", 2),
    0xAB: Op("adda", "idx", 2),
    0xAC: Op("cpx", "idx", 2),
    0xAD: Op("jsr", "idx", 2),
    0xAE: Op("lds", "idx", 2),
    0xAF: Op("sts", "idx", 2),
    0xB0: Op("suba", "ext", 3),
    0xB1: Op("cmpa", "ext", 3),
    0xB2: Op("sbca", "ext", 3),
    0xB4: Op("anda", "ext", 3),
    0xB5: Op("bita", "ext", 3),
    0xB6: Op("ldaa", "ext", 3),
    0xB7: Op("staa", "ext", 3),
    0xB8: Op("eora", "ext", 3),
    0xB9: Op("adca", "ext", 3),
    0xBA: Op("oraa", "ext", 3),
    0xBB: Op("adda", "ext", 3),
    0xBC: Op("cpx", "ext", 3),
    0xBD: Op("jsr", "ext", 3),
    0xBE: Op("lds", "ext", 3),
    0xBF: Op("sts", "ext", 3),
    0xC0: Op("subb", "imm8", 2),
    0xC1: Op("cmpb", "imm8", 2),
    0xC2: Op("sbcb", "imm8", 2),
    0xC4: Op("andb", "imm8", 2),
    0xC5: Op("bitb", "imm8", 2),
    0xC6: Op("ldab", "imm8", 2),
    0xC8: Op("eorb", "imm8", 2),
    0xC9: Op("adcb", "imm8", 2),
    0xCA: Op("orab", "imm8", 2),
    0xCB: Op("addb", "imm8", 2),
    0xCC: Op("ldd", "imm16", 3),
    0xCE: Op("ldx", "imm16", 3),
    0xD0: Op("subb", "dir", 2),
    0xD1: Op("cmpb", "dir", 2),
    0xD2: Op("sbcb", "dir", 2),
    0xD4: Op("andb", "dir", 2),
    0xD5: Op("bitb", "dir", 2),
    0xD6: Op("ldab", "dir", 2),
    0xD7: Op("stab", "dir", 2),
    0xD8: Op("eorb", "dir", 2),
    0xD9: Op("adcb", "dir", 2),
    0xDA: Op("orab", "dir", 2),
    0xDB: Op("addb", "dir", 2),
    0xDC: Op("ldd", "dir", 2),
    0xDD: Op("std", "dir", 2),
    0xDE: Op("ldx", "dir", 2),
    0xDF: Op("stx", "dir", 2),
    0xE0: Op("subb", "idx", 2),
    0xE1: Op("cmpb", "idx", 2),
    0xE2: Op("sbcb", "idx", 2),
    0xE4: Op("andb", "idx", 2),
    0xE5: Op("bitb", "idx", 2),
    0xE6: Op("ldab", "idx", 2),
    0xE7: Op("stab", "idx", 2),
    0xE8: Op("eorb", "idx", 2),
    0xE9: Op("adcb", "idx", 2),
    0xEA: Op("orab", "idx", 2),
    0xEB: Op("addb", "idx", 2),
    0xEC: Op("ldd", "idx", 2),
    0xED: Op("std", "idx", 2),
    0xEE: Op("ldx", "idx", 2),
    0xEF: Op("stx", "idx", 2),
    0xF0: Op("subb", "ext", 3),
    0xF1: Op("cmpb", "ext", 3),
    0xF2: Op("sbcb", "ext", 3),
    0xF4: Op("andb", "ext", 3),
    0xF5: Op("bitb", "ext", 3),
    0xF6: Op("ldab", "ext", 3),
    0xF7: Op("stab", "ext", 3),
    0xF8: Op("eorb", "ext", 3),
    0xF9: Op("adcb", "ext", 3),
    0xFA: Op("orab", "ext", 3),
    0xFB: Op("addb", "ext", 3),
    0xFC: Op("ldd", "ext", 3),
    0xFD: Op("std", "ext", 3),
    0xFE: Op("ldx", "ext", 3),
    0xFF: Op("stx", "ext", 3),
}

TERMINATORS = {"jmp", "rts", "rti", "swi"}
COND_BRANCHES = {
    "bhi",
    "bls",
    "bcc",
    "bcs",
    "bne",
    "beq",
    "bvc",
    "bvs",
    "bpl",
    "bmi",
    "bge",
    "blt",
    "bgt",
    "ble",
}


@dataclass
class Decoded:
    address: int
    op: Op
    bytes_: bytes
    text: str
    targets: list[int]
    falls_through: bool


def in_manual_data(address: int) -> bool:
    for start, end in MANUAL_DATA_RANGES:
        if start <= address <= end:
            return True
    return False


def is_internal(address: int, image: bytes) -> bool:
    return BASE <= address < BASE + len(image)


def signed_byte(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def label_for(address: int, image: bytes) -> str:
    if address in NAMED_LABELS:
        return NAMED_LABELS[address]
    if is_internal(address, image):
        return f"L{address:04X}"
    return f"MON_{address:04X}"


def decode_one(image: bytes, address: int) -> Decoded | None:
    if not is_internal(address, image) or in_manual_data(address):
        return None
    offset = address - BASE
    opcode = image[offset]
    op = OPS.get(opcode)
    if op is None:
        return None
    if offset + op.size > len(image):
        return None
    raw = image[offset : offset + op.size]
    operand = ""
    targets: list[int] = []
    if op.mode == "inh":
        operand = ""
    elif op.mode == "imm8":
        operand = f"#$%02X" % raw[1]
    elif op.mode == "imm16":
        value = (raw[1] << 8) | raw[2]
        if op.mnemonic in {"ldx", "lds", "ldd", "cpx"} and is_internal(value, image):
            operand = f"#{label_for(value, image)}"
            targets.append(value)
        else:
            operand = f"#$%04X" % value
    elif op.mode == "dir":
        operand = f"$%02X" % raw[1]
    elif op.mode == "idx":
        operand = f"$%02X,x" % raw[1]
    elif op.mode == "ext":
        value = (raw[1] << 8) | raw[2]
        operand = label_for(value, image)
        targets.append(value)
    elif op.mode == "rel":
        value = (address + op.size + signed_byte(raw[1])) & 0xFFFF
        operand = label_for(value, image)
        targets.append(value)
    else:
        raise ValueError(f"unsupported addressing mode {op.mode}")

    text = op.mnemonic if not operand else f"{op.mnemonic} {operand}"
    falls_through = op.mnemonic not in TERMINATORS and op.mnemonic != "bra"
    return Decoded(address=address, op=op, bytes_=raw, text=text, targets=targets, falls_through=falls_through)


def discover_code(image: bytes) -> tuple[dict[int, Decoded], set[int], set[int]]:
    decoded: dict[int, Decoded] = {}
    internal_targets: set[int] = {BASE}
    external_targets: set[int] = set()
    queue = [BASE]
    seen: set[int] = set()

    while queue:
        address = queue.pop()
        if address in seen or not is_internal(address, image) or in_manual_data(address):
            continue
        seen.add(address)
        current = address
        while is_internal(current, image) and not in_manual_data(current) and current not in decoded:
            inst = decode_one(image, current)
            if inst is None:
                break
            decoded[current] = inst
            for target in inst.targets:
                if is_internal(target, image):
                    internal_targets.add(target)
                    queue.append(target)
                else:
                    external_targets.add(target)
            if inst.op.mnemonic in COND_BRANCHES or inst.op.mnemonic == "bsr":
                queue.append(current + inst.op.size)
            if not inst.falls_through:
                break
            current += inst.op.size
    return decoded, internal_targets, external_targets


def prune_overlaps(decoded: dict[int, Decoded], internal_targets: set[int]) -> dict[int, Decoded]:
    pruned = dict(decoded)
    changed = True
    while changed:
        changed = False
        for address, inst in list(pruned.items()):
            covered = range(address + 1, address + inst.op.size)
            if any(target in covered for target in internal_targets):
                del pruned[address]
                changed = True
    return pruned


def fcb_line(values: bytes) -> str:
    return "db " + ",".join(f"$%02X" % value for value in values)


def emit_asm(image: bytes, decoded: dict[int, Decoded], internal_targets: set[int], external_targets: set[int]) -> str:
    lines: list[str] = []
    lines.append("CPU 6800")
    lines.append("*=$0100")
    lines.append("")
    for ext in sorted(external_targets):
        lines.append(f"{label_for(ext, image)} equ ${ext:04X}")
    if external_targets:
        lines.append("")

    end = BASE + len(image)
    address = BASE
    while address < end:
        label = ""
        if address in internal_targets or address in NAMED_LABELS:
            label = label_for(address, image)

        if address in decoded:
            inst = decoded[address]
            if label:
                lines.append(f"{label} {inst.text}")
            else:
                lines.append(f" {inst.text}")
            address += inst.op.size
            continue

        chunk_start = address
        chunk: list[int] = []
        while address < end and address not in decoded and address not in internal_targets and address not in NAMED_LABELS and len(chunk) < 8:
            chunk.append(image[address - BASE])
            address += 1
        if not chunk and address < end:
            chunk.append(image[address - BASE])
            address += 1
        if label:
            lines.append(f"{label} {fcb_line(bytes(chunk))}")
        else:
            lines.append(f" {fcb_line(bytes(chunk))}")
        if chunk_start in {start for start, _ in MANUAL_DATA_RANGES}:
            lines.append("")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Disassemble the normalized Tiny BASIC image into CRASM syntax.")
    parser.add_argument("binary", type=Path, help="Input binary image")
    parser.add_argument("output", type=Path, help="Output asm path")
    args = parser.parse_args()

    image = args.binary.read_bytes()
    decoded, internal_targets, external_targets = discover_code(image)
    decoded = prune_overlaps(decoded, internal_targets)
    asm = emit_asm(image, decoded, internal_targets, external_targets)
    args.output.write_text(asm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
