"""Prepare successor offline gates; no EDA launch and no automatic admission."""
import argparse
import gzip
import json
from pathlib import Path
import shlex
import xml.etree.ElementTree as ET

import qualify_operand_mask_data_timeout_offline as q

OUT = q.OUT
RUN = OUT / 'operand-mask-data-old-image-parent-20261007-02'
PREPARED = RUN.with_name(RUN.name + '.prepared.json')
PREPARED_SHA = '0744b28320a35105a5f22a250b97692534c999a74560b5c531ab0c2f5a5572d5'
BASE = OUT / 'load-ni-tlb-offline-admitted-762-agent-20261007-01'
BASE_SHA = '6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5'


def normal_exit(state):
    q.need(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and
           type(state.get('returncode')) is int and state['returncode'] == 0 and
           not state.get('coverage_admitted') and not state.get('admission_performed'),
           'Normal successful OS exit required; timeout cannot pass this gate')
    q.need(not state.get('timeout', False), 'Timeout not admissible')


def vdb_end(vdb, command):
    folders = list((vdb / 'snps/coverage/db/testdata').glob('*'))
    q.need(len(folders) == 1 and folders[0].is_dir() and folders[0].name == 'operand_mask_full_width_data',
           'Missing/ambiguous native testdata')
    files = []
    for name in ('line.verilog.data.xml', 'cond.verilog.data.xml', 'branch.verilog.data.xml',
                 'fsm.verilog.data.xml', 'tgl.verilog.data.xml', 'siminfo.xml', 'vcmArguments.xml'):
        p = folders[0] / name
        q.need(p.is_file() and not p.is_symlink() and p.stat().st_size > 0, 'Incomplete native end member: ' + name)
        raw = p.read_bytes()
        ET.fromstring(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
        files.append(p)
    raw = (folders[0] / 'siminfo.xml').read_bytes()
    sim = ET.fromstring(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw).find('srctest')
    q.need(sim is not None and int(sim.get('finishtime', '0')) > int(sim.get('starttime', '0')) > 0
           and shlex.split(sim.get('cmdline', '')) == command and sim.get('workdir') == str(RUN),
           'Native simulation finish/command/workdir identity absent')
    return {str(p): q.sha(p) for p in files}


def architecture_gate(result):
    q.need(result.get('full_architecture_qualified') is True and
           result.get('full_scalar', {}).get('status') == 'ALL_SCALAR_RVC_PC_GPR_MEMORY_EXACT' and
           result.get('independent_oracle', {}).get('independently_compared_bytes') == 8256 and
           result['independent_oracle'].get('software_checks') == 5256 and
           result.get('full_vector', {}).get('status') == 'PASS' and
           result.get('protocol_lastdrain', {}).get('status') == 'EXACT_HANDSHAKE_LASTDRAIN_PASS_NOT_SIMULATOR_FINAL_SUMMARY',
           'Complete successor scalar/RVC/vector/independent/lastdrain qualification required')
    q.need(all(result['full_vector'].get(k) == 0 for k in
           ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions')) and
           all(result['full_vector'].get(k) == [] for k in
           ('incomplete_requests', 'unretired_requests', 'trapped_requests')),
           'Partial or unknown vector comparison cannot be admitted')


def prepare(output):
    q.need(output.parent == OUT and not output.exists(), 'Fresh independent preparation directory required')
    q.need(q.sha(PREPARED) == PREPARED_SHA, 'Parent successor prepared seal differs')
    record = json.loads(PREPARED.read_bytes())
    q.need(record['timeout_s'] == 1800 and record['command'].count('+COMMIT_TOHOST=80001000') == 1 and
           record['preflight']['software_checks'] == 5256 and
           record['preflight']['independently_compared_vector_bytes'] == 8256, 'Same ELF/budget/oracle contract differs')
    q.need(q.sha(BASE / 'admission-manifest.json') == BASE_SHA, 'Latest762 baseline seal differs')
    baseline = json.loads((BASE / 'admission-manifest.json').read_bytes())
    pins = dict(record['pins'])
    for source in (baseline['input_pins'], baseline['output_pins']):
        for path, sha in source.items():
            q.need(path not in pins or pins[path] == sha, 'Conflicting inherited pin')
            pins[path] = sha
    for path, digest in pins.items():
        q.need(q.sha(path) == digest, 'Inherited762/successor pin mismatch: ' + path)
    for p in (PREPARED, BASE / 'admission-manifest.json', Path(__file__).resolve(), Path(q.__file__).resolve(),
              Path(__file__).with_name('test_prepare_operand_mask_data_02_offline_admission.py'),
              OUT / 'operand-mask-data-timeout-offline-qualified-agent-20261007-03/qualification.json'):
        pins[str(p)] = q.sha(p)
    result = dict(schema='OPERAND_MASK_DATA_SUCCESSOR02_OFFLINE_ADMISSION_PREPARATION_V1',
        status='PREPARED_HOLD_UNTIL02_NORMAL_EXIT_FULL_ARCHITECTURE_NATIVE_END',
        baseline=762, baseline_manifest=str(BASE / 'admission-manifest.json'), baseline_sha256=BASE_SHA,
        parent_prepared=str(PREPARED), parent_prepared_sha256=PREPARED_SHA,
        same_ELF_sha256=record['preflight']['pins'][str(q.PRE / 'input.elf')],
        same_budget_s=1800, required_terminal='0x80001000=1',
        run02=str(RUN), command=record['command'], pins=pins,
        required_gates=[
            'normal_exit(): successful actual OS receipt, never timeout-to-PASS conversion',
            'architecture_gate(): full scalar/RVC + full native vector + independent8256bytes5256checks + exact lastdrain',
            'Normal final ARA_CONTRACT summary: requests=responses=62, exceptions/errors/outstanding/stalled=0; exactly one Core SUCCESS',
            'vdb_end(): one exact native test; five metric XMLs, siminfo/vcmArguments parse; finishtime>starttime and exact command/workdir',
            'Rehash every prepared run and latest762 baseline pin; verify image/source identities',
            'Compare full native shape checksum/width/scope universe before raw OR, reject lost hits and duplicate VDB/test',
            'Compute line/cond/branch/FSM union delta against exact762 using coverage_bitmap_delta; Toggle remains separately typed raw serialized delta, not a DVE percentage',
            'Write independent candidate763 receipt only after all gates; do not edit latest762/global reports'],
        rawdelta_api='verification/coverage/coverage_bitmap_delta.py: collect, combine, delta (read-only reuse after qualification)',
        original01_VDB_admissible=False, original01_timeout_status_unchanged=True,
        original01_native_vector_capture_complete=False,
        parent_service='ara-operand-mask-data-20261007-02',
        running02_outputs_read=False, simulation_launched=False, DVE_launched=False,
        admission_performed=False, population_modified=False,
        reason_not_admitted='Parent02 is independently running. This preparation neither waits/polls nor assumes its terminal qualification.')
    output.mkdir()
    q.save(output / 'prepared.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.output.absolute())
    print(json.dumps(dict(status=result['status'], seal=q.sha(args.output / 'prepared.json'),
                          inherited_pins=len(result['pins']), simulation_launched=False)))
