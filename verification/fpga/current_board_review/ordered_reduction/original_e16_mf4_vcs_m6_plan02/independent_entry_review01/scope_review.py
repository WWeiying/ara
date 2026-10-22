"""Independent successor scope negatives; protocol fixtures only, no DUT."""
import csv
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(ROOT))
import replay as r
import test_host as host
sys.path.insert(0, '/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/verification')
from ara_verify.trace import validate_trace, is_vector_instruction

plan = r.read(ROOT / 'prepared01/plan.json')
spec = plan['spec']
proof = r.read(r.checker.REF / 'sourceproof.json')
ledger = r.read(Path(plan['image']) / 'image.json')
evidence = dict(all_unused_pcs=[], original_interior_counterexamples=[], phase_negatives=[])

def empty_row(pc, encoding, event='retire'):
    return dict(cycle='0', event=event, order='0', port='0', trans_id='0', pc=f'{pc:x}',
                insn=encoding, rd='0', rd_wdata='0', mem_addr='0', mem_rmask='0',
                mem_wmask='0', mem_wdata='0', trap='0')

# Independent proof-window coverage, including both last compressed returns.
for name in ('op_1', 'op_2'):
    window = proof['helper_windows']['soc'][name]['new']
    low, high = spec['unused_ranges'][0 if name == 'op_1' else 1]
    assert low == window[0][0] and high == window[-1][0] + len(window[-1][1]) // 2
    for pc, encoding, text in window:
        try: r.checker.retirement([empty_row(pc, encoding)], spec)
        except ValueError as error:
            assert str(error) == 'Unused helper PC range'
            evidence['all_unused_pcs'].append(dict(helper=name, pc=hex(pc), rejected=str(error)))
        else: raise AssertionError((name, hex(pc)))

for name in ('op_1', 'op_2'):
    pc, encoding, text = proof['helper_windows']['soc'][name]['new'][11]
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        root = Path(tmp)
        path = root / 'commit_trace.csv'
        def rows():
            order = cycle = 0
            for row in host.fixture(spec):
                if row['event'] == 'retire' and int(row['pc'], 16) == spec['exit_store']['pc']:
                    for event in ('cvx_req', 'cvx_resp', 'retire'):
                        yield dict(empty_row(pc, encoding, event), order=str(order), cycle=str(cycle))
                        cycle += 1
                        order += event == 'retire'
                yield dict(row, order=str(order), cycle=str(cycle))
                cycle += 1
                order += row['event'] == 'retire'
        stream = rows()
        first = next(stream)
        with path.open('w', newline='') as target:
            writer = csv.DictWriter(target, fieldnames=list(first))
            writer.writeheader(); writer.writerow(first); writer.writerows(stream)
        generic = validate_trace(path)
        with path.open() as source:
            try: r.checker.retirement(csv.DictReader(source), spec)
            except ValueError as error: assert str(error) == 'Unused helper PC range'
            else: raise AssertionError('strict accepted old counterexample')
        (root / 'work').mkdir()
        (root / 'input.elf').write_bytes(Path(plan['case']['elf']).read_bytes())
        r.common.save(root / 'trace_summary.json', dict(status='VALID', **generic))
        r.common.save(root / 'inputs.json', dict(binary=dict(source=plan['case']['elf'],
            path=str(root / 'input.elf'), sha256=plan['case']['sha256']),
            simv=dict(path=ledger['simv'], image_sha256=ledger['files'])))
        r.common.save(root / 'command.json', dict(cwd=str(root / 'work'), command=[ledger['simv'],
            '-l', 'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD=' + str(root / 'input.elf'),
            '+TESTCASE=' + r.NAME, '+NO_FSDB', '+COMMIT_TRACE=' + str(path)]))
        console = '\n'.join(['BOARD_CASE_BEGIN ' + r.NAME, r.checker.MARKER,
            'BOARD_CASE_PASS ' + r.NAME, 'BOARD_REPLAY_PASS', r.common.SUCCESS, '$finish']) + '\n'
        (root / 'console.log').write_text(console)
        (root / 'work/run.vcs.log').write_text(console)
        result = SimpleNamespace(name=r.NAME, status='PASS', returncode=0, reason='', elapsed_s=1, artifact_dir=root)
        try: r.checker.artifacts(result, plan['case'], ledger, spec, validate_trace)
        except ValueError as error:
            assert str(error) == 'Unused helper PC range'
            evidence['original_interior_counterexamples'].append(dict(helper=name, pc=hex(pc), opcode=encoding,
                generic='PASS', strict='REJECTED', full_artifact='REJECTED', reason=str(error)))
        else: raise AssertionError('full artifact accepted old counterexample')

for fault, expected in [('missing_prelude_CSR', 'CSR outside original source phase'),
                        ('wrong_vlenb', 'Original C vlenb'),
                        ('missing_capacity_return', 'Capacity must retire all3 consecutively')]:
    def rows():
        order = 0
        for row in host.fixture(spec):
            pc = int(row['pc'], 16)
            if row['event'] == 'retire':
                if fault == 'missing_prelude_CSR' and pc == spec['csr_prelude'][2]['pc']: continue
                if fault == 'missing_capacity_return' and pc == spec['capacity_routine'][2]['pc']: continue
                if fault == 'wrong_vlenb' and pc == spec['csr_prelude'][-1]['pc']: row = dict(row, rd_wdata='40')
            yield dict(row, order=str(order))
            order += row['event'] == 'retire'
    try: r.checker.retirement(rows(), spec)
    except ValueError as error:
        assert str(error) == expected
        evidence['phase_negatives'].append(dict(fault=fault, rejected=str(error)))
    else: raise AssertionError(fault)

# All vector instructions in this pinned ELF are accounted for: no classifier
# omission at another PC can sidestep the selected-capacity/op0 count policy.
actual_rvv = {item['pc'] for item in spec['instructions'].values()
              if is_vector_instruction(int(item['insn'], 16)) and int(item['insn'], 16) & 127 != 0x73}
checker_rvv = {item['pc'] for item in spec['instructions'].values() if r.checker.is_rvv(int(item['insn'], 16))}
assert actual_rvv == checker_rvv
allowed = {item['pc'] for item in spec['capacity_routine'] + spec['routine'] if r.checker.is_rvv(int(item['insn'], 16))}
forbidden = {pc for name in ('op_1', 'op_2') for pc, encoding, _ in proof['helper_windows']['soc'][name]['new']
             if r.checker.is_rvv(int(encoding, 16))}
assert len(allowed) == 11 and len(forbidden) == 20 and actual_rvv == allowed | forbidden
evidence.update(status='PASS_HOST_SCOPE_REVIEW_NOT_DUT', allowed_rvv=11, prohibited_rvv=20,
                all_elf_rvv_accounted=True, synthetic_protocol_only=True, DUT_started=False)
(OUT / 'scope_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in evidence.items()}))
