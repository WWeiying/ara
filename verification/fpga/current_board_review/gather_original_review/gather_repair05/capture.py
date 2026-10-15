#!/usr/bin/env python3
"""One authorized two-case M4 capture; expected negative is evidence, not acceptance."""
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / '../integration'))
import run as integration

ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def resources():
    owned_unit = 'ara-gather-focused-candidate04-01.service'
    whole_unit = 'ara-whole-history59-candidate04-01.service'
    others, whole = [], []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc / 'comm').read_text().strip()
        except FileNotFoundError:
            continue
        # An unreadable potential simv is never silently omitted.
        if not comm.startswith('simv'):
            continue
        try:
            executable = str((proc / 'exe').resolve(strict=True))
            cgroup = (proc / 'cgroup').read_text()
            argv = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if Path(executable).name != 'simv':
            continue
        if owned_unit in cgroup:
            raise ValueError('Existing owned simulator; refuse repeat launch')
        record = dict(pid=int(proc.name), executable=executable, cgroup=cgroup, argv=argv)
        (whole if whole_unit in cgroup else others).append(record)
    memory = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    admitted = len(others) + max(6, len(whole)) + 2
    if admitted > 24 or memory['MemAvailable'] < 32 * 1024 * 1024:
        raise ValueError('Capacity admission failed')
    return dict(others=others, whole=whole, whole_reserved=6, own_reserved=2,
                admission_total=admitted, cap=24, available_kib=memory['MemAvailable'])


def profile():
    signals = ['ara_tb.clk', 'ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q']
    mask = ARA + '.i_masku'
    signals += [mask + '.' + name for name in (
        'pe_req_i', 'pe_req_valid_i', 'vinsn_issue', 'vinsn_issue_valid',
        'vrgat_cnt_q', 'masku_operand_alu_seq', 'masku_operand_alu_valid', 'masku_operand_alu_ready',
        'vrgat_req_idx_d', 'vrgat_req_idx_q', 'vrgat_idx_oor_d', 'vrgat_idx_oor_q',
        'vrgat_idx_fifo_push', 'vrgat_idx_fifo_pop', 'vrgat_idx_fifo_empty',
        'vrgat_req_d', 'vrgat_req_q', 'vrgat_req_fifo_push', 'vrgat_req_fifo_pop',
        'vrgat_req_no_data_d', 'masku_vrgat_req_o', 'masku_vrgat_req_valid_o', 'masku_vrgat_req_ready_i',
        'masku_operand_vd_seq', 'masku_operand_vd_valid', 'masku_operand_vd_ready',
        'issue_cnt_q', 'out_valid_cnt_q', 'out_vrf_word_valid', 'be_vrgat_seq_d',
        'vrgat_res', 'alu_result', 'result_queue_d', 'result_queue_q',
        'masku_result_req_o', 'masku_result_gnt_i', 'masku_result_addr_o',
        'masku_result_wdata_o', 'masku_result_be_o')]
    for i in range(4):
        lane = ARA + '.gen_lanes[%d].i_lane' % i
        signals += [lane + '.' + name for name in (
            'operand_request', 'operand_request_valid', 'operand_request_ready',
            'operand_queue_input', 'operand_queue_input_valid', 'vrf_operand', 'vrf_operand_valid')]
        req = lane + '.i_operand_requester'
        signals += [req + '.' + name for name in (
            'requester_metadata_q', 'operand_requester_gnt', 'operand_payload',
            'operand_queue_cmd_o', 'vrf_req_o', 'vrf_addr_o', 'vrf_tgt_opqueue_o',
            'vrf_wen_o', 'vrf_wdata_o', 'vrf_be_o')]
    return signals


def main():
    plan = json.loads((HERE / 'plan.json').read_text())
    pins = json.loads((HERE / 'prepared_pins.json').read_text())
    for path, digest in pins.items():
        if integration.sha(Path(path)) != digest:
            raise ValueError('Prepared pin drift: '+path)
    out = Path(plan['output'])
    out.mkdir(exist_ok=False)
    save(out / 'admission.json', resources())
    save(out / 'plan.json', plan)
    signals = profile()
    save(out / 'signals.json', signals)
    tcl = out / 'capture.tcl'
    # No force/deposit. Capture ends at 90000ns or simulator exit, whichever is earlier.
    tcl.write_text('\n'.join(['onerror {quit}', 'set fid [dump -file focused.fsdb -type FSDB]',
        *['dump -add {'+name+'} -aggregates -fid $fid' for name in signals],
        'run -absolute 90000ns', 'dump -disable -fid $fid', 'dump -flush $fid', 'run', 'quit'])+'\n')
    ledger = json.loads((Path(plan['image']) / 'image.json').read_text())
    integration.framework(Path(ledger['snapshot']) / 'sources')
    import ara_verify.runner as engine
    original = engine._run_monitored

    def capture(command, cwd, console, timeout, cancel):
        command = [*command, '-ucli', '-do', str(tcl)]
        (console.parent / 'command.json').write_text(json.dumps(dict(command=command, cwd=str(cwd)), indent=2)+'\n')
        # Two independent baseline observations: expected negative must not cancel control.
        # Fatal/assert/tool failures retain the existing monitor veto and per-case timeout.
        return original(command, cwd, console, timeout, threading.Event())

    engine._run_monitored = capture
    started = time.time()
    rc = integration.run_programs(SimpleNamespace(image=Path(plan['image']), programs=HERE / 'soc01',
        out=out / 'replay', case=[c['name'] for c in plan['cases']], jobs=2, timeout=180, execute=True))
    for path, digest in pins.items():
        if integration.sha(Path(path)) != digest:
            raise ValueError('Prepared pin changed during capture: '+path)
    save(out / 'complete.json', dict(status='BASELINE_CAPTURE_TERMINAL_NOT_ACCEPTANCE',
        runner_returncode=rc, elapsed_s=time.time()-started,
        results=json.loads((out / 'replay/summary.json').read_text()),
        retries=0, rtl_modified=False, force=False, pins_unchanged=True, prefix_closed=False))


if __name__ == '__main__':
    env = integration.environment()
    os.environ.clear()
    os.environ.update(env)
    main()
