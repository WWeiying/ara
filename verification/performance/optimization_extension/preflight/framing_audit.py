#!/usr/bin/env python3
"""Narrow, separately sealed audit of one completed UART/probe-interleaved run."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
HERE = Path(__file__).resolve().parent
BENCH = OUT/'optimization_extension_preflight_20261111_02'
IMAGE = OUT/'enablement_soc_build_20261111_02'
ORIGINAL_RESULT = 'b68fdc4788e1dbb7dd00aff2115c99b7add1205713ac7caba8825fe723c1a157'
SOURCE_PINS = 'abb6562a9d4ee8099d611ed161b345069e07ce9398e6a78faec4f4d624758b5a'
RAW = '9ae419d47fe59f8c339299ecc5f4cc8f4fef63743d04d3c38fa197106466444a'
VECTOR = 'd634dd53f7e82642790a93673ea5ad8a5d5a2ea6dc2ba92320bbdc5254d3b431'
COMMIT = '957e9d3e444826dea3edc1cafa9b2bdf1a9707544c9af0c57e918ddbbb5e4411'
CHECKER = '0826f7ca6192a2cb558dfe681c8fe4802cff595ace55cd1997da7576ba6e4ecc'
OWN = ('framing_audit.py', 'test_framing_audit.py')
FIELDS = ('k trial candidate cycles instructions bytes fcsr vcsr queries hits producers misses stores '
          'rejected conflicts allocation_failures evictions comparison_bytes_requested copied_payload_bytes '
          'vstart guard_bytes payload_equal payload_hash errors').split()
UVM_PREFIX = ('UVM_INFO '+str(IMAGE/'source/verification/uvm/ara_cvxif_uvm_pkg.sv')+
              '(259) @ ')
TRACE = re.compile(r'\[ARA_CONTRACT_TRACE\] sample=pre_edge cycle=(\d+) req=1/1 fire=1 '
                   r'id=([0-7]) insn=([0-9a-f]{8}) resp=1/1 fire=1 id=([0-7]) exc=0 '
                   r'pending=00 stalled=10 errors=0000000')
UVM = re.compile(re.escape(UVM_PREFIX)+r'(\d+): uvm_test_top.env.agent.monitor \[CVXIF/EVENT\] '
                 r'cycle=(\d+) req_fire=1 req_id=([0-7]) insn=([0-9a-f]{8}) '
                 r'resp_fire=1 resp_id=([0-7]) exc=0')
SCOPE = ('Separate framing-only audit of the original completed simulation, not a clean original-worker PASS. '
         'Exactly 8 UART trials, 24 fragments and 16 identified CSR probe interruptions. '
         'Strict original numerical checker on reconstructed UART records; independent frozen protocol '
         'checker on the entire unmodified raw log and vector trace. K4096 is activation-byte reshape, '
         'not a real K4096 operator; no model speedup or hardware acceptance claim.')


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, sort_keys=True, indent=2); f.write('\n')


def verify(pins):
    for p, value in pins.items(): require(sha(p) == value, 'Pin drift: '+str(p))


def load(path):
    spec = importlib.util.spec_from_file_location('original_strict_preflight_checker', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def reconstruct(text):
    lines = text.splitlines(); output = []; records = []; i = 0
    cuts = (FIELDS.index('vcsr'), FIELDS.index('vstart'))
    parts = (FIELDS[:cuts[0]], FIELDS[cuts[0]:cuts[1]], FIELDS[cuts[1]:])
    patterns = [re.compile(('EXT_PREFLIGHT_TRIAL' if n == 0 else '')+
                           ''.join(' '+key+r'=\d+' for key in keys)) for n, keys in enumerate(parts)]
    while i < len(lines):
        line = lines[i]
        if line.startswith('EXT_PREFLIGHT_TRIAL'):
            require(i+4 < len(lines), 'Truncated UART/probe frame')
            fragments = []; probes = []
            for offset, insn in ((0, '00f02473'), (2, '00802473')):
                pair = lines[i+offset].split('[ARA_CONTRACT_TRACE]')
                require(len(pair) == 2, 'Exactly one recognized probe insertion per segment')
                fragment, trace = pair[0], '[ARA_CONTRACT_TRACE]'+pair[1]
                require(patterns[offset//2].fullmatch(fragment) is not None, 'Malformed UART fragment/extra fields')
                t, u = TRACE.fullmatch(trace), UVM.fullmatch(lines[i+offset+1])
                require(t is not None and u is not None, 'Unknown/malformed/intervening probe record')
                tc, req, instruction, resp = t.groups()
                when, uc, ureq, uinsn, uresp = u.groups()
                require(instruction == insn and uinsn == instruction and req == resp == ureq == uresp and
                        int(uc) == int(tc)+1 and int(when) > 0, 'CSR probe pair identity/cycle mismatch')
                fragments.append(fragment); probes += [trace, lines[i+offset+1]]
            require(patterns[2].fullmatch(lines[i+4]) is not None, 'Malformed/truncated final UART segment')
            fragments.append(lines[i+4]); complete = ''.join(fragments)
            output += [complete, *probes]
            records.append(dict(raw_lines=[i+1, i+2, i+3, i+4, i+5],
                fragment_sha256=[digest(s) for s in fragments], probe_sha256=[digest(s) for s in probes],
                reconstructed_sha256=digest(complete), reconstructed=complete))
            i += 5; continue
        require('EXT_PREFLIGHT_' not in line or line == 'EXT_PREFLIGHT_DONE shapes=2 trials=8 calls=24 errors=0',
                'Unknown benchmark record/prefix')
        require(not line.startswith((' vcsr=', ' vstart=')), 'Orphan/extra UART fragment')
        output.append(line); i += 1
    require(len(records) == 8 and text.count('EXT_PREFLIGHT_TRIAL') == 8 and
            text.count('EXT_PREFLIGHT_DONE') == 1, 'Exactly 8 trials and one DONE required')
    return '\n'.join(output)+'\n', records


def image_inventory():
    sim = IMAGE/'sim'
    return {str(p): sha(p) for p in sorted(sim.rglob('*')) if p.is_file() and
            (p.name == 'simv' or p.is_relative_to(sim/'simv.daidir'))}


def destination(path):
    p = Path(path).resolve()
    require(p.parent == OUT and re.fullmatch(r'optimization_extension_preflight_framing_audit_[A-Za-z0-9_]+', p.name),
            'Fresh direct signoff audit output required')
    return p


def prepare(out):
    require(not out.exists(), 'Preserve prior audit output')
    verify({str(BENCH/'result.json'): ORIGINAL_RESULT, str(BENCH/'source-pins.json'): SOURCE_PINS,
            str(BENCH/'vcs/run.vcs.log'): RAW, str(BENCH/'vcs/vector.csv'): VECTOR,
            str(BENCH/'vcs/commit.csv'): COMMIT, str(BENCH/'inputs/check.py'): CHECKER})
    original = read(BENCH/'result.json')
    require(original['state'] == 'FAIL' and original['error'] ==
            "ValueError('Malformed/duplicate/unknown trial fields')", 'Only the known original framing failure')
    pins = read(BENCH/'source-pins.json'); verify(pins); verify(original['artifacts'])
    require(image_inventory() == read(BENCH/'plan.json')['image_pins'], 'Image membership/content drift')
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()

    def pin(p): pins[str(p)] = sha(p)
    def copy(src, dst):
        pin(src); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst); pin(dst)
    for name in OWN: copy(HERE/name, inputs/name)
    copy(BENCH/'inputs/check.py', inputs/'original_check.py')
    for src in sorted((BENCH/'inputs/verification/ara_verify').rglob('*.py')):
        require(pins.get(str(src)) == sha(src), 'Protocol source not sealed')
        copy(src, inputs/'verification/ara_verify'/src.relative_to(BENCH/'inputs/verification/ara_verify'))
    for p in (BENCH/'result.json', BENCH/'source-pins.json', BENCH/'build.json', BENCH/'commands.json'):
        pin(p)
    pins.update(original['artifacts']); pin(Path(sys.executable).resolve())
    with (out/'tests.log').open('x') as log:
        test = subprocess.run([sys.executable, '-B', inputs/'test_framing_audit.py', '-v'],
            cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    require(test.returncode == 0, 'Framing audit negative tests failed')
    pin(out/'tests.log'); verify(pins); save(out/'source-pins.json', pins)
    save(out/'prepared.json', dict(state='FRAMING_AUDIT_PREPARED', source_pins_sha256=sha(out/'source-pins.json'),
                                  scope=SCOPE, original_worker_state='FAIL', simulation_rerun=False))
    return read(out/'prepared.json')


def execute(out, review):
    require(Path(__file__).resolve() == out/'inputs/framing_audit.py', 'Frozen successor auditor required')
    require(sha(out/'source-pins.json') == review, 'Audit source pin identity')
    require(not (out/'attempt.json').exists() and not (out/'result.json').exists(), 'One independent audit attempt')
    pins = read(out/'source-pins.json'); verify(pins)
    save(out/'attempt.json', dict(pid=os.getpid(), original_result_sha256=ORIGINAL_RESULT, source_pins_sha256=review))
    report = dict(state='FAIL', scope=SCOPE, simulation_rerun=False, original_worker_state='FAIL',
                  original_result_path=str(BENCH/'result.json'), original_result_sha256=ORIGINAL_RESULT,
                  benchmark=str(BENCH), raw_log_path=str(BENCH/'vcs/run.vcs.log'), raw_log_sha256=RAW,
                  vector_trace_path=str(BENCH/'vcs/vector.csv'), vector_trace_sha256=VECTOR,
                  source_pins_sha256=review, performance_measured=False, automatic_retry=False)
    try:
        checker = load(out/'inputs/original_check.py')
        require(checker.FIELDS == FIELDS and sha(out/'inputs/original_check.py') == CHECKER, 'Original strict parser identity')
        raw = (BENCH/'vcs/run.vcs.log').read_text(); checker.successful(raw)
        # Establish that this audit does not silently reinterpret an original PASS.
        try: checker.numerical(raw, vcs=True, reference=read(BENCH/'spike-check.json'))
        except ValueError as exc: require(str(exc) == 'Malformed/duplicate/unknown trial fields', 'Different original failure')
        else: raise ValueError('Original parser no longer reproduces recorded framing failure')
        canonical, records = reconstruct(raw)
        (out/'numerical-framed.log').write_text(canonical); save(out/'fragments.json', records)
        numerical = checker.numerical(canonical, vcs=True, reference=read(BENCH/'spike-check.json'))
        save(out/'numerical.json', numerical)
        plan = read(BENCH/'plan.json'); env = plan['environment'].copy()
        env['PYTHONPATH'] = str(out/'inputs/verification')
        elf = plan['elves']['soc']['path']; simv = plan['simv']
        argv = [sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                '--require-axi', '--require-axi-write', '--vector-trace', str(BENCH/'vcs/vector.csv'),
                '--log', str(BENCH/'vcs/run.vcs.log'), '--simv', simv, '--elf', elf,
                '--output', str(out/'protocol.json')]
        save(out/'protocol.command.json', dict(argv=argv, cwd=str(out), environment=env, timeout_seconds=1200))
        with (out/'protocol.log').open('x') as log:
            process = subprocess.run(argv, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
        save(out/'protocol.exit.json', dict(returncode=process.returncode))
        require(process.returncode == 0, 'Independent full raw-log protocol failed')
        proof = read(out/'protocol.json')
        checker.protocol(proof, dict(elf_sha256=sha(elf), simv_sha256=sha(simv),
                                    log_sha256=RAW, vector_trace_sha256=VECTOR))
        expected_image = {p: h for p, h in plan['image_pins'].items() if p == simv or p.endswith('.so')}
        require(proof['sim_image_sha256'] == expected_image, 'Independent compiled-image identity')
        verify(pins); require(image_inventory() == plan['image_pins'], 'Post image membership/content drift')
        report.update(state='M4_PREFLIGHT_FRAMING_AUDIT_CHECKED', original_report_preserved=True,
            post_pins_match=True, post_image_match=True, performance_measured=True,
            complete_numerical=True, complete_raw_protocol=True, cycle_metrics=numerical['cycle_metrics'],
            trials=8, uart_fragments=24, csr_probe_interruptions=16,
            numerical_path=str(out/'numerical.json'), numerical_sha256=sha(out/'numerical.json'),
            canonical_log_path=str(out/'numerical-framed.log'), canonical_log_sha256=sha(out/'numerical-framed.log'),
            fragments_path=str(out/'fragments.json'), fragments_sha256=sha(out/'fragments.json'),
            protocol_path=str(out/'protocol.json'), protocol_sha256=sha(out/'protocol.json'),
            protocol_counts=proof['contract_counts'], image_pins=plan['image_pins'], elf_path=elf,
            elf_sha256=sha(elf), simv_path=simv, simv_sha256=sha(simv), full_model_claim=False)
    except BaseException as exc: report['error'] = repr(exc)
    report['artifacts'] = {str(p): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    save(out/'result.json', report); print(json.dumps(report), flush=True)
    return int(report['state'] != 'M4_PREFLIGHT_FRAMING_AUDIT_CHECKED')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'execute')); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-sha256'); args = parser.parse_args(); out = destination(args.output)
    if args.action == 'prepare': print(json.dumps(prepare(out)), flush=True); return 0
    return execute(out, args.review_sha256)


if __name__ == '__main__': raise SystemExit(main())
