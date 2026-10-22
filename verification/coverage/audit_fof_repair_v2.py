"""Original FOF fixture acceptance with bitwise unknown-tail provenance.

audit(directory) retains the sealed v1 scalar, RAM, context, lifecycle and
terminal checks. Only native vector state handling is replaced. No EDA/pins
from historical RTL, no whole-writer exemption, no unknown byte-enable waiver.
"""
from collections import Counter
import csv
from dataclasses import dataclass
from pathlib import Path
from types import FunctionType

import audit_fof_repair as base

require, vc = base.require, base.vc
BASE_SHA = 'f26ca1666247361a853f8395d000e1c24319e84016add0856180103bfd1ad801'


@dataclass(frozen=True)
class BitWrite(vc.VectorWrite):
    known_bits: int = 0
    z_bits: int = 0


def parse_wdata(text):
    require(len(text) == 16 and all(c in '0123456789abcdefxXzZ' for c in text),
            'Exact 64-bit native data encoding')
    value = known = highz = 0
    for nibble, char in enumerate(reversed(text.lower())):
        shift = 4 * nibble
        if char == 'z':
            highz |= 15 << shift
        elif char != 'x':
            value |= int(char, 16) << shift
            known |= 15 << shift
    return value, known, highz


def parse_native(path):
    # The shared parser strictly rejects unknown BE, including the measured 0x.
    lanes, vlen, activities = vc._parse_vector_trace(path)
    with Path(path).open(newline='') as stream:
        rows = {i: r for i, r in enumerate(csv.DictReader(stream), start=2)}
    for activity in activities.values():
        writes = []
        for w in activity.writes:
            data, bits, highz = parse_wdata(rows[w.row]['wdata'])
            writes.append(BitWrite(**dict(vars(w), data=data), known_bits=bits, z_bits=highz))
        activity.writes = writes
    return lanes, vlen, activities


def byte_events(write):
    require(0 <= write.addr < 128 and 0 <= write.lane < 4 and
            0 <= write.eew <= 3 and 0 <= write.be < 256, 'Invalid native write metadata')
    known = getattr(write, 'known_bits', sum(255 << (8 * b) for b in range(8)
                    if write.known_be >> b & 1))
    highz = getattr(write, 'z_bits', 0)
    reg, word = divmod(write.addr, 4)
    for byte in range(8):
        if not write.be >> byte & 1:
            continue
        require(not (highz >> (8 * byte) & 255), 'High-Z enabled native data')
        index = word * 32 + vc._deshuffle_byte(write.lane * 8 + byte, 4, write.eew)
        yield (reg, index), (write.data >> (8 * byte) & 255, known >> (8 * byte) & 255)


def preserve_bits(value, known, old_value, old_known, allow_ones=False):
    """X may persist only from old-X; it cannot replace a known old bit.

    A new concrete bit from old-X is unproved unless it is a permitted tail 1.
    This is an observational provenance check, not proof of physical X identity.
    """
    for bit in range(8):
        mask = 1 << bit
        if allow_ones and known & value & mask:
            continue
        require(bool(known & mask) == bool(old_known & mask) and
                (not known & mask or not (value ^ old_value) & mask),
                'Unproved tail/prestart/transport bit provenance')


def native_state(reference, activities, mapping, symbols):
    require(all(seq in mapping for seq in activities), 'Unmapped native request')
    require(Counter(mapping.values()) == Counter(i for i, c in enumerate(reference)
                if base.is_vector_instruction(c.instruction)), 'Every vector/CSR retirement mapped exactly once')
    state, last_write, records, kinds = {}, {}, [], Counter()
    unknown_bits = zero_be = 0
    for seq, index in sorted(mapping.items()):
        c, a = reference[index], activities.get(seq)
        if a is None:
            require(not c.vector_writes and c.instruction & 127 != 0x27, 'Missing native writer/store')
            continue
        require(a.instruction == c.instruction and a.allocations == a.completions == 1,
                'Native opcode/exact single-uop completion')
        gold = {}
        if not c.vector_writes:
            require(c.instruction & 127 == 0x27 and not a.use_vd and
                    all(w.source == 3 for w in a.writes), 'Unclassified nonarchitectural writer')
            kind = 'IDENTITY_TRANSPORT'
            first = c.instruction >> 7 & 31
            require(c.vector_lmul in ('m1', 'm2'), 'Original store group geometry')
            allowed = set(range(first, first + (2 if c.vector_lmul == 'm2' else 1)))
        else:
            require(a.use_vd and a.vd == (c.instruction >> 7 & 31) and a.vstart == 0 and
                    c.vector_sew == 32 and c.vector_vstart == 0 and
                    c.vector_tail_agnostic is False and c.vector_mask_agnostic is False,
                    'Exact native destination and TU/MU context')
            if c.pc == symbols['sf_fof']:
                require(c.instruction == base.FOF and a.eew == 2 and a.vl == 4 and
                        c.vector_vl == 1 and all(w.source == 4 for w in a.writes), 'FOF native context')
                gold = {(8, b): base.oracle.prior.WORD >> (8 * b) & 255 for b in range(4)}
                allowed, kind = {8, 9}, 'FOF_DEFINED_PREFIX'
            elif c.instruction == base.MASK:
                require(a.eew == 0 and a.vl == 64 and all(w.source == 2 for w in a.writes),
                        'Mask writer context')
                gold = {(0, b): 255 for b in range(8)}
                allowed, kind = {0}, 'MASK_ACTIVE64'
            else:
                require(c.instruction & 127 == 7 or c.pc == symbols['sf_long_div'],
                        'Unexpected architectural writer')
                producer = 1 if c.pc == symbols['sf_long_div'] else 4
                require(a.eew == 2 and a.vl == c.vector_vl and
                        all(w.source == producer for w in a.writes), 'Load/DIV producer/context')
                count = 32 if c.pc == symbols['sf_recovery_load'] else 128
                gold = {(reg, b): value >> (8 * b) & 255
                        for reg, value in c.vector_writes.items() for b in range(count)}
                allowed = set(c.vector_writes)
                kind = 'DIV' if producer == 1 else 'RECOVERY' if count == 32 else 'FULL_LOAD'
        before, actual, permitted, tail_unknown = dict(state), {}, 0, 0
        for w in sorted(a.writes, key=lambda w: (w.cycle, w.row)):
            require(w.arch_seq == seq and w.instruction == c.instruction,
                    'Native write identity')
            if kind != 'IDENTITY_TRANSPORT':
                require(w.eew == a.eew, 'Native write layout differs')
            zero_be += int(w.be == 0)
            for key, (value, known) in byte_events(w):
                require(key[0] in allowed, 'Non-destination/register-group clobber')
                require(w.cycle > last_write.get(key, -1), 'Out-of-order overlapping native writers')
                # Inspect every event, not just the last write to a byte.
                if key in gold:
                    require(known == 255 and value == gold[key],
                            'Unknown/incorrect defined destination bits')
                elif kind == 'FOF_DEFINED_PREFIX' and key[0] == 8 and 4 <= key[1] < 16:
                    permitted += 1
                else:
                    old_value, old_known = before.get(key, (0, 0))
                    preserve_bits(value, known, old_value, old_known,
                                  allow_ones=kind == 'MASK_ACTIVE64' and key[1] >= 8)
                    tail_unknown += 8 - bin(known).count('1')
                unknown_bits += 8 - bin(known).count('1')
                state[key] = actual[key] = (value, known)
                last_write[key] = w.cycle
        require(all(actual.get(key) == (value, 255) for key, value in gold.items()),
                'Missing defined destination bytes')
        kinds[kind] += 1
        records.append(dict(arch_seq=seq, pc=hex(c.pc), instruction=hex(c.instruction),
            kind=kind, defined_bytes=len(gold), accepted_bytes=len(actual),
            fof_spurious_byte_events=permitted, preserved_unknown_tail_bit_events=tail_unknown))
    require(kinds == Counter(FULL_LOAD=2, DIV=1, MASK_ACTIVE64=1, FOF_DEFINED_PREFIX=1,
                             RECOVERY=1, IDENTITY_TRANSPORT=4), 'All six writers and four stores required')
    return dict(status='PASS', primary_writers=6, stores=4,
        defined_compared_bytes=sum(r['defined_bytes'] for r in records),
        unknown_accepted_bit_events=unknown_bits, zero_be_events=zero_be,
        whole_instruction_skipped=0, whole_VRF_initial_state_qualified=False,
        initial_unknown_policy='Only preserved old-X within the same register group; mask tail may set ones',
        fof_relaxation='Only v8 bytes4..15; prefix fully known; other tails require old-bit provenance',
        records=records)


def native(directory, reference, symbols):
    lanes, vlen, activities = parse_native(directory / 'vector_trace.csv')
    starts, retires, rejected = vc._parse_architecture_mapping(directory / 'commit_trace.csv')
    require((lanes, vlen) == (4, 1024) and not rejected, 'Geometry/rejected CVX request')
    arch = vc._map_architecture_retires(starts, retires, rejected)
    mapping = vc._map_spike_commits(arch, reference)
    require(len(arch) == len(retires) == len(mapping), 'Missing/unmapped vector retirement')
    return native_state(reference, activities, mapping, symbols)


def audit(directory):
    require(base.life.digest(Path(base.__file__)) == BASE_SHA, 'Sealed v1 helper identity')
    # Private function namespace: no monkey-patching of a sealed imported module.
    implementation = FunctionType(base.audit.__code__, dict(base.audit.__globals__,
                                  native=native, __file__=__file__))
    result = implementation(directory)
    result['input_pins'][str(Path(base.__file__).resolve())] = BASE_SHA
    result['checker'] = 'audit_fof_repair_v2'
    base.life.check(result['input_pins'])
    return result
