"""Prepare/verify one fixed120s CSR run; separate parent authorization to execute."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import build_csr_frozen_counter_preflight as oracle
import run_pure_war_simulation as frozen

life, require = frozen.life, oracle.require
PRE = life.OUT / 'csr-frozen-counter-preflight-738-agent-20261006-01'
PRE_SEAL = 'ea8b192a08e8bb131a5e3d4f094626b3393f7caad47a1f35ea672b84916220ab'
ELF = PRE / 'input.elf'
ELF_SHA = '9ee9c9e3977f901facb771b413538f15405f3dca2108481ae21b3e879837c297'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
LIFECYCLE_SHA = '2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'
NAME, BUDGET = 'vcsr_frozen_counter_matrix', 120


def exact_fields(record, expected, message):
    require(all(k in record and type(record[k]) is type(v) and record[k] == v
                for k, v in expected.items()), message)


def validate_preflight(pre):
    exact_fields(pre, dict(status='CSR_COUNTER_MATRIX_PREFLIGHT_PASS_NOT_VCS', baseline_tests=738,
        input_elf=str(ELF), input_spike_trace=str(PRE / 'spike.trace'),
        target_before=str(PRE / 'target-before.json'), measured_raw_increment=None,
        rtl_changed=False, VCS_authorized=False, coverage_admitted=False), 'Preflight contract differs')
    require(pre['output_pins'].get(str(ELF)) == ELF_SHA and
            type(pre['symbols']['tohost']) is int and pre['symbols']['tohost'] == 0x80001000,
            'ELF/terminal identity differs')
    for name in ('input.elf', 'spike.trace', 'spike.stdout', 'spike-command.json', 'compile-command.json',
                 'compile.log', 'spike-validation.json', 'target-before.json', 'independent-gold.json'):
        require(str(PRE / name) in pre['output_pins'], 'Missing preflight output pin: ' + name)
    require(pre['pins'].get(str(Path(oracle.__file__).resolve())) == life.digest(Path(oracle.__file__)),
            'Frozen oracle source drift')
    return life.merge_pins(pre['pins'], pre['output_pins'])


def reference_counts(commits, entry, tohost):
    prefix = []
    for c in commits:
        if not prefix and c.pc != entry:
            continue
        prefix.append(c)
        if (tohost, 1) in c.memory_accesses:
            break
    require(prefix and prefix[-1].memory_accesses == ((tohost, 1),), 'No complete terminal prefix')
    require(all(c.instruction & 3 == 3 for c in prefix), 'Unexpected compressed opcode')
    require(not any(c.vector_writes or getattr(c, 'fpr_writes', {}) for c in prefix),
            'Unexpected vector/FP destination')
    return dict(matched_instructions=len(prefix), matched_scalar_writes=sum(len(c.gpr_writes) for c in prefix),
        matched_scalar_memory_accesses=sum(len(c.memory_accesses) for c in prefix),
        skipped_unobservable_register_values_required=0, expected_traps=0,
        source='sealed Spike terminal prefix; no DUT-derived expectation')


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(ELF), '+TESTCASE=' + NAME, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', NAME]


def lifecycle_namespace():
    path = Path(frozen.__file__).resolve()
    require(life.digest(path) == LIFECYCLE_SHA, 'Frozen lifecycle drift')
    namespace = dict(__name__='csr_counter_private_fixed120_lifecycle', __file__=str(path))
    exec(compile(path.read_bytes(), str(path), 'exec'), namespace)
    namespace.update(PRE=PRE, ELF_SEAL=ELF_SHA, IMAGE_SEAL=IMAGE_SHA, BUDGET=BUDGET,
                     preflight=SimpleNamespace(NAME=NAME), command=command)
    return namespace


def manifest(out):
    out = Path(out).absolute()
    require(out.parent == life.OUT and out.resolve() == out, 'Direct canonical output required')
    pre = life.read_bound(PRE / 'preflight-manifest.json', PRE_SEAL)
    pins = validate_preflight(pre)
    require(life.digest(Path(frozen.__file__)) == LIFECYCLE_SHA, 'Frozen lifecycle drift')
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66 and
            plan['image'].get(str(life.IMAGE)) == IMAGE_SHA, 'Exact frozen old image66 required')
    pins = life.merge_pins(pins, plan['image'])
    pins = life.merge_pins(pins, plan['design_files'])
    paths = [Path(__file__).resolve(), Path(__file__).with_name('test_run_csr_frozen_counter_simulation.py'),
             Path(frozen.__file__).resolve(), Path(life.__file__).resolve()]
    paths += list((life.ROOT / 'verification/ara_verify').rglob('*.py'))
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in paths})
    pins = life.merge_pins(pins, {str(PRE / 'preflight-manifest.json'): PRE_SEAL,
                                str(life.PLAN): life.PLAN_SEAL})
    life.check(pins)
    target = life.read_bound(PRE / 'target-before.json', pins[str(PRE / 'target-before.json')])
    target_pins = {}
    require(target == oracle.target_evidence(target_pins), 'Exact compiled738 targets changed')
    require(all(pins.get(path) == digest for path, digest in target_pins.items()), 'Unpinned target derivation')
    require({(r['metric'], r['raw_index']) for r in target['targets']} ==
            {('line', 275), ('line', 578), ('line', 585), ('line', 589), ('cond', 90), ('cond', 92),
             ('branch', 202)}, 'Exact seven fresh targets required')
    commits = oracle.shared.parse_spike_commits(PRE / 'spike.trace')
    validation = oracle.validate(commits, pre['symbols'])
    require(validation == pre['validation'] == life.read_bound(PRE / 'spike-validation.json',
                pins[str(PRE / 'spike-validation.json')]), 'Independent software oracle differs')
    require(life.read_bound(PRE / 'independent-gold.json', pins[str(PRE / 'independent-gold.json')])['observed']
            == oracle.expected(), 'Independent gold differs')
    spike_command = life.read_bound(PRE / 'spike-command.json', pins[str(PRE / 'spike-command.json')])
    require(spike_command == [str(oracle.shared.SPIKE), '--isa=' + oracle.SPIKE_ISA, '--priv=msu',
            '--pmpregions=0', '-l', '--log-commits', str(ELF)], 'Exact reference capability differs')
    entry = int.from_bytes(ELF.read_bytes()[24:32], 'little')
    require(entry == 0x80000000, 'Wrong ELF entry')
    counts = reference_counts(commits, entry, pre['symbols']['tohost'])
    exact_fields(counts, dict(matched_instructions=782, matched_scalar_writes=434,
        matched_scalar_memory_accesses=203), 'Actual terminal counts differ')
    return dict(case=NAME, output=str(out), preflight=str(PRE / 'preflight-manifest.json'),
        preflight_seal=PRE_SEAL, input_elf=str(ELF), input_spike_trace=str(PRE / 'spike.trace'),
        elf_sha256=ELF_SHA, image_sha256=IMAGE_SHA, pins=pins, command=command(out), timeout_s=BUDGET,
        old_image_files_checked=66, static_target_baseline=738, targets=target['targets'],
        scalar_reference_counts=counts, expected_checks=54, expected_observed_bytes=416,
        qualification_contract=dict(full_scalar_terminal_match=True, skipped_scalar_values=0,
            partial_or_prefix_allowed=False, traps=0, memory='all opcode/address/mask/data exact; no compressed instructions',
            CSR='all scalar CSR returns exact; CY/IR frozen before every counter observation; no dynamic value waiver',
            independent_oracle='all52 observations +54checks +guards +precise prime/freeze/restore population',
            counter_final_state='write MCYCLE/MINSTRET0 while inhibited then inhibit0; no elapsed-time preservation claim',
            vector='zero destination/bytes/incomplete/trapped; retain UNOBSERVABLE, never fabricated PASS',
            backend='exact zero CVX/uop requests/responses/errors/exceptions/outstanding',
            stdout='single SUCCESS and tohost1; reject UVM_ERROR/FATAL/nonzero summaries'),
        foreground_lifetime=True, automatic_retry=False, no_FSDB=True,
        launch_gate='prepared exact seal AND separate --parent-authorized; prepare/verify never launch',
        coverage_admitted=False, admission_performed=False, terminal_oracle_verified=False,
        rtl_changed=False, new_RTL_signoff=False, simulator_exit_is_not_functional_pass=True,
        systemd_policy=dict(RuntimeMaxSec=180, TimeoutStopSec=10, KillMode='control-group'))


def prepare(out):
    require(not Path(out).exists(), 'Fresh run only; no overwrite/retry')
    return manifest(out)


def verify_prepared(out, record):
    require(record == prepare(out), 'Prepared exact fields/pins/command drift')
    return record


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
            lifecycle_namespace()['run'](out, record)
        else:
            print('CSR_COUNTER_FIXED120_PREPARED_VERIFY_PASS_NO_VCS')


if __name__ == '__main__':
    main()
