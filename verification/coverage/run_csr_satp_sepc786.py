"""One reviewed 180s fixed-image CSR run; prepare/check never launch."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from types import FunctionType, SimpleNamespace

import build_csr_satp_sepc785 as oracle
import run_csr_frozen_counter_simulation as template
import collect_dtlb_ppn_swap1200 as converter

life, require = template.life, oracle.require
PRE = life.OUT / 'csr-satp-sepc785-preflight-agent-20261008-04'
PRE_SEAL = '530f6b46bca0b9007642628beab66f2a663a8e8072eb7f2024e26b8406cd7ed2'
ELF = PRE / 'input.elf'
ELF_SHA = 'db6e0c5fe7835da7dfb903c5650a9afb69902acedf31706e8f977f15c323ce11'
BASE = life.OUT / 'qbs-two-phase-m4-offline-admitted786-agent-20261008-01'
BASE_SHA = '384c2b5b364f41a49968aac913b8e0904b5fe2f83c5af818af3afe535d864904'
IMAGE_SHA = template.IMAGE_SHA
NAME, BUDGET = 'csr_satp_sepc_matrix785', 180
PROBE = Path(__file__).with_name('csr_satp_sepc_probe.tcl').resolve()
SERVICE = 'ara-csr-satp-sepc786-parent-20261008-01.service'
exact_fields = template.exact_fields


def source_contract():
    book_path = oracle.inventory.BUILD / 'build-source-pins.json'
    book = json.loads(book_path.read_bytes())
    pins = {str(book_path): life.digest(book_path)}
    names = ['csr_regfile.sv', 'csr_buffer.sv', 'ex_stage.sv', 'commit_stage.sv', 'cva6.sv', 'issue_read_operands.sv',
             'include/ariane_pkg.sv', 'include/build_config_pkg.sv', 'include/cv64a6_imafdcv_sv39_config_pkg.sv']
    for name in names:
        path = life.ROOT / 'hardware/deps/cva6/core' / name
        require(life.digest(path) == book[str(path)], 'Frozen CSR producer source drift')
        pins[str(path)] = book[str(path)]
    package = (life.ROOT / 'hardware/deps/cva6/core/include/ariane_pkg.sv').read_text()
    body = re.search(r'typedef enum logic \[7:0\]\s*\{(.*?)\}\s*fu_op;', package, re.S)
    require(body is not None, 'Exact fu_op enum unavailable')
    tokens = re.sub(r'//[^\n]*|/\*.*?\*/', '', body.group(1), flags=re.S).split(',')
    tokens = [t.strip() for t in tokens if t.strip()]
    require(all(re.fullmatch(r'[A-Z][A-Z0-9_]*', t) for t in tokens), 'Nonimplicit fu_op enum')
    ops = {name: tokens.index(name) for name in ('CSR_WRITE', 'CSR_READ', 'CSR_SET', 'CSR_CLEAR')}
    config = oracle.inventory.CONFIG.read_text()
    require('CVA6ConfigNrScoreboardEntries = 8;' in config and 'CVA6ConfigNrCommitPorts = 2;' in config,
            'Native TID/commit port configuration')
    buffer = (life.ROOT / 'hardware/deps/cva6/core/csr_buffer.sv').read_text()
    require('csr_reg_n.csr_address = fu_data_i.operand_b[11:0];' in buffer and
            'assign csr_result_o = fu_data_i.operand_a;' in buffer and
            'if (csr_commit_i && ~csr_valid_i)' in buffer and
            "if ((csr_reg_q.valid || csr_valid_i) && ~csr_commit_i) csr_ready_o = 1'b0;" in buffer and
            "if (csr_valid_i) begin" in buffer, 'CSR buffer owner/address/data/ready path')
    producer = (life.ROOT / 'hardware/deps/cva6/core/issue_read_operands.sv').read_text()
    require('assign csr_valid_o = csr_valid_q;' in producer and 'csr_valid_q    <= csr_valid_n;' in producer
            and 'if (!issue_instr_i[i].ex.valid && issue_instr_valid_i[i] && issue_ack_o[i]) begin' in producer
            and "CSR: begin\n            csr_valid_n[i] = 1'b1;" in producer,
            'CSR valid must be registered acknowledged one-cycle issue, not request/ready handshake')
    return dict(ops=ops, tid_width=3, commit_ports=2,
                same_edge_order='consume old commit before accepting next issue',
                issue_semantics='csr_valid_i is already-issued registered pulse; ready is future-capacity feedback',
                ready_formula='!((csr_reg_q.valid || csr_valid_i) && !csr_commit_i)',
                retire_trace_tid_is_unavailable=True), pins


def reference(pre):
    commits = list(oracle.shared.parse_spike_commits(PRE / 'spike.trace'))
    start = next(i for i, c in enumerate(commits) if c.pc == 0x80000000)
    end = next(i for i, c in enumerate(commits) if (pre['symbols']['tohost'], 1) in c.memory_accesses)
    return commits[start:end + 1]


def command(out):
    return FunctionType(template.command.__code__, dict(template.command.__globals__,
        ELF=ELF, NAME=NAME))(out) + ['-ucli', '-do', str(PROBE)]


def manifest(out, service=SERVICE):
    out = Path(out).absolute()
    require(out.parent == life.OUT and out.resolve() == out, 'Direct canonical output')
    require(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service', service) is not None, 'Exact owning user service')
    pre = life.read_bound(PRE / 'preflight-manifest.json', PRE_SEAL)
    exact_fields(pre, dict(status='CSR_SATP_SEPC785_PREFLIGHT_PASS_NOT_DUT', baseline=785,
        baseline_seal=oracle.BASE_SHA, input_elf=str(ELF), VCS_authorized=False,
        coverage_admitted=False, RTL_changed=False), 'Frozen software preflight')
    require(pre['output_pins'][str(ELF)] == ELF_SHA, 'Sealed ELF')
    ref = reference(pre)
    require(oracle.validate(ref, pre['symbols']) == pre['validation'], 'Independent full software replay')
    counts = template.reference_counts(ref, 0x80000000, pre['symbols']['tohost'])
    exact_fields(counts, dict(matched_instructions=673, matched_scalar_writes=388,
        matched_scalar_memory_accesses=168), 'Exact reference prefix')
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    require(base['baseline'] == str(oracle.BASE) and base['baseline_seal'] == oracle.BASE_SHA,
            'Exact785-to786 genealogy for static target rebase')
    status = life.read_bound(BASE / 'status.json', base['output_pins'][str(BASE / 'status.json')])
    require(type(status['aggregate_passed']) is int and status['aggregate_passed'] == 786
            and status['coverage_admitted'] is True, 'Formal786 baseline')
    inputs = BASE / 'combined-inputs.txt'
    ledger = life.read_bound(inputs, base['output_pins'][str(inputs)]) if inputs.suffix == '.json' else inputs.read_text().splitlines()
    require(life.digest(inputs) == base['output_pins'][str(inputs)] and len(ledger) == len(set(ledger)) == 787,
            'Exact786 member ledger')
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(len(image['image']) == 66 and image['image'][str(life.IMAGE)] == IMAGE_SHA, 'Frozen image66')
    proof, source_pins = source_contract()
    pins = life.merge_pins(pre['pins'], pre['output_pins'])
    for extra in (image['image'], image['design_files'], source_pins,
                  {str(PRE / 'preflight-manifest.json'): PRE_SEAL, str(life.PLAN): life.PLAN_SEAL,
                   str(BASE / 'admission-manifest.json'): BASE_SHA, str(inputs): base['output_pins'][str(inputs)]}):
        pins = life.merge_pins(pins, extra)
    for name in ('status.json', 'combined-bits.json'):
        pins = life.merge_pins(pins, {str(BASE / name): base['output_pins'][str(BASE / name)]})
    files = [Path(__file__).resolve(), Path(__file__).with_name('test_run_csr_satp_sepc786.py'), PROBE,
             Path(__file__).with_name('collect_csr_satp_sepc786.py'),
             Path(__file__).with_name('test_collect_csr_satp_sepc786.py'),
             Path(template.__file__).resolve(), Path(template.frozen.__file__).resolve(), Path(life.__file__).resolve(),
             converter.CONVERTER]
    files += list((life.ROOT / 'verification/ara_verify').rglob('*.py'))
    require(life.digest(converter.CONVERTER) == converter.CONVERTER_SHA, 'Frozen VPD converter')
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files}); life.check(pins)
    return dict(case=NAME, output=str(out), pins=pins, command=command(out), timeout_s=BUDGET,
        input_elf=str(ELF), input_spike_trace=str(PRE / 'spike.trace'), elf_sha256=ELF_SHA,
        image_sha256=IMAGE_SHA, preflight_seal=PRE_SEAL, static_target_baseline=785,
        raw_baseline=str(BASE), raw_baseline_seal=BASE_SHA, raw_baseline_population=786,
        source_contract=proof, scalar_reference_counts=counts, expected_checks=44, expected_observed_bytes=336,
        old_image_files_checked=66, automatic_retry=False, no_FSDB=True, focused_readonly_VPD=True,
        systemd_policy=dict(RuntimeMaxSec=240, TimeoutStopSec=10, KillMode='control-group'),
        coverage_admitted=False, RTL_changed=False, terminal_oracle_verified=False,
        service=service, authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED_BEFORE_RUN')


def verify_prepared(out, record, terminal=False):
    require(terminal or not Path(out).exists(), 'Prepare/run requires fresh output')
    require(record == manifest(out, record['service']), 'Full prepared command/pins/source drift')
    return record


def lifecycle_namespace(out, record):
    ns = template.lifecycle_namespace()
    ns.update(PRE=PRE, ELF_SEAL=ELF_SHA, IMAGE_SEAL=IMAGE_SHA, BUDGET=BUDGET,
              preflight=SimpleNamespace(NAME=NAME), command=command)
    # Preserve every subprocess constant; replace only creation to record actual executable identity.
    def popen(*args, **kwargs):
        process = subprocess.Popen(*args, **kwargs)
        try:
            proc = Path('/proc/%d' % process.pid)
            argv = (proc / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
            require([x.decode() for x in argv] == record['command'] and
                    (proc / 'exe').resolve() == life.IMAGE.resolve() and
                    (proc / 'cwd').resolve() == out and os.getpgid(process.pid) == process.pid,
                    'Actual simv/cwd/command/process-group identity')
            cgroup = (proc / 'cgroup').read_text()
            require(cgroup == Path('/proc/self/cgroup').read_text() and
                    any(line.rsplit('/', 1)[-1] == record['service'] for line in cgroup.splitlines()),
                    'Simulator must remain in exact foreground owning service')
            life.save(out / 'live-identity.json', dict(pid=process.pid, executable=str(life.IMAGE.resolve()),
                cwd=str(out), command=record['command'], process_group=process.pid, cgroup=cgroup,
                service=record['service'], verified=True))
        except BaseException:
            import signal
            os.killpg(process.pid, signal.SIGKILL); process.wait(); raise
        return process
    ns['subprocess'] = SimpleNamespace(**dict(vars(subprocess), Popen=popen))
    return ns


def run(out, record):
    lifecycle_namespace(out, record)['run'](out, record)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify', 'run')); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepared-seal'); p.add_argument('--parent-authorized', action='store_true')
    p.add_argument('--service', default=SERVICE); a = p.parse_args()
    require((a.mode != 'prepare') == bool(a.prepared_seal), 'Prepared seal required')
    require((a.mode == 'run') == a.parent_authorized, 'Separate parent authorization required')
    out = a.output.absolute(); path = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        require(not out.exists() and not path.exists(), 'Fresh output/sidecar')
        record = manifest(out, a.service); life.save(path, record)
        print(json.dumps(dict(prepared=str(path), seal=life.digest(path), VCS_started=False)))
    else:
        record = life.read_bound(path, a.prepared_seal); verify_prepared(out, record)
        if a.mode == 'run': run(out, record)
        else: print('CSR_SATP_SEPC786_PREPARED_VERIFY_PASS_NO_VCS')


if __name__ == '__main__': main()
