"""Prepare one fixed300s PTW experiment; parent authorization required to run."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import build_ptw_sfence_boundary_preflight as oracle
import run_pure_war_simulation as frozen
import closure_point_inventory as inventory

life, require = oracle.life, oracle.require
PRE = life.OUT / 'ptw-sfence-boundary-preflight-737-agent-20261006-02'
PRE_SEAL = '0d1c7cb868f77d68fb5c5350a15c94c6171fa8e5c81891cc740c4e93441b3b9e'
ELF = PRE / 'input.elf'
ELF_SHA = 'c2dd97c913514cbc2608fe32622bac1a0162abe742f4cc134104d91dfde92587'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
LIFECYCLE_SHA = '2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'
NAME = 'vptw_sfence_boundary'
BUDGET = 300


def exact_fields(value, expected, message):
    require(all(k in value and type(value[k]) is type(v) and value[k] == v
                for k, v in expected.items()), message)


def validate(pre):
    exact_fields(pre, dict(status='SPIKE_ARCHITECTURE_PASS_NOT_PTW_WINDOW_PROOF',
        baseline_tests=737, input_elf=str(ELF),
        input_spike_trace=str(PRE.with_name('ptw-sfence-boundary-preflight-737-agent-20261006-01') / 'spike.trace'),
        runtime_window_verified=False, VCS_authorized=False, coverage_admitted=False), 'Preflight differs')
    require(pre['output_pins'].get(str(ELF)) == ELF_SHA and pre['symbols']['tohost'] == 0x80001000,
            'Exact reused ELF/terminal differs')
    pins = life.merge_pins(pre['pins'], pre['output_pins'])
    for name in ('input.elf', 'input.disasm', 'spike-validation.json', 'target-before.json',
                 'configuration-proof.json', 'control-window-contract.json', 'spike-reference.json',
                 'compile-command.json', 'compile.log'):
        require(str(PRE / name) in pre['output_pins'], 'Missing preflight output pin: ' + name)
    require(pre['input_spike_trace'] in pre['pins'], 'Missing original Spike trace pin')
    return pins


def validate_targets(evidence):
    exact_fields(evidence, dict(baseline_tests=737), 'Target baseline differs')
    rows = evidence['targets']
    require(len(rows) == 2 and [r['raw_index'] for r in rows] == [21, 25], 'Exact two targets required')
    for row, state, predicate in zip(rows, ('WAIT_GRANT', 'WAIT_RVALID'),
                                    ('flush_i && !req_port_i.data_gnt', 'flush_i && data_rvalid_q')):
        exact_fields(row, dict(scope=oracle.SCOPE, metric='fsm', width=35, checksum='3345966803',
            source_state=state, destination_state='LATENCY', predicate=predicate,
            hit_before=False, runtime_window_verified=False), 'Target coordinates/predicate differ')


def compiled_targets(tree):
    definitions = [n for n in tree.iter('fsmdef') if n.get('chksum') == '3345966803']
    require(len(definitions) == 1, 'Missing/ambiguous PTW compiled definition')
    definition = definitions[0]
    require([n.get('name') for n in definition.iter('fsminst')] == [oracle.SCOPE],
            'PTW compiled instance binding differs')
    points = []
    for machine in definition.iter('fsmfsm'):
        states = {s.get('id'): s.get('name') for s in machine.findall('state')}
        require(len(states) == len(machine.findall('state')), 'Duplicate FSM state ID')
        for node in machine:
            if node.tag == 'state':
                points.append(dict(machine=machine.get('name'), state=node.get('name')))
            elif node.tag == 'transition':
                require(node.get('fromid') in states and node.get('toid') in states, 'Unknown transition state')
                points.append(dict(machine=machine.get('name'), source=states[node.get('fromid')],
                                   destination=states[node.get('toid')]))
    require(len(points) == 35, 'PTW flattened FSM width differs')
    for raw, state in ((21, 'WAIT_GRANT'), (25, 'WAIT_RVALID')):
        require(points[raw] == dict(machine='state_q', source=state, destination='LATENCY'),
                'Raw FSM index does not identify requested transition')
    return {str(raw): points[raw] for raw in (21, 25)}


def reference_counts(commits, entry, tohost):
    prefix = []
    for commit in commits:
        if not prefix and commit.pc != entry:
            continue
        prefix.append(commit)
        if (tohost, 1) in commit.memory_accesses:
            break
    require(prefix and prefix[-1].memory_accesses == ((tohost, 1),), 'No complete reference terminal prefix')
    require(not any(c.vector_writes for c in prefix), 'Unexpected vector destination in scalar fixture')
    return dict(matched_instructions=len(prefix),
        matched_scalar_writes=sum(len(c.gpr_writes) for c in prefix),
        matched_scalar_memory_accesses=sum(len(c.memory_accesses) for c in prefix),
        expected_trap_events=2, floating_writes=0, vector_destination_instructions=0,
        reference_from='sealed Spike terminal prefix, not DUT',
        skipped_unobservable_register_values_required=0, compressed_memory_must_be_audited=True)


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(ELF), '+TESTCASE=' + NAME, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', NAME]


def lifecycle_namespace():
    path = Path(frozen.__file__).resolve()
    require(life.digest(path) == LIFECYCLE_SHA, 'Frozen lifecycle drift')
    # Reuse its reviewed run body without changing the imported module globals.
    namespace = dict(__name__='ptw_private_fixed300_lifecycle', __file__=str(path))
    exec(compile(path.read_bytes(), str(path), 'exec'), namespace)
    namespace.update(PRE=PRE, ELF_SEAL=ELF_SHA, IMAGE_SEAL=IMAGE_SHA, BUDGET=BUDGET,
                     preflight=SimpleNamespace(NAME=NAME), command=command)
    return namespace


def manifest(out):
    out = Path(out).absolute()
    require(out.parent == life.OUT and out.resolve() == out, 'Direct canonical output required')
    pre = life.read_bound(PRE / 'preflight-manifest.json', PRE_SEAL)
    pins = validate(pre)
    require(life.digest(Path(frozen.__file__)) == LIFECYCLE_SHA, 'Frozen lifecycle drift')
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66 and
            plan['image'].get(str(life.IMAGE)) == IMAGE_SHA, 'Exact old image66 required')
    pins = life.merge_pins(pins, plan['image'])
    pins = life.merge_pins(pins, {str(PRE / 'preflight-manifest.json'): PRE_SEAL,
        str(life.PLAN): life.PLAN_SEAL, str(Path(frozen.__file__).resolve()): LIFECYCLE_SHA,
        str(Path(__file__).resolve()): life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_run_ptw_sfence_boundary_simulation.py')):
            life.digest(Path(__file__).with_name('test_run_ptw_sfence_boundary_simulation.py'))})
    # Supplement parser/decode identities without rewriting the sealed software preflight.
    files = list((life.ROOT / 'verification/ara_verify').rglob('*.py'))
    files += [life.ROOT / 'verification/coverage/scoped_rv64c_memory.py',
              life.ROOT / 'verification/coverage/test_scoped_rv64c_memory.py',
              Path(inventory.__file__).resolve()]
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files})
    pins = life.merge_pins(pins, plan['design_files'])
    compile_file = life.OUT / 'repaired-aligned-build-20260930-01/compile.command.json'
    pins = life.merge_pins(pins, {str(compile_file): life.digest(compile_file)})
    life.check(pins)
    shape = life.OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml'
    require(str(shape) in pins, 'Missing reviewed compiled FSM shape pin')
    shape_binding = compiled_targets(inventory.read_xml(shape))
    target = life.read_bound(PRE / 'target-before.json', pins[str(PRE / 'target-before.json')])
    validate_targets(target)
    commits = oracle.shared.parse_spike_commits(Path(pre['input_spike_trace']))
    validation = oracle.validate(commits, pre['symbols'])
    require(validation == life.read_bound(PRE / 'spike-validation.json',
                pins[str(PRE / 'spike-validation.json')]), 'Independent software replay differs')
    entry = int.from_bytes(ELF.read_bytes()[24:32], 'little')
    require(entry == 0x80000000, 'Unexpected ELF entry')
    counts = reference_counts(commits, entry, pre['symbols']['tohost'])
    return dict(case=NAME, output=str(out), preflight=str(PRE / 'preflight-manifest.json'),
        preflight_seal=PRE_SEAL, input_elf=str(ELF), input_spike_trace=pre['input_spike_trace'],
        elf_sha256=ELF_SHA, image_sha256=IMAGE_SHA, pins=pins, command=command(out), timeout_s=BUDGET,
        old_image_files_checked=66, static_target_baseline=737, targets=target['targets'],
        compiled_target_binding=shape_binding,
        scalar_reference_counts=counts, expected_checks=35, expected_S_ecalls=2,
        expected_output_bytes=160, expected_trap_ledger_bytes=64,
        qualification_contract=dict(full_scalar_terminal_match=True, skipped_scalar_values=0,
            scalar_memory_including_RVC='all original opcodes/address/masks/data, no skip',
            traps='exact two S-ECALL PCs/cause9/tval0/MPP=S and complete handler ledger',
            CSR='full scalar CSR-return comparison and six restored CSR self-checks',
            memory='independent output160/ledger64/guards/PTE oracle and all scalar memory comparison',
            vector='exact zero destination/bytes/activity, retain UNOBSERVABLE not fabricated PASS',
            contract='exact zero CVX/backend requests/responses/exceptions/protocol errors/outstanding',
            stdout='single SUCCESS/tohost1, no UVM_ERROR/FATAL/nonzero diagnostic'),
        observation_contract=dict(method='raw native FSM coverage, commit trace, vector trace, no new probes',
            target_indices=[21, 25], checksum='3345966803', width=35,
            exact_target_transitions_observable=True, PTW_cycle_probe_enabled=False,
            particular_younger_Iwalk_attribution_proven=False, second_PTE_cache_coldness_proven=False,
            no_hit_action='preserve diagnostic, no layout/budget retry',
            admission_gate='complete architecture qualification AND positive fresh latest-formal delta'),
        foreground_lifetime=True, normal_wait_calls=1, automatic_retry=False, no_FSDB=True,
        authorization_source='USER_AUTHORIZED_SINGLE_EXPERIMENT_AFTER_SEPARATE_PARENT_REVIEW',
        launch_gate='exact prepared seal AND explicit --parent-authorized; prepare/verify never launch',
        coverage_admitted=False, admission_performed=False, terminal_oracle_verified=False,
        rtl_changed=False, new_RTL_signoff=False, simulator_exit_is_not_functional_pass=True,
        systemd_policy=dict(RuntimeMaxSec=360, TimeoutStopSec=10, KillMode='control-group'))


def prepare(out):
    require(not Path(out).exists(), 'Fresh run only; no retry/overwrite')
    return manifest(out)


def verify_prepared(out, record):
    require(record == manifest(out), 'Prepared exact fields/pins/command drift')
    return record


def invoke_run(out, record):
    require(prepare(out) == record, 'Reviewed execution drift')
    lifecycle_namespace()['run'](out, record)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify', 'run'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepared-seal')
    p.add_argument('--parent-authorized', action='store_true')
    a = p.parse_args(argv)
    require((a.mode != 'prepare') == bool(a.prepared_seal), 'Verify/run require prepared seal')
    require((a.mode == 'run') == a.parent_authorized, 'Run requires separate parent authorization')
    out = a.output.absolute()
    sidecar = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        require(not sidecar.exists(), 'Fresh prepared sidecar required')
        record = prepare(out)
        life.save(sidecar, record)
        print(json.dumps(dict(prepared=str(sidecar), seal=life.digest(sidecar), timeout_s=BUDGET,
                              pins_checked=len(record['pins']), VCS_started=False)))
    else:
        record = life.read_bound(sidecar, a.prepared_seal)
        verify_prepared(out, record)
        if a.mode == 'run':
            invoke_run(out, record)
        else:
            print('PTW_FIXED300_PREPARED_VERIFY_PASS_NO_VCS')


if __name__ == '__main__':
    main()
