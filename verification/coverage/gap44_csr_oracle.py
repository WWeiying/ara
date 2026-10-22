"""Independent fixed opcode/trap oracle. Imports neither the C nor DUT results."""
import re
import struct

NAME = "csr_gap44_absent"
TEST = "rvv:" + NAME
FORMAT = "gap44-csr-spike-v1"
RUNTIME_FORMAT = "gap44-csr-uart-generic-trace-v1"
PHASES, ILLEGAL, CHECKS = 52, 50, 1290
SENTINEL = 0x1122334455667788
SCRATCH = 0xa596f00f24681357
RECOVERY = 0x93a5c7e901234567
SEEDS = (0x13579bdf2468ace0, 0xfedcba9876543210)


def require(ok, message):
    if not ok:
        raise ValueError("gap44: " + message)


def stub_address(data):
    """Read the actual ELF64 symbol table, never trust a supplied nm listing."""
    require(data[:7] == b"\x7fELF\x02\x01\x01", "not little-endian ELF64")
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    require(header[1:4] == (2, 243, 1) and header[11] == 64, "wrong ELF target/type")
    offset, size, count = header[6], header[11], header[12]
    require(count > 0 and offset + size * count <= len(data), "invalid ELF sections")
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, offset + i * size) for i in range(count)]
    found = []
    for section in sections:
        if section[1] != 2:
            continue
        require(section[9] == 24 and section[5] % 24 == 0 and section[6] < count, "invalid ELF symbols")
        strings = sections[section[6]]
        names = data[strings[4]:strings[4] + strings[5]]
        require(section[4] + section[5] <= len(data) and len(names) == strings[5], "truncated ELF")
        for pos in range(section[4], section[4] + section[5], 24):
            name, info, _, index, value, length = struct.unpack_from("<IBBHQQ", data, pos)
            require(name < len(names) and b"\0" in names[name:], "invalid ELF name")
            if names[name:].split(b"\0", 1)[0] == b"csr_gap35_stub":
                require(info & 15 == 1 and 0 < index < count and length == 8,
                        "wrong probe symbol type/size")
                owner = sections[index]
                require(owner[2] & 3 == 3 and owner[3] <= value and value + 8 <= owner[3] + owner[5],
                        "probe symbol is not allocated writable storage")
                found.append(value)
    require(len(found) == 1 and found[0] % 64 == 0, "missing/ambiguous/unaligned ELF stub")
    return found[0]


def expected_probes(stub):
    rows = []

    def add(csr, write, legal=False, rd=SENTINEL):
        insn = (csr << 20) | ((11 if write else 0) << 15) | ((1 if write else 2) << 12) | (13 << 7) | 0x73
        rows.append(dict(phase=len(rows), priv=3, insn=insn, legal=int(legal),
                         cause=11 if legal else 2, epc=stub + (4 if legal else 0),
                         tval=0 if legal else insn, rd=rd))

    add(0x340, True, True, SCRATCH)
    # Architectural address list is intentionally independent of the C table.
    for csr in (0x200, 0x204, 0x205, 0x240, 0x241, 0x242, 0x243, 0x244, 0x280,
                0x600, 0x602, 0x603, 0x604, 0x606, 0x607, 0x60a, 0x643, 0x644,
                0x645, 0x64a, 0x680, 0x34a, 0x34b):
        add(csr, False)
        add(csr, True)
    add(0xe12, False)
    add(0xb83, False)
    add(0xb83, True)
    add(0xc83, False)
    add(0x340, False, True, RECOVERY)
    require(len(rows) == PHASES and sum(not r["legal"] for r in rows) == ILLEGAL, "oracle dimensions")
    return rows


def validate_capability(log):
    expected = [f"HPM_CAP pattern={seed:x} read=0 shadow=0 stable=0" for seed in SEEDS]
    require(log.splitlines() == expected, "pinned Spike HPM capability differs")
    return dict(profile="spike-raz", writable=False, dut_preservation_proved=False)


def validate_log(log, spike, stub=None):
    lines = log.splitlines()
    require(not re.search(r"(?i)\bFAIL(?:ED)?\b|\bFatal:|\bError:", log), "failure marker")
    summary = f"{NAME} phases={PHASES} checks={CHECKS} illegal={ILLEGAL} legal=2 failures=0"
    require([s for s in lines if s.startswith(NAME + " phases=")] == [summary], "exact summary required")
    require([s for s in lines if s.startswith("PASSED:")] == ["PASSED: " + NAME], "unique PASS required")
    guard = ("HPM_GUARD profile=spike-raz writable=0 seed_a=0 seed_b=0 stable=0 after=0 event=0"
             if spike else f"HPM_GUARD profile=dut-rw writable=1 seed_a={SEEDS[0]:x} seed_b={SEEDS[1]:x} "
             f"stable={SEEDS[1]:x} after={SEEDS[1]:x} event=0")
    require([s for s in lines if s.startswith("HPM_GUARD")] == [guard], "nonzero DUT HPM guard/profile required")
    require(lines.index(guard) < lines.index(summary) < lines.index("PASSED: " + NAME), "evidence order")
    raw = [s for s in lines if s.startswith("PROBE")]
    probes = []
    if spike:
        require(type(stub) is int and stub % 64 == 0 and len(raw) == PHASES, "exact ELF-bound probe count")
        pattern = (r"PROBE phase=(\d+) priv=(\d+) insn=([0-9a-f]+) legal=(\d+) "
                   r"cause=([0-9a-f]+) epc=([0-9a-f]+) tval=([0-9a-f]+) rd=([0-9a-f]+)")
        for index, (line, expected) in enumerate(zip(raw, expected_probes(stub))):
            match = re.fullmatch(pattern, line)
            require(match is not None, "malformed PROBE")
            values = [int(v, 10 if i in (0, 1, 3) else 16) for i, v in enumerate(match.groups())]
            observed = dict(zip(("phase", "priv", "insn", "legal", "cause", "epc", "tval", "rd"), values))
            require(observed == expected, f"independent probe {index} differs")
            probes.append(observed)
        require(lines.index(raw[50]) < lines.index(guard) < lines.index(raw[51]) < lines.index(summary),
                "recovery/guard order")
    else:
        require(not raw, "unexpected DUT PROBE stream")
    return dict(phases=PHASES, checks=CHECKS, illegal=ILLEGAL, legal=2, failures=0,
                hpm_profile="spike-raz" if spike else "dut-rw", hpm_nonzero_preservation=not spike,
                probes=probes)
