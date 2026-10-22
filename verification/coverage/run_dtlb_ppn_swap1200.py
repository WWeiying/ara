"""One frozen ELF/image run: simulator1200s, outer systemd1260s, no retry/admission."""
import argparse
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import build_dtlb_ppn_swap779 as pre

life, require = pre.life, pre.require
PRE = life.OUT/'dtlb-ppn-swap-preflight779-agent-20261008-01/preflight.json'
PRE_SHA = '6406682f2833285682e3777c919f47e7daf11fbd849cee6447a023f44c9512fc'
CASE = 'dtlb_ppn_swap_matrix'
PROBE = Path(__file__).with_name('dtlb_ppn_swap1200_probe.tcl').resolve()
SCHEMA = 'DTLB_PPN_SWAP779_FROZEN1200_V1'


def command(output):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD='+str(PRE.parent/'input.elf'), '+TESTCASE='+CASE, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'), '+VECTOR_TRACE='+str(output/'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(output/'code.vdb'), '-cm_name', CASE,
        '+ARA_UVM_TRACE_LIMIT=100000', '+ARA_CONTRACT_TRACE_LIMIT=100000', '-ucli', '-do', str(PROBE)]


def validate_record(r):
    out = Path(r['output'])
    require(r['schema'] == SCHEMA and r['case'] == CASE and type(r['timeout_s']) is int and
        r['timeout_s'] == 1200 and type(r['systemd_runtime_max_s']) is int and
        r['systemd_runtime_max_s'] == 1260 and r['automatic_retry'] is False and
        r['coverage_admitted'] is False and r['preflight'] == str(PRE) and
        r['preflight_seal'] == PRE_SHA and r['baseline_seal'] == pre.BASE_SHA and
        isinstance(r['service'],str) and re.fullmatch(r'ara-[A-Za-z0-9_.-]+\.service',r['service']) and
        r['command'] == command(out) and out.parent == life.OUT and out.resolve() == out,
        'Exact frozen1200 command/population/budget required')
    return out


def prepare(output, service='ara-dtlb-ppn-swap779-20261008-01.service'):
    import collect_dtlb_ppn_swap1200 as collect
    q = life.read_bound(PRE, PRE_SHA)
    require(q['status'] == 'FULL_SPIKE_PTE_DATA_CSR_GUARDS_PASS_NOT_DUT' and q['baseline'] == 779 and
        q['counts']['matched_instructions'] == 191475 and q['counts']['software_checks'] == 8297 and
        q['counts']['translated_loads'] == 96 and q['coverage_admitted'] is False and q['VCS_launched'] is False,
        'Complete frozen software preflight required')
    require(output.parent == life.OUT and output.resolve() == output and not output.exists() and
        not output.with_name(output.name+'.prepared.json').exists(), 'Fresh independent run required')
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(image['simv'] == str(life.IMAGE) and len(image['image']) == 66, 'Exact66 old image required')
    pins = life.merge_pins(q['input_pins'], q['output_pins'])
    pins = life.merge_pins(pins, image['image'])
    pins = life.merge_pins(pins, {str(PRE):PRE_SHA, str(life.PLAN):life.PLAN_SEAL})
    proof, source_pins = collect.source_layout()
    pins = life.merge_pins(pins, source_pins)
    collect.reference_check(q)
    files = [PROBE, Path(__file__).resolve(), Path(__file__).with_name('test_run_dtlb_ppn_swap1200.py'),
             Path(collect.__file__), Path(__file__).with_name('test_collect_dtlb_ppn_swap1200.py'),
             collect.CONVERTER]
    require(life.digest(collect.CONVERTER) == collect.CONVERTER_SHA, 'Pinned VPD converter required')
    for module in tuple(sys.modules.values()):
        f = getattr(module, '__file__', None)
        if f and str(life.ROOT/'verification') in f and Path(f).is_file(): files.append(Path(f).resolve())
    for p in files: pins = life.merge_pins(pins, {str(p):life.digest(p)})
    life.check(pins)
    r = dict(schema=SCHEMA, case=CASE, output=str(output), command=command(output), pins=pins,
        preflight=str(PRE), preflight_seal=PRE_SHA, baseline_seal=pre.BASE_SHA,
        timeout_s=1200, systemd_runtime_max_s=1260, automatic_retry=False, coverage_admitted=False,
        budget_supersedes_unmeasured_preflight_prediction_seconds=300, source_layout=proof,
        qualification_automatic=False,service=service)
    validate_record(r)
    path = output.with_name(output.name+'.prepared.json'); life.save(path, r)
    print('PREPARED_NO_EDA', path, life.digest(path), flush=True)


def check(path, seal):
    r = life.read_bound(path, seal); validate_record(r); life.check(r['pins']); return r


def process_identity(pid, output, expected_sha, service):
    proc = Path('/proc')/str(pid)
    exe = (proc/'exe').resolve(strict=True)
    require(exe == life.IMAGE.resolve(strict=True) and life.digest(exe) == expected_sha,
            'Live executable differs from frozen simv')
    require((proc/'cwd').resolve(strict=True) == output, 'Live cwd differs')
    cmd = (proc/'cmdline').read_bytes().split(b'\0'); cmd = [x.decode() for x in cmd if x]
    require(cmd == command(output), 'Actual simulator command differs')
    cgroup=(proc/'cgroup').read_text()
    require(any(service in line.split(':',2)[-1].split('/') for line in cgroup.splitlines()),
            'Live simulator not in prepared owning service')
    return dict(pid=pid, executable=str(exe), executable_sha256=expected_sha,
                cwd=str(output), command=cmd, cgroup=cgroup,service=service)


def run(path, seal):
    r = check(path, seal); output = validate_record(r)
    require(not output.exists(), 'No repeat run')
    pins = life.merge_pins(r['pins'], {str(path):seal})
    actual = dict(r, pins=pins); output.mkdir(); life.save(output/'manifest.json', actual)
    child = None; start = time.monotonic(); timed_out = False
    try:
        life.check(pins)
        with (output/'console.log').open('x') as log:
            child = subprocess.Popen(r['command'], cwd=output, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            identity = process_identity(child.pid, output, pins[str(life.IMAGE)],r['service'])
            life.save(output/'live-simv-identity.json', identity)
            try: rc = child.wait(timeout=1200)
            except subprocess.TimeoutExpired:
                timed_out = True; raise
        require(type(rc) is int and rc == 0, 'Nonzero simulator exit')
        life.check(pins)
        life.save(output/'simulation-status.json', dict(status='SIMULATION_EXITED_NOT_ADMITTED',
            returncode=rc, timeout=False, elapsed_s=time.monotonic()-start, case=CASE,
            coverage_admitted=False, automatic_retry=False))
    except Exception as e:
        if child is not None:
            try: os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                child.wait()
        drift = None
        try: life.check(pins)
        except Exception as pin_error: drift = str(pin_error)
        life.save(output/'simulation-status.json', dict(status='SIMULATION_NOT_ADMITTED', timeout=timed_out,
            returncode=None if child is None else child.returncode, reason=str(e), pin_error=drift,
            elapsed_s=time.monotonic()-start, case=CASE, coverage_admitted=False, automatic_retry=False))
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('mode', choices=['prepare','check','run'])
    p.add_argument('--output', type=Path); p.add_argument('--input', type=Path); p.add_argument('--seal')
    p.add_argument('--service',default='ara-dtlb-ppn-swap779-20261008-01.service')
    a = p.parse_args()
    if a.mode == 'prepare':
        require(a.output is not None, 'Output required'); prepare(a.output.absolute(),a.service)
    else:
        require(a.input is not None and a.seal is not None, 'Prepared input/seal required')
        if a.mode == 'run': run(a.input.absolute(), a.seal)
        else: check(a.input.absolute(), a.seal); print('PREPARED_CHECK_PASS_NO_EDA')
