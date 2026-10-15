"""Synthetic CSV mutation only: unexpected helper interiors, no execution."""
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
from ara_verify.trace import validate_trace

plan = r.read(ROOT / 'prepared01/plan.json')
spec = plan['spec']
ledger = r.read(Path(plan['image']) / 'image.json')
proof = r.read(r.checker.REF / 'sourceproof.json')
findings = []
for name, pc, opcode in [
    (op + '_interior_target', *proof['helper_windows']['soc'][op]['new'][11][:2])
    for op in ('op_1', 'op_2')
] + [('op_1_entry_control', *proof['helper_windows']['soc']['op_1']['new'][0][:2])]:
    with tempfile.TemporaryDirectory(dir=OUT) as temp:
        path = Path(temp) / 'mutated.csv'
        def rows():
            retired = cycle = 0
            for row in host.fixture(spec):
                if row['event'] == 'retire' and int(row['pc'], 16) == spec['exit_store']['pc']:
                    # Add a matched vector request/response/retirement after the
                    # full original oracle, before CTRL exit. All original rows
                    # stay unchanged except order/cycle renumbering.
                    for event in ('cvx_req', 'cvx_resp', 'retire'):
                        new = {k: '0' for k in row}
                        new.update(cycle=str(cycle), event=event, order=str(retired),
                                   pc=f'{pc:x}', insn=opcode, port='0', trans_id='0')
                        yield new
                        cycle += 1
                        retired += event == 'retire'
                yield dict(row, cycle=str(cycle), order=str(retired))
                cycle += 1
                retired += row['event'] == 'retire'
        stream = rows()
        first = next(stream)
        with path.open('w', newline='') as target:
            writer = csv.DictWriter(target, fieldnames=list(first))
            writer.writeheader()
            writer.writerow(first)
            writer.writerows(stream)
        generic = validate_trace(path)
        try:
            with path.open() as source:
                strict = r.checker.retirement(csv.DictReader(source), spec)
        except ValueError as error:
            findings.append(dict(mutation=name, pc=hex(pc), opcode=opcode, generic='PASS',
                                 strict='REJECTED', reason=str(error)))
        else:
            assert (strict['csv_rows'], strict['csv_last_cycle'], strict['retired_rows']) == (
                generic['rows'], generic['last_cycle'], generic['retire_count'])
            # Full artifact-gate fixture: copy the exact existing ELF, but do
            # not execute it. Console and provenance below are synthetic test
            # protocol fields, not claims of a simulator result.
            artifact = Path(temp)
            (artifact / 'work').mkdir()
            (artifact / 'input.elf').write_bytes(Path(plan['case']['elf']).read_bytes())
            path.rename(artifact / 'commit_trace.csv')
            r.common.save(artifact / 'trace_summary.json', dict(status='VALID', **generic))
            r.common.save(artifact / 'inputs.json', dict(binary=dict(source=plan['case']['elf'],
                path=str(artifact / 'input.elf'), sha256=plan['case']['sha256']),
                simv=dict(path=ledger['simv'], image_sha256=ledger['files'])))
            r.common.save(artifact / 'command.json', dict(cwd=str(artifact / 'work'), command=[
                ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
                '+PRELOAD=' + str(artifact / 'input.elf'), '+TESTCASE=' + r.NAME,
                '+NO_FSDB', '+COMMIT_TRACE=' + str(artifact / 'commit_trace.csv')]))
            console = '\n'.join(['BOARD_CASE_BEGIN ' + r.NAME, r.checker.MARKER,
                'BOARD_CASE_PASS ' + r.NAME, 'BOARD_REPLAY_PASS', r.common.SUCCESS, '$finish']) + '\n'
            (artifact / 'console.log').write_text(console)
            (artifact / 'work/run.vcs.log').write_text(console)
            result = SimpleNamespace(name=r.NAME, status='PASS', returncode=0, reason='', elapsed_s=1,
                                     artifact_dir=artifact)
            r.checker.artifacts(result, plan['case'], ledger, spec, validate_trace)
            findings.append(dict(mutation=name, pc=hex(pc), opcode=opcode, generic='PASS',
                                 full_artifact_gate='PASS_SYNTHETIC_PROTOCOL_FIXTURE',
                                 strict='PASS', claimed_target_calls=strict['target_calls'],
                                 claimed_helper_instructions=len(strict['helper']),
                                 actual_additional_vector_retirement=1))
(OUT / 'extra_helper_evidence.json').write_text(json.dumps(findings, indent=2) + '\n')
print(json.dumps(findings))
