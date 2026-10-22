"""Exact reset-reachable source-proven lookahead two-transition native capture."""
import argparse
import inspect
import json
from pathlib import Path
from types import FunctionType

import prove_lookahead_send_ready762 as proof
import capture_dispatcher_four762 as prior

life, require, native, tools = prior.life, prior.require, prior.native, prior.tools
HERE = Path(__file__).resolve().parent
AUDIT = life.OUT/'lookahead-send-ready2-source-proof-762-agent-20261007-01.json'
TCL = prior.TCL
SCHEMA = 'LOOKAHEAD_SEND_READY_EXACT2_NATIVE_762_V1'
PRIOR_CONFIG = life.OUT/'dispatcher-four-native762-agent-20261007-01/config.json'
PRIOR_CONFIG_SHA = 'bdd628a853dfd19870280e8f00fc2ea2cb3c94b73cb712152897f12293aaaac9'


def bound_proof(seal):
    a = life.read_bound(AUDIT, seal)
    life.check(a['pins'])
    require(a['status'] == 'SOURCE_BOUND_RESET_REACHABLE_SEND_READY2_PROOF_NOT_NATIVE_NOT_APPLIED' and
            a['population'] == 762 and a['targets'] == 2 and a['protected'] == 46 and
            a['scope'] == proof.SCOPE and a['proof']['send_ready_edges'] == 0 and
            a['negative_single_beat_reachable'] and a['negative_illegal_initial_state_reachable'] and
            not a['native_qualified'] and not a['application_approved'], 'Wrong static proof')
    return a


def historical_pins(book):
    previous = life.read_bound(PRIOR_CONFIG,PRIOR_CONFIG_SHA)
    require(previous['schema'] == 'DISPATCHER_EXACT4_NATIVE_762_V1' and previous['baseline'] == 762,
            'Wrong historical auxiliary provenance')
    life.check(previous['pins'])
    return life.merge_pins(life.merge_pins(book['input_pins'],book['output_pins']),previous['pins'])


def prepare(out, proof_seal):
    require(out.parent == life.OUT and not out.exists() and out.resolve() == out, 'Fresh output required')
    a = bound_proof(proof_seal)
    book = life.read_bound(prior.BASE/'admission-manifest.json', proof.BASE_SHA)
    bitpath = prior.BASE/'combined-bits.json'
    bits = life.read_bound(bitpath, book['output_pins'][str(bitpath)])
    ledger = prior.BASE/'combined-inputs.txt'
    require(life.digest(ledger) == book['output_pins'][str(ledger)], 'Exact ledger differs')
    members = ledger.read_text().splitlines()
    require(members[1:] == bits['tests'] and len(set(members)) == len(members) == 763, 'Not formal762')
    design, sample = Path(members[0]), Path(members[1])
    pins = dict(a['pins'], **{str(AUDIT):proof_seal})
    inherited = historical_pins(book)
    pins[str(PRIOR_CONFIG)] = PRIOR_CONFIG_SHA
    membership = {}
    for root in (design,sample):
        require(root.resolve() == root and root.is_dir(), 'Aliased VDB')
        files = sorted(p for p in root.rglob('*') if p.is_file())
        require(files and not any(p.is_symlink() for p in root.rglob('*')), 'Empty/aliased VDB')
        membership[str(root)] = [str(p.relative_to(root)) for p in files]
        for p in files:
            sha = life.digest(p)
            require(str(p) in inherited and inherited[str(p)] == sha, 'Unsealed historical sample/design')
            pins[str(p)] = sha
    shape = design/'snps/coverage/db/shape/fsm.verilog.shape.xml'
    gs = proof.groups(native.read_xml(shape),bits)
    require(gs == a['groups'], 'Source proof and native plan differ')
    plan = dict(groups=gs, targets=2, protected=46, strategy='direct-transition-only-66',
                point_query_authority='saved-native-identity')
    expected = native.expected_records(plan,native.Design(design))
    tests = sorted(p for p in (sample/'snps/coverage/db/testdata').iterdir() if p.is_dir())
    require(len(tests) == 1, 'Not one historical sample')
    selected = str(sample.with_suffix('')/tests[0].name)
    rawpath, rawsha = prior.runner.native.inherited.admission.RAW, prior.runner.native.inherited.admission.RAW_SHA
    raw = life.read_bound(rawpath,rawsha); pins[str(rawpath)] = rawsha
    tools.revalidate(raw['tool_identity'])
    deps = [Path(__file__).resolve(),HERE/'test_capture_lookahead_send_ready762.py',Path(prior.__file__).resolve(),
            Path(proof.__file__).resolve(),TCL,Path(prior.runner.__file__).resolve(),Path(native.__file__).resolve(),
            Path(life.__file__).resolve(),Path(tools.__file__).resolve()]
    deps += [HERE/n for n in ('fsm741_transition_native.tcl','fsm741_transition_batch.tcl',
        'fsm741_native_singleton.tcl','fsm741_native_probe.tcl','discover_ptw_pmp0_fsm_v2.tcl',
        'apply_points740_v4.tcl','inventory_operand_debug.py','closure_point_inventory.py')]
    for p in deps: pins[str(p)] = life.digest(p)
    lines = ['set fx_groups {}\n']
    for g in gs:
        fields = [g['scope'],str(proof.SOURCE),g['machine']['name'],g['mode']]
        names = ' '.join(prior.runner.atom(r['name']) for r in g['rows'])
        targets = ' '.join(prior.runner.atom(r['name']) for r in g['rows'] if r['target'])
        lines.append('lappend fx_groups [list '+' '.join(map(prior.runner.atom,fields))+
                     ' [list '+names+'] [list '+targets+']]\n')
    lines += ['set '+k+' '+prior.runner.atom(v)+'\n' for k,v in
              dict(d4_design=design,d4_sample=sample,d4_selected=selected).items()]
    life.check(pins)
    out.mkdir()
    (out/'selection.tcl').write_text(''.join(lines)); pins[str(out/'selection.tcl')] = life.digest(out/'selection.tcl')
    life.save(out/'config.json',dict(schema=SCHEMA,output=str(out),pins=pins,plan=plan,expected_records=expected,
        identity=raw['tool_identity'],input_membership=membership,sample_inputs=[str(design),str(sample)],
        selected=selected,baseline=762,sample_population=1,population_application=False,
        automatic_retry=False,other46_protected=True,states_explicitly_excluded=False,
        proof=str(AUDIT),proof_seal=proof_seal,annotation=native.ANNOTATION,timeout_seconds=900,
        tcl_reuse='Immutable dispatcher capture session; d4 names are generic design/sample variables, not identity inference.'))
    print(json.dumps(dict(status='PREPARED_NO_DVE',output=str(out),seal=life.digest(out/'config.json'))),flush=True)


def verifier():
    # Only identity/result metadata changes; substantive predecessor gates unchanged.
    source = inspect.getsource(prior.verify)
    substitutions = {
        "'DISPATCHER_EXACT4_NATIVE_762_V1'":repr(SCHEMA),
        "'EXACT_DISPATCHER4_NATIVE_ROUNDTRIP_NOT_APPLICATION_APPROVAL'":"'EXACT_LOOKAHEAD2_NATIVE_ROUNDTRIP_NOT_APPLICATION_APPROVAL'",
        'targets=4, protected=88':'targets=2, protected=46',
        'remaining13_protected=True':'other46_protected=True',
    }
    for old,new in substitutions.items():
        require(source.count(old) == 1, 'Frozen verifier identity adapter differs')
        source = source.replace(old,new)
    ns = dict(prior.verify.__globals__)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),ns)
    return ns['verify']


def verify(out,seal,prepared=False):
    c = life.read_bound(out/'config.json',seal)
    a = bound_proof(c['proof_seal'])
    require(c['proof'] == str(AUDIT) and c['plan']['groups'] == a['groups'] and
            c['plan']['targets'] == 2 and c['plan']['protected'] == 46 and c['other46_protected'] and
            c['baseline'] == 762 and not c['population_application'], 'Scope/proof gate differs')
    verifier()(out,seal,prepared)


def run(out,seal):
    ns = dict(prior.runner.run.__globals__,verify=verify,TCL=TCL)
    FunctionType(prior.runner.run.__code__,ns)(out,seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','run','verify'))
    p.add_argument('--output',type=Path,required=True); p.add_argument('--seal');p.add_argument('--proof-seal')
    a = p.parse_args(); out = a.output.absolute()
    if a.mode == 'prepare':
        require(a.proof_seal,'Explicit proof seal required');prepare(out,a.proof_seal)
    else:
        require(a.seal,'Exact config seal required')
        if a.mode == 'run': run(out,a.seal)
        else: verify(out,a.seal,a.mode=='check')
