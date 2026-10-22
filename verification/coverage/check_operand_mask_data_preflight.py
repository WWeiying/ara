"""Independent integer oracle for the full-width mask/gather stimulus."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ara_verify.spike_trace import parse_spike_commits

PATTERNS = (0x55, 0xaa, 0xff, 0)
OPS = (0x00880c57, 0x6a8800d7, 0x32880c57)


def expected(phase):
    assert phase in range(4)
    add = bytes((((i ^ (255 if phase & 1 else 0)) + (3*i+17)) & 255)
                if PATTERNS[phase] >> (i % 8) & 1 else (i ^ 0xa5) & 255
                for i in range(1024))
    source = [0x0123456789abcdef ^ (0x0101010101010101*i) for i in range(128)]
    if phase & 1:
        source = [x ^ ((1 << 64)-1) for x in source]
    indices = list(reversed(range(128))) if phase < 2 else [(1 << 64)-1]*128
    gather = b''.join((source[i] if i < 128 else 0).to_bytes(8, 'little') for i in indices)
    mask = sum(int(a < b) << i for i, (a, b) in enumerate(zip(source, indices)))
    return add, mask, gather


def validate(commits):
    registers, phase, position, compared = {}, 0, 0, 0
    for commit in commits:
        registers.update(commit.vector_writes)
        if commit.instruction not in OPS:
            continue
        assert phase < 4 and commit.instruction == OPS[position], 'Missing/extra/reordered target'
        add, mask, gather = expected(phase)
        if position == 1:
            assert 1 in registers and registers[1] & ((1 << 128)-1) == mask, 'Compare mask differs'
            compared += 16
        else:
            assert all(r in registers for r in range(24, 32)), 'Missing destination group'
            actual = b''.join(registers[r].to_bytes(128, 'little') for r in range(24, 32))
            assert actual == (add if position == 0 else gather), 'Full destination group differs'
            compared += 1024
        position += 1
        if position == 3:
            position, phase = 0, phase+1
    assert (phase, position, compared) == (4, 0, 8256), 'Incomplete four-phase oracle'
    return compared


def main(directory):
    trace = directory/'spike.trace'
    assert 'exception ' not in trace.read_text(), 'Unexpected Spike exception'
    commits = parse_spike_commits(trace)
    compared = validate(commits)
    from elftools.elf.elffile import ELFFile
    with (directory/'input.elf').open('rb') as stream:
        symbols = {s.name: s.entry.st_value for s in ELFFile(stream).get_section_by_name('.symtab').iter_symbols()}
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    assert writes[symbols['tohost']] == 1, 'Software failure'
    assert writes[symbols['g75_result']] == 5256 and writes[symbols['g75_result']+4] == 0
    assert writes[symbols['num_failed']] == 0
    paths = [directory/'input.elf', trace, Path(__file__).resolve(),
             Path(__file__).resolve().parents[2]/'apps/riscv-tests/isa/rv64uv/vgap_operand_mask_data.c']
    result = dict(status='SPIKE_INDEPENDENT_INTEGER_ORACLE_PASS_NOT_RTL', phases=4,
                  instructions=len(commits), target_instructions=12,
                  independently_compared_vector_bytes=compared, software_checks=5256,
                  symbols=symbols, coverage_admitted=False, VCS_launched=False,
                  pins={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (directory/'preflight.json').open('x') as stream:
        json.dump(result, stream, indent=2)
    print({k:v for k,v in result.items() if k not in ('pins','symbols')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    main(parser.parse_args().directory.resolve())
