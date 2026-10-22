"""Offline, non-admitting collector. No process queries, simulator or retries."""
import argparse
import hashlib
import inspect
import json
from pathlib import Path

import fence_t_u_padding_oracle as oracle

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'verification/out'
PLAN = OUT/'fence-t-u-padding-linked-agent-727-20261006-01/review.json'
PLAN_SHA = 'f43c5b5374b60779359772babbb88359f9640ec410d8817b3951f61754857292'
require = oracle.require


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''): h.update(chunk)
    return h.hexdigest()


def check_pins(pins):
    require(len(pins) == 151, 'Linked plan pin population differs')
    for path, digest in pins.items(): require(sha(path) == digest, 'Pin drift: '+path)


def execution_gate(receipt, plan, outputs):
    require(type(receipt.get('returncode')) is int and receipt['returncode'] == 0 and
            receipt.get('timed_out') is False, 'Nonzero/unknown/timeout terminal')
    require(receipt.get('cwd') == plan['run']['cwd'] and
            receipt.get('command') == plan['run']['argv'], 'Execution command/cwd differs')
    require(type(receipt.get('elapsed_seconds')) in (int,float) and
            0 <= receipt['elapsed_seconds'] <= 615, 'Missing/out-of-budget wall time')
    require(receipt.get('output_pins') == outputs, 'Terminal output pins differ')


def retirement_adapter():
    source=inspect.getsource(oracle.retirement)
    changes=[('index > positions[back][0]', 'index > padding_positions[back][0]'),
             ('positions=positions,back=back', 'padding_positions=positions,back=back')]
    for before,after in changes:
        require(source.count(before)==1, 'Frozen retirement scoping boundary differs')
        source=source.replace(before,after)
    namespace=dict(oracle.retirement.__globals__)
    exec(compile(source,__file__+':third-position-scope-only','exec'),namespace)
    return namespace['retirement']


def evaluate(console, trace, metadata, blob, sites):
    syms = {s['Symbol']['Name']['Name']:s['Symbol'] for s in metadata['Symbols']}
    uart = oracle.uart(console, syms['padding_u_ecall']['Value'])
    retired = retirement_adapter()(trace, metadata, blob, sites, uart['software_ceil'])
    require(retired['capture_stores_checked'] == 195 and
            len(retired['rounds']) == 3 and retired['native_CSR_ceil_parity'],
            'Incomplete retirement checks')
    return dict(status='FUNCTIONAL_AND_FOCUSED_RETIREMENT_PASS_NOT_ADMITTED',
                uart=uart, retirement=retired, cyclequalified=False,
                native_counter_observer_verified=False, exact_cycle_proof=False,
                full_ISA_reference_verified=False, relative727_gain_checked=False,
                checker_scope_adapter='Exact two substitutions: padding_positions avoids audit_rows local positions list; frozen oracle unchanged',
                application_approval=False,
                scope='Actual RVFI/ELF, capture/trap stores and CSR/UART parity; no continuous native counter route')


def collect(output, execution, execution_sha):
    require(output.parent == OUT and not output.exists() and output.resolve() == output,
            'Fresh collector output required')
    require(sha(PLAN) == PLAN_SHA, 'Linked plan seal differs')
    plan = json.loads(PLAN.read_bytes())
    check_pins(plan['pins'])
    run = Path(plan['run']['cwd'])
    paths = [run/'console.log', run/'run.vcs.log', run/'commit_trace.csv']
    outputs = {str(p):sha(p) for p in paths}
    require(sha(execution) == execution_sha, 'Parent execution receipt seal differs')
    receipt = json.loads(execution.read_bytes())
    execution_gate(receipt, plan, outputs)
    build = OUT/'fence-t-u-padding-build-parent-727-20261006-01'
    metadata = json.loads((build/'elf_metadata.json').read_bytes())[0]
    result = evaluate(paths[0].read_text(), paths[2].read_text(), metadata,
                      (build/'input.elf').read_bytes(), plan['proof']['sites'])
    # Recheck all 151 frozen pins and every read artifact before sealing results.
    check_pins(plan['pins'])
    for path,digest in outputs.items(): require(sha(path)==digest, 'Output still changing: '+path)
    require(sha(PLAN)==PLAN_SHA and sha(execution)==execution_sha, 'Plan/receipt changed')
    result.update(linked_plan_sha256=PLAN_SHA, frozen_input_pins=plan['pins'],
                  frozen_pin_count=151, frozen_pins_pre_and_post_verified=True,
                  terminal_receipt=str(execution), terminal_receipt_sha256=execution_sha,
                  terminal_verified_against_parent_receipt=True,
                  output_pins=outputs,
                  collector_pins={str(Path(__file__).resolve()):sha(Path(__file__)),
                                  str(ROOT/'verification/coverage/test_collect_fence_t_u_padding_post.py'):
                                  sha(ROOT/'verification/coverage/test_collect_fence_t_u_padding_post.py')})
    output.mkdir()
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    seal=sha(output/'result.json')
    (output/'seal.json').write_text(json.dumps(dict(result_sha256=seal))+'\n')
    print(json.dumps(dict(output=str(output),seal=seal,status=result['status'])))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execution',type=Path,required=True,
                        help='Parent terminal JSON: returncode, timed_out, elapsed_seconds, cwd, command, output_pins')
    parser.add_argument('--execution-sha256',required=True)
    args=parser.parse_args()
    collect(args.output.absolute(),args.execution.absolute(),args.execution_sha256)
