"""Original system_gap30_cache acceptance on a newly pinned image; no EDA.

The parent runner must verify image/configuration provenance and normal process
exit. This checker checks the complete original scalar workload and its terminal,
not a Spike run or a new all-instruction scalar interpreter.
"""
import argparse
import json
from pathlib import Path
import re

from ara_verify.contract import parse_contract_summary
import audit_extra_acceptance_20261008 as extra

ROOT = Path(__file__).resolve().parents[2]
ELF_SHA = extra.HASHES['cache']
require = extra.require


def source():
    return ROOT/'verification/out/system-gap30-20260929-01/results/extra-rvv-system_gap30_cache/tests/rvv_system_gap30_cache'


def check_log(text):
    lines = [line.strip() for line in text.splitlines()]
    require([line for line in lines if line.startswith('PASSED:')] ==
            ['PASSED: system_gap30 case=6 checks=1758'], 'Complete original1758 check PASS required')
    require(text.count('Core Test *** SUCCESS ***') == 1, 'One normal Core SUCCESS required')
    summaries = [line for line in lines if '[ARA_CONTRACT]' in line]
    require(len(summaries) == 1, 'One scalar-only contract summary required')
    contract = parse_contract_summary(summaries[0])
    require(contract is not None and all(value == 0 for value in contract.values()),
            'Scalar cache case must have no accelerator activity/error/outstanding')
    for line in lines:
        require(not re.search(r'\b(?:Error:|Fatal:|Error-\[|Fatal-\[)|\$fatal|\[ARA_CONTRACT_ERROR\]', line),
                'Simulator/contract error')
        require(not re.match(r'(?:FAIL(?:ED)?\b|ERROR\b|Assertion\b)', line) and
                'Core Test *** FAILED' not in line, 'Software failure')
        if re.search(r'\b(?:UVM_ERROR|UVM_FATAL)\b', line):
            require(re.fullmatch(r'(?:UVM_ERROR|UVM_FATAL)\s*:\s*0+', line) is not None,
                    'UVM error/fatal diagnostic')
    return contract


def check_rows(rows, blob):
    require(rows and extra.number(rows[0], 'pc') == 0x80000000, 'Missing original entry')
    require(all(row['event'] == 'retire' for row in rows), 'Unexpected vector/backend event in scalar case')
    require(all(int(a['cycle']) <= int(b['cycle']) for a, b in zip(rows, rows[1:])),
            'Nonmonotonic trace')
    for row in rows:
        word = extra.number(row, 'insn')
        width = 4 if word & 3 == 3 else 2
        require(int.from_bytes(extra.code_at(blob, extra.number(row, 'pc'), width), 'little') == word,
                'Retired instruction does not belong to original ELF')
    data = extra.cache_prefix(rows)
    require(data['stores'] == [4096]*3 and data['loads'] == data['check_counter_updates'] == [586]*3,
            'All3 rounds/12288 stores/1758 independent readbacks required')
    expected = [0x80000146, 0x800001a2, 0x800001a6,
                0x800001ca, 0x80000226, 0x8000022a,
                0x80000252, 0x800002a8, 0x800002ac]
    actual = [extra.number(r, 'pc') for r in rows
              if extra.number(r, 'insn') in (0x0120000f, 0x0330000f, 0x0000100f)]
    require(actual == expected, 'All9 original fences must retire in order')
    # Each round must finish stores, fence, checks, and final fences before the next round.
    checkpoints = [0x8000013c, 0x80000146, 0x80000170, 0x800001a2, 0x800001a6,
                   0x800001c0, 0x800001ca, 0x800001f4, 0x80000226, 0x8000022a,
                   0x80000248, 0x80000252, 0x8000027c, 0x800002a8, 0x800002ac, 0x800002be]
    groups = {pc: [i for i, r in enumerate(rows) if extra.number(r, 'pc') == pc] for pc in checkpoints}
    require(all(groups.values()) and all(max(groups[a]) < min(groups[b])
                                        for a, b in zip(checkpoints, checkpoints[1:])),
            'Round/fence/completion ordering')
    marker = [r for r in rows if extra.number(r, 'pc') == 0x800002be]
    require(len(marker) == 1 and extra.number(marker[0], 'mem_addr') == 0x80009688 and
            extra.number(marker[0], 'mem_wmask') == 255 and
            extra.number(marker[0], 'mem_wdata') == 0x7379733330, 'Original completion marker')
    for pc, addr, value, width, rd in ((0x800002e0, 0x80009688, 0x7379733330, 255, 11),
                                    (0x800002e2, 0x80009680, 1758, 15, 12),
                                    (0x800002e4, 0x80009684, 0, 240, 13)):
        found = [r for r in rows if extra.number(r, 'pc') == pc]
        require(len(found) == 1 and extra.number(found[0], 'mem_addr') == addr and
                extra.number(found[0], 'mem_rmask') == width and
                extra.number(found[0], 'rd_wdata') == value and int(found[0]['rd']) == rd,
                'main must read actual completion/count/failures correctly')
    terminals = [r for r in rows if extra.number(r, 'mem_addr') == 0xd0000000
                 and extra.number(r, 'mem_wmask')]
    require(len(terminals) == 1 and extra.number(terminals[0], 'pc') == 0x800000ec and
            extra.number(terminals[0], 'mem_wmask') == 255 and
            extra.number(terminals[0], 'mem_wdata') == 0, 'Original MMIO success terminal')
    require(int(marker[0]['order']) < int(terminals[0]['order']), 'Terminal before completion')
    require(not any(extra.number(r, 'pc') in (0x80000316, 0x800000fc) for r in rows),
            'Failure exit path executed')
    return dict(status='PASS', rounds=3, checks=1758, stores=12288, independent_readbacks=1758,
                independent_readback_bytes=14064, original_fences=9,
                retirements=data['retirements'], last_cycle=int(rows[-1]['cycle']),
                oracle='Exact original ELF; independent store/read formula, ordered rounds/fences, completion/count/failure readback and normal MMIO terminal',
                full_scalar_ISA_comparison_claimed=False)


def audit(directory):
    directory = Path(directory).resolve()
    require(extra.sha(source()/'input.elf') == ELF_SHA and
            extra.sha(directory/'input.elf') == ELF_SHA, 'Original ELF required; no same-name replacement')
    required = [directory/'input.elf', directory/'commit_trace.csv', directory/'run.vcs.log']
    if (directory/'console.log').exists():
        required.append(directory/'console.log')
    pins = {str(path): extra.sha(path) for path in required}
    for log in required[2:]:
        check_log(log.read_text())
    result = check_rows(list(extra.rows(directory/'commit_trace.csv')), (directory/'input.elf').read_bytes())
    require(all(extra.sha(p) == h for p, h in pins.items()), 'Evidence changed during audit')
    result.update(input_pins=pins, ELF_sha256=ELF_SHA, checker_sha256=extra.sha(__file__),
                  coverage_admitted=False, new_simulation_started=False,
                  runner_obligations='Pin image/config/checkers and require normal process exit; do not merge old-image VDBs.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), indent=2, sort_keys=True))
