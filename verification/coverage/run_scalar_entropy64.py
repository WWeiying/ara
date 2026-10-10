"""Frozen entropy64 runtime: prepare first; explicit reviewed run only."""
import argparse
import json
from pathlib import Path
from types import ModuleType

import run_gap95_simulation as life
import preflight_scalar_entropy64 as oracle
import collect_gap103_strict as architecture
import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence_v2 as toggle
import inspect_cva6_mda767 as mda
import rv64_compressed_memory as compressed

ROOT, OUT, need = life.ROOT, life.OUT, oracle.need
PRE = OUT / 'scalar-entropy64-preflight-agent-20261008-01'
PRE_SHA = '44d7b0d95052bff5db0b7f35d3bd0047948640db1802d40d9cd9c43fc22bd69c'
BASE = OUT / 'qbs-two-phase-m4-offline-admitted786-agent-20261008-01'
BASE_SHA = '384c2b5b364f41a49968aac913b8e0904b5fe2f83c5af818af3afe535d864904'
PREFIX = 'ara_tb.dut.i_ara_soc.i_system.i_ariane'
SCOPES = [PREFIX + '.issue_stage_i.i_issue_read_operands.gen_asic_regfile.i_ariane_regfile',
          PREFIX + '.ex_stage_i.lsu_i.i_store_unit.store_buffer_i']
CHECKSUMS = dict(zip(SCOPES, ('3675723707', '2778502720')))


def reference_interval(commits, symbols):
    entries = [i for i,c in enumerate(commits) if c.pc == 0x80000000]
    stops = [i for i,c in enumerate(commits) if (symbols['tohost'],1) in c.memory_accesses]
    need(len(entries) == len(stops) == 1 and entries[0] < stops[0], 'Unique entry/success terminal required')
    begin,end = entries[0],stops[0]
    need(begin == 5 and [c.pc for c in commits[:begin]] == [0x1000,0x1004,0x1008,0x100c,0x1010],
         'Frozen Spike ROM boot prefix differs')
    need(all(c.pc == commits[end].pc+4 and c.instruction == 0xa001 and not c.memory_accesses and
             not c.gpr_writes and not c.fpr_writes and not c.vector_writes for c in commits[end+1:]),
         'Foreign post-tohost reference activity')
    return commits[begin:end+1]


def check(pins):
    for name, sha in pins.items():
        need(toggle.digest(Path(name)) == sha, 'Frozen input drift: ' + name)


def helper_pins():
    # Walk only the explicitly imported module graph, not ambient sys.modules.
    todo, seen, pins = [life, oracle, architecture, bitmap, toggle, mda, compressed], set(), {}
    while todo:
        module = todo.pop()
        if id(module) in seen:
            continue
        seen.add(id(module))
        filename = getattr(module, '__file__', None)
        if not filename or not str(Path(filename).resolve()).startswith(str(ROOT / 'verification') + '/'):
            continue
        path = Path(filename).resolve()
        pins[str(path)] = toggle.digest(path)
        todo.extend(v for v in vars(module).values() if isinstance(v, ModuleType))
    for path in sorted((ROOT / 'verification/ara_verify').glob('*.py')):
        pins[str(path)] = toggle.digest(path)
    for name in ('run_scalar_entropy64.py', 'collect_scalar_entropy64.py',
                 'test_scalar_entropy64_runtime.py'):
        path = ROOT / 'verification/coverage' / name
        pins[str(path)] = toggle.digest(path)
    return pins


def make_command(out, pre):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD=' + str(PRE / 'input.elf'), '+TESTCASE=scalar_entropy64',
            '+COMMIT_TOHOST=%x' % pre['symbols']['tohost'],
            '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
            '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
            '+ARA_UVM_TRACE_LIMIT=100000', '+ARA_CONTRACT_TRACE_LIMIT=100000',
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'),
            '-cm_name', 'scalar_entropy64']


def compiled(pins, design):
    db = Path(design) / 'snps/coverage/db'
    paths = [db / name for name in ('design/verilog.design.xml',
             'shape/tgl.verilog.info.xml', 'shape/tgl.verilog.shape.xml')]
    for path in paths:
        need(str(path) in pins, 'Unbound compiled input: ' + str(path))
        check({str(path): pins[str(path)]})
    d, info, shape = [toggle.xml(p) for p in paths]
    nodes = {n.get('id'): (n, module) for module in d.findall('srcdef') for n in module.findall('srcinst')}
    def full(key, seen=()):
        need(key not in seen, 'Compiled hierarchy cycle')
        n, _ = nodes[key]
        parent = n.get('pid')
        return (full(parent, seen + (key,)) + '.' if parent in nodes else '') + n.get('name')
    result = {}
    for scope in SCOPES:
        instances = [module for key, (_, module) in nodes.items() if full(key) == scope]
        data = [n for n in info.iter('instance_data') if n.get('name') == scope]
        need(len(instances) == len(data) == 1 and data[0].get('chksum') == CHECKSUMS[scope],
             'Compiled instance/checksum differs')
        matches = [n for n in shape.findall('tgldef') if n.get('chksum') == CHECKSUMS[scope]
                   and n.get('name', '').split(' (')[0] == instances[0].get('name')]
        need(len(matches) == 1, 'Ambiguous compiled typed definition')
        result[scope] = dict(module=dict(instances[0].attrib), checksum=CHECKSUMS[scope],
                            shape=toggle.ET.tostring(matches[0], encoding='unicode'))
    return result


def prepare(out):
    out = out.absolute()
    need(out.parent == OUT and out == out.resolve() and not out.exists(), 'Fresh direct output only')
    pre = life.read_bound(PRE / 'preflight.json', PRE_SHA)
    need(pre['status'] == 'INTEGER64_MEMORY_SPIKE_PREFLIGHT_PASS_NOT_RTL' and
         pre['counts']['checks'] == 390 and pre['counts']['instructions'] == 5000,
         'Wrong sealed preflight')
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    need(base['coverage_admitted'] is True, 'Baseline not admitted')
    pins = {str(PRE / 'preflight.json'): PRE_SHA, str(BASE / 'admission-manifest.json'): BASE_SHA}
    for book in (pre['input_pins'], pre['output_pins'], base['input_pins'], base['output_pins']):
        pins = life.merge_pins(pins, book)
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    need(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66, 'Not frozen66 image')
    pins = life.merge_pins(pins, plan['image'])
    pins[str(life.PLAN)] = life.PLAN_SEAL
    pins = life.merge_pins(pins, helper_pins())
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    before = json.loads((BASE / 'combined-bits.json').read_bytes())
    need(len(ledger) == len(set(ledger)) == 787 and ledger[1:] == before['tests'], 'Exact786 ledger required')
    need(sum(len(v) for v in before['metrics'].values()) == 6162, 'Full6162 metric universe required')
    definitions = compiled(pins, ledger[0])
    commits = oracle.build.parse_spike_commits(PRE/'spike.trace')
    interval = reference_interval(commits,pre['symbols'])
    need(oracle.validate(interval,pre['symbols'])['checks'] == 390, 'Reference prefix oracle differs')
    counts = architecture.reference_counts(interval,pre['symbols'])
    need(counts == dict(matched_instructions=3326,matched_scalar_writes=1646,
                       matched_floating_writes=0,matched_scalar_memory_accesses=903), 'Frozen prefix counts differ')
    check(pins)
    return out, dict(schema='SCALAR_ENTROPY64_PREPARED_V1', case='scalar_entropy64',
        preflight=pre, pins=pins, baseline=str(BASE), baseline_seal=BASE_SHA,
        input_ledger=ledger, compiled_definitions=definitions, command=make_command(out, pre),
        reference_interval_counts=counts, parsed_reference_log_instructions=len(commits),
        timeout_s=600, coverage_admitted=False, admission_performed=False, rtl_changed=False,
        MDA_direction_gain_qualified=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--mode', choices=('prepare', 'run-reviewed'), default='prepare')
    p.add_argument('--seal')
    a = p.parse_args()
    record = Path(str(a.output.absolute()) + '.prepared.json')
    if a.mode == 'prepare':
        need(not record.exists(), 'Prepared record already exists')
        out, manifest = prepare(a.output)
        life.save(record, manifest)
        print(json.dumps(dict(prepared=str(record), seal=toggle.digest(record), pins=len(manifest['pins']))), flush=True)
    else:
        need(a.seal is not None, 'Reviewed seal required')
        old = life.read_bound(record, a.seal)
        out, manifest = prepare(a.output)
        need(old == manifest, 'Reviewed runtime contract differs')
        life.run(out, manifest)


if __name__ == '__main__':
    main()
