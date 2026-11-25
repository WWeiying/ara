#!/usr/bin/env python3
"""Audited Q8 matmul subwindow from a completed continuous gate VCD; no GLS."""
import argparse
import collections
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
FROZEN = OUT / 'power_dc_20261117_formal_native_follow_01/q8/native/inputs'
DC_SHA = '66b6f9f1732020f3541db3e545cd991cdbb7f45041b1f76a4779a24a1a872903'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRIVATE = HERE if (HERE / 'reference-pair.json').exists() else FROZEN
d = load(PRIVATE / 'dc_power.py', 'phase_frozen_dc')
c = load(PRIVATE / 'convert.py', 'phase_frozen_converter')
require, read, save, sha = d.require, d.read, d.save, d.sha
require(sha(PRIVATE / 'dc_power.py') == DC_SHA, 'Reviewed DC helper drift')
BASE = 'ara_tb.dut.i_ara_soc.'
PATHS = {
    'clock': BASE+'clk_i', 'reset': BASE+'rst_ni',
    'pc': BASE+'i_system.i_ariane.pc_commit',
    'ack': BASE+'i_system.i_ariane.commit_ack_commit_id',
    'writeback': BASE+'i_system.i_ariane.wdata_commit_id',
    'dispatcher': BASE+'i_system.i_ara.i_dispatcher.state_q',
    'sequencer': BASE+'i_system.i_ara.i_sequencer.state_q',
    'vector_valid': BASE+'i_system.i_ara.i_sequencer.ara_req_valid_i',
    'qbs_state': BASE+'i_system.i_ara.i_vlsu.i_qbs_engine.state_q',
    'compute_state': BASE+'i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.state_q',
    'command': BASE+'i_system.i_ara.i_vlsu.i_qbs_engine.command_valid_i',
    'success': BASE+'i_system.i_ara.i_vlsu.i_qbs_engine.success_valid_o',
    'fault': BASE+'i_system.i_ara.i_vlsu.i_qbs_engine.fault_valid_o',
    'qbs_clock': BASE+'i_system.i_ara.i_vlsu.i_qbs_engine.clk_i',
}
PCS = {0x80001864: 0xc00029f3, 0x80001884: 0xc0002973}


def known(value):
    return bool(value) and not set(value)-set('01')


def update_status(path, data):
    temporary = path.with_suffix('.next')
    save(temporary,data)
    os.replace(temporary,path)


def probe_history(output):
    require(not output.exists(), 'Fresh nonmeasurement probe required')
    output.mkdir()
    vcd, saif = output/'history.vcd', output/'history.saif'
    lines = ['$timescale 1 ps $end', '$scope module ara_tb $end', '$scope module dut $end',
        '$scope module i_ara_soc $end', '$var wire 1 ! clk_i $end',
        '$var wire 1 " held_pre $end', '$var wire 1 # held_zero $end',
        '$upscope $end', '$upscope $end', '$upscope $end', '$enddefinitions $end',
        '#1000', '$dumpvars', '0!', '0"', '1#', '$end']
    for tick in range(1500, 200001, 500):
        lines += ['#'+str(tick), str(((tick-1000)//500)%2)+'!']
        if tick == 40000:
            lines.append('0#')
        if tick == 50000:
            lines.append('1"')
    vcd.write_text('\n'.join(lines)+'\n')
    argv = [str(c.TOOL), '-input', str(vcd), '-output', str(saif),
            '-instance', 'ara_tb.dut.i_ara_soc', '-time', '100000', '200000']
    with (output/'probe.log').open('x') as log:
        subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    one, zero = c.saif_summary(saif, 'held_pre'), c.saif_summary(saif, 'held_zero')
    duration = one['duration_ticks']
    require(duration*one['tick_fs'] == 100000000, 'Raw tick probe duration mismatch')
    require(one['clock_activity']['T1'] == duration and one['clock_activity']['TX'] == 0 and
            one['clock_activity']['TC'] == 0, 'Converter did not replay pre-window rising value')
    require(zero['clock_activity']['T0'] == duration and zero['clock_activity']['TX'] == 0 and
            zero['clock_activity']['TC'] == 0, 'Converter did not replay pre-window falling value')
    result = dict(state='CONVERTER_HISTORY_REPLAY_PROBE_PASS_NOT_MEASUREMENT', command=argv,
        fixture_not_measurement=True, held_pre=one, held_zero=zero,
        pins={str(p): sha(p) for p in (vcd, saif, c.TOOL, PRIVATE/'convert.py')})
    save(output/'result.json', result)
    return result


def elf_pcs(path):
    raw = path.read_bytes()
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(raw[:7] == b'\x7fELF\x02\x01\x01' and h[2] == 243, 'Expected pinned RISC-V ELF64 LE')
    observed = {}
    for pc, instruction in PCS.items():
        for index in range(h[10]):
            p = struct.unpack_from('<IIQQQQQQ', raw, h[5]+index*h[9])
            if p[0] == 1 and p[3] <= pc and pc+4 <= p[3]+p[5]:
                observed[pc] = struct.unpack_from('<I', raw, p[2]+pc-p[3])[0]
        require(observed.get(pc) == instruction, 'CSR boundary PC/opcode differs in exact ELF')
    return {hex(k): hex(v) for k,v in observed.items()}


def read_frames(vcd, evidence):
    reverse = {v:k for k,v in PATHS.items()}
    scopes, codes, widths = [], {}, {}
    with vcd.open() as stream:
        for line in stream:
            fields = line.split()
            if not fields:
                continue
            if fields[0] == '$scope':
                scopes.append(fields[2])
            elif fields[0] == '$upscope':
                scopes.pop()
            elif fields[0] == '$var':
                label = reverse.get('.'.join(scopes+[fields[4]]))
                if label:
                    codes.setdefault(fields[3], []).append(label)
                    widths[label] = int(fields[2])
            elif fields[0] == '$enddefinitions':
                break
    require(set(widths) == set(PATHS), 'Missing exact gate phase/control paths: '+str(set(PATHS)-set(widths)))
    alternatives = '|'.join(re.escape(code) for code in codes)
    expression = r'^(?:#[0-9]+|[01xXzZ](?:'+alternatives+r')|[bB][01xXzZ]+[ \t]+(?:'+alternatives+r'))$'
    command = ['/usr/bin/timeout', '--signal=TERM', '--kill-after=10', '7200',
               '/usr/bin/rg', '-N', expression, str(vcd)]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    frames, changes, tick = [], {}, None
    try:
        for raw in proc.stdout:
            line = raw.rstrip()
            if line.startswith('#'):
                if tick is not None:
                    frames.append((tick, changes))
                tick, changes = int(line[1:]), {}
                continue
            if line[0] in 'bB':
                value, code = line.split()
                value = value[1:].lower()
            else:
                value, code = line[0].lower(), line[1:]
            require(tick is not None, 'Value before native VCD timestamp')
            for label in codes[code]:
                changes[label] = value.rjust(widths[label], value[0] if value[0] in 'xz' else '0')
        require(proc.wait() == 0, 'Finite selected-signal scan failed')
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if tick is not None:
        frames.append((tick, changes))
    require(frames and frames[0][0] == evidence['first_tick'] and frames[-1][0] == evidence['last_tick'],
            'Parent native VCD bounds do not match completed receipt')
    return frames, command


def phase_bounds(frames, parent):
    evidence = parent['vcd_evidence']
    period = 1000000//evidence['timescale_fs']
    offset = evidence['first_tick']-parent['first_cycle']*period
    values, samples = {}, {pc: [] for pc in PCS}
    for tick, change in frames:
        values.update(change)
        if values.get('clock') != '0' or (tick-offset)%period or not known(values.get('ack')) or not int(values['ack'],2)&1:
            continue
        if not known(values.get('pc')):
            continue
        pc = int(values['pc'],2)
        if pc in samples:
            word = values.get('writeback', 'x')[-64:]
            require(known(word), 'Boundary CSR writeback contains X')
            samples[pc].append(dict(tick=tick, cycle=(tick-offset)//period, csr=int(word,2)))
    for pc, matches in samples.items():
        require(matches and len(matches) <= 2 and len({r['csr'] for r in matches}) == 1,
                'Missing/ambiguous stable CSR boundary '+hex(pc))
    first, last = samples[0x80001864][0], samples[0x80001884][0]
    span, csr_span = last['cycle']-first['cycle'], last['csr']-first['csr']
    require(span >= 20000 and abs(span-csr_span) <= 2, 'Matmul span/CSR read-slot phase inconsistent')
    require(parent['first_cycle'] <= first['cycle'] < last['cycle'] <= parent['last_cycle'], 'Phase outside original capture')
    return dict(first_tick=first['tick'], last_tick=last['tick'], first_cycle=first['cycle'],
        last_cycle=last['cycle'], cycles=span, period_ticks=period, tick_fs=evidence['timescale_fs'],
        duration_ticks=last['tick']-first['tick'], duration_fs=(last['tick']-first['tick'])*evidence['timescale_fs'],
        csr_start=first['csr'], csr_end=last['csr'], csr_duration=csr_span,
        rtl_reference=dict(first_csr=15988,last_csr=44479,cycles=28491),
        gate_minus_rtl=dict(start_cycle=first['cycle']-15988,end_cycle=last['cycle']-44479,duration=span-28491),
        read_slot_vs_CSR=dict(start_cycles=first['cycle']-first['csr'],end_cycles=last['cycle']-last['csr']),
        boundary_duration_uncertainty_cycles=2, boundary_duration_relative_bound=2/span,
        power_error_bound_claimed=False, boundary_samples={hex(pc):r for pc,r in samples.items()},
        semantics='Stable slot0 CSR PC/ack/writeback at falling edges; not a fabricated retire trace or RTL-cycle crop')


def audit_phase(frames, phase):
    values, dwell, transitions = {}, collections.defaultdict(collections.Counter), collections.Counter()
    rises = collections.defaultdict(list)
    critical = set(PATHS)-{'pc','ack','writeback'}
    pc_bad = 0
    for index, (tick, changes) in enumerate(frames):
        for name, value in changes.items():
            previous = values.get(name)
            if phase['first_tick'] < tick <= phase['last_tick'] and previous is not None and previous != value:
                transitions[name] += 1
                if value == '1' and name in ('command','success','fault'):
                    rises[name].append(tick)
            values[name] = value
        end = frames[index+1][0] if index+1 < len(frames) else tick
        dt = min(end,phase['last_tick'])-max(tick,phase['first_tick'])
        if dt <= 0:
            continue
        for name in critical:
            require(known(values.get(name)), 'Critical gate phase X: '+name)
            dwell[name][values[name]] += dt
        require(values['reset'] == '1' and values['fault'] == '0', 'Reset/fault during matmul')
        if known(values.get('ack')) and int(values['ack'],2)&1 and not known(values.get('pc')):
            pc_bad += 1
    require(pc_bad == 0 and len(rises['command']) == len(rises['success']) == 8 and not rises['fault'],
            'Not eight complete known QBS commands in matmul phase')
    require(any(int(v,2)==3 and t for v,t in dwell['compute_state'].items()), 'No QBS COMPUTE_TILE activity')
    require(not any(int(v,2) in (6,9) and t for v,t in dwell['qbs_state'].items()), 'QBS fault/drain state')
    require(abs(transitions['clock']-2*phase['cycles']) <= 2, 'Root clock/span mismatch')
    return dict(state='GATE_MATMUL_PHASE_AUDIT_PASS_NOT_TASK_PASS',
        control_dwell={k:dict(v) for k,v in dwell.items()}, rises=dict(rises), transitions=dict(transitions),
        unknown_PC_while_acknowledged=pc_bad, gate_protocol_proof=False,
        all_design_or_all_payload_knownness_claimed=False, power_acceptance=False)


def completed_parent(parent, out, plan, binding):
    original = read(parent/'result.json')
    if original['state'] == 'CAPTURE_COMPLETE_NOT_TASK_PASS':
        return original
    require(original['state'] == 'FAIL' and
            original.get('error') == "FileNotFoundError(2, 'No such file or directory')" and
            not (parent/'roi-selection.json').exists(), 'Not the scoped missing ROI bookkeeping failure')
    # This receipt is independent; the original FAIL and all its inputs remain unchanged.
    status = read(parent/'status.json')
    require(status.get('completed') is True and status.get('child_pid') is None,
            'Parent collector is not terminal')
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            require((entry/'cwd').resolve() != parent/'run', 'Live process still owns parent run directory')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    attempt = read(parent/'attempt.json')
    require(attempt['plan_sha256'] == sha(parent/'plan.json') and
            attempt['binding_sha256'] == sha(parent/'image-binding.json'), 'Original attempt identity drift')
    gate = load(parent/'inputs/gate_run.py', 'phase_original_gate')
    eof = load(parent/'inputs/audit_gate_capture_eof.py', 'phase_original_eof')
    log, console, vcd = parent/'run/run.vcs.log',parent/'run/console.log',parent/'run/window.vcd'
    text = log.read_text()
    gate.clean_log(text)
    gate.clean_log(console.read_text())
    require(not re.search(r'input (?:CLK|CEB/CEBM|WEB/WEBM|A/AM|BWEB/BWEBM) unknown/high-Z', console.read_text()),
            'Critical mapped memory X remains')
    require(re.search(r'^GATE_VRF_INIT_COMPLETE seed=0 words=512 reset=0 runtime_force=0\s*$',
                      console.read_text(), re.M), 'Reset-only VRF initialization missing')
    first,last = gate.capture_markers(text,plan['first_cycle'],plan['last_cycle'])
    require(re.search(r'\$finish at simulation time\s+'+str(last)+r'\s*$',text,re.M) and
            'V C S   S i m u l a t i o n   R e p o r t' in text, 'Missing clean actual EOF/finish')
    stat = vcd.stat()
    require(0 < stat.st_size <= plan['max_vcd_bytes'] and
            attempt['started_ns'] <= stat.st_mtime_ns <= (parent/'result.json').stat().st_mtime_ns and
            attempt['started_ns'] <= stat.st_ctime_ns <= (parent/'result.json').stat().st_mtime_ns,
            'VCD provenance/size mismatch')
    evidence = eof.inspect_vcd(vcd,first,last,plan['last_cycle']-plan['first_cycle'])
    receipt = dict(state='INDEPENDENT_EOF_CAPTURE_AUDIT_PASS_NOT_TASK_PASS',
        original_state='FAIL',original_result_unchanged=True,
        original_result=dict(path=str(parent/'result.json'),sha256=sha(parent/'result.json')),
        bookkeeping_failure='Sealed producer references absent roi-selection.json; actual selection is pinned in plan.window_selection',
        vcd=str(vcd),log=str(log),vcd_sha256=sha(vcd),log_sha256=sha(log),
        first_cycle=plan['first_cycle'],last_cycle=plan['last_cycle'],vcd_evidence=evidence,
        elf_sha256=plan['elf_map']['sha256'],simv_sha256=binding['simv_sha256'],
        full_gate_task_pass=False,gate_numeric_checked=False,gate_protocol_checked=False,
        simulator_exit_code_not_separately_recorded=True,
        evidence_scope='Independent immutable EOF/log/identity audit, not a rewritten original worker PASS')
    save(out/'parent-independent-audit.json',receipt)
    return receipt


def prepare(pair, parent, probe):
    require(pair.parent == OUT and not pair.exists(), 'Fresh owned postprocessing output required')
    require(read(probe/'result.json')['state'] == 'CONVERTER_HISTORY_REPLAY_PROBE_PASS_NOT_MEASUREMENT', 'History replay proof required')
    out = pair/'native'
    (out/'inputs').mkdir(parents=True)
    (out/'reports').mkdir()
    for source,name in ((Path(__file__).resolve(),'q8_matmul_post_v1.py'),
                        (HERE/'test_q8_matmul_post_v1.py','test_q8_matmul_post_v1.py'),
                        (FROZEN/'dc_power.py','dc_power.py'), (FROZEN/'convert.py','convert.py')):
        shutil.copyfile(source,out/'inputs'/name)
    reference = OUT/'power_dc_20261117_formal_native_follow_01/q8/pair-plan.json'
    shutil.copyfile(reference,out/'inputs/reference-pair.json')
    libraries = read(reference)['library_sha256']
    unit = pair.name.replace('_','-')+'.service'
    plan = dict(parent=str(parent), probe=str(probe/'result.json'), wait_seconds=36000,
        library_sha256=libraries, service_unit=unit, automatic_retry=False,
        reference_pair=str(reference), minimum_cycles=20000, no_GLS_or_compile=True,
        baseline_result=str(OUT/'power_dc_20261117_baseline_rvv_wide_02/q8/rvv/result.json'),
        limitations=['Native entire matmul vs RVV steady matmul subwindow: same stage, not identical cold/warm mixture or equal completed work',
            'CSR/read-slot endpoint quantization is not a percentage bound on power error',
            'No full gate numeric/protocol PASS; no timing/signoff or historical-baseline byte identity claim',
            'Strict annotation/link/unknown failures remain failures; provisional values do not relabel them'])
    save(out/'post-plan.json',plan)
    save(pair/'pair-plan.json',dict(runs=dict(native=str(out),rvv=str(pair/'peer-not-collected')),
        library_sha256=libraries,period_ns=1,limitations=plan['limitations']))
    paths = [*(p for p in (out/'inputs').iterdir() if p.is_file()), out/'post-plan.json',
             pair/'pair-plan.json',probe/'result.json', parent/'plan.json',parent/'source-pins.json',
             parent/'image-binding.json',parent/'image-pins.json', c.TOOL, reference]
    save(out/'post-pins.json',{str(p):sha(p) for p in paths})
    service = ['/usr/bin/systemd-run','--user','--unit='+unit,'--property=Type=exec',
        '--property=KillMode=control-group','--property=RuntimeMaxSec=72000','--property=TimeoutStopSec=30',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        '/usr/bin/python3','-B',str(out/'inputs/q8_matmul_post_v1.py'),'follow',
        '--output',str(pair),'--authorize-post']
    save(out/'ready-command.json',dict(service=service,shell=shlex.join(service),launched=False))
    save(out/'follow-status.json',dict(state='PREPARED_WAITING_PARENT_CAPTURE_NO_GLS',power_acceptance=False))


def follow(pair, authorized):
    out = pair/'native'
    require(authorized and Path(__file__).resolve() == out/'inputs/q8_matmul_post_v1.py', 'Authorized frozen post worker required')
    require(not (out/'follow-attempt.json').exists(), 'No postprocessing retry')
    job = read(out/'post-plan.json')
    owner = subprocess.check_output(['systemctl','--user','show',job['service_unit'],'-p','MainPID','--value'],text=True).strip()
    require(owner == str(os.getpid()) and job['service_unit'] in Path('/proc/self/cgroup').read_text(), 'Direct service owner required')
    d.verify(read(out/'post-pins.json'))
    save(out/'follow-attempt.json',dict(pid=os.getpid(),started_ns=time.time_ns()))
    def status(state):
        update_status(out/'follow-status.json',dict(state=state,pid=os.getpid(),power_acceptance=False))
        print(state,flush=True)
    try:
        parent = Path(job['parent'])
        status('WAITING_COMPLETED_PARENT_CAPTURE_NO_GLS_RERUN')
        deadline = time.monotonic()+job['wait_seconds']
        while not (parent/'result.json').exists():
            require(time.monotonic()<deadline,'Finite parent wait expired')
            time.sleep(120)
        status('VERIFYING_PARENT_AND_MEASURING_GATE_CSR_PHASE')
        plan,binding,ddc,pins,roles = d.activity_inputs(parent,'native','q8')
        capture = completed_parent(parent,out,plan,binding)
        require(plan['case_id'] == 'legacy_q8_qbs_sdk_v2_successor' and plan['init_seed'] == 0, 'Wrong admitted Q8 case/environment')
        vcd,log = parent/'run/window.vcd',parent/'run/run.vcs.log'
        require(sha(vcd)==capture['vcd_sha256'] and sha(log)==capture['log_sha256'], 'Completed parent file drift')
        require(capture['elf_sha256']==plan['elf_map']['sha256'] and capture['simv_sha256']==binding['simv_sha256'], 'Parent receipt identity')
        require(capture['vcd_evidence']['complete_initial_state'] and capture['vcd_evidence']['eof_at_selected_end'], 'Parent lacks complete native initial state/EOF')
        opcodes = elf_pcs(Path(plan['elf_map']['gls']))
        frames,scan_command = read_frames(vcd,capture['vcd_evidence'])
        phase = phase_bounds(frames,capture)
        activity = audit_phase(frames,phase)
        proof = dict(state=activity['state'],parent_capture=dict(path=str(parent/'result.json'),sha256=sha(parent/'result.json')),
            parent_VCD=dict(path=str(vcd),sha256=sha(vcd)),phase=phase,activity=activity,opcodes=opcodes,
            parent_independent_audit=str(out/'parent-independent-audit.json') if (out/'parent-independent-audit.json').exists() else None,
            scan_command=scan_command,initial_state_mode='vcd2saif replays intact parent history; tested by static-in-window nets changed before start',
            history_probe=dict(path=job['probe'],sha256=sha(job['probe'])),log_original_unchanged=True,
            no_child_TB_markers_fabricated=True,ELF_sha256=capture['elf_sha256'],simv_sha256=capture['simv_sha256'],
            whole_task_pass=False,power_acceptance=False)
        save(out/'phase-audit.json',proof)
        del frames
        d.verify(read(job['probe'])['pins'])
        status('CONVERTING_ACTUAL_MATMUL_RAW_TICK_SUBWINDOW')
        conversion = out/'phase-conversion';conversion.mkdir()
        saif = conversion/'activity.saif'
        argv = [str(c.TOOL),'-input',str(vcd),'-output',str(saif),'-instance','ara_tb.dut.i_ara_soc',
                '-time',str(phase['first_tick']),str(phase['last_tick'])]
        with (conversion/'conversion.log').open('x') as stream:
            subprocess.run(argv,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=14400)
        summary = c.saif_summary(saif)
        c.check_activity(phase,summary,phase['cycles'],1)
        pins.update({str(p):sha(p) for p in (parent/'result.json',vcd,log,out/'phase-audit.json',Path(job['probe']),c.TOOL,saif)})
        if (out/'parent-independent-audit.json').exists():
            pins[str(out/'parent-independent-audit.json')] = sha(out/'parent-independent-audit.json')
            for p in (parent/'run/console.log',parent/'attempt.json',parent/'status.json'):
                pins[str(p)] = sha(p)
        d.verify(pins)
        save(conversion/'source-pins.json',pins)
        save(conversion/'result.json',dict(state='SAIF_CONVERSION_PASS_NOT_POWER',parent_capture=proof['parent_capture'],
            phase_audit=dict(path=str(out/'phase-audit.json'),sha256=sha(out/'phase-audit.json')),
            command=argv,window=phase,saif=str(saif),saif_sha256=sha(saif),saif_summary=summary,
            instance='ara_tb/dut/i_ara_soc',source_pins=str(conversion/'source-pins.json'),
            elf_sha256=capture['elf_sha256'],simv_sha256=capture['simv_sha256'],whole_task_pass=False,power_measured=False))
        status('PREPARING_SAME_DDC_REAL_PIN_LOAD_DC')
        shutil.copyfile(ddc,out/'inputs/design.ddc')
        shutil.copyfile(saif,out/'inputs/activity.saif')
        (out/'inputs/power.tcl').write_text(d.make_real_load_tcl(out,sorted(job['library_sha256']),'qbs'))
        cpins = dict(job['library_sha256'])
        cpins.update({str(p):sha(p) for p in (d.DC_SHELL,*d.DC_INIT_FILES,out/'inputs/design.ddc',out/'inputs/activity.saif',out/'inputs/power.tcl')})
        (out/'inputs/container-pins.sha256').write_text(''.join(h+'  '+p+'\n' for p,h in sorted(cpins.items())))
        docker = Path(shutil.which('docker') or '/usr/bin/docker')
        command = [str(docker),'exec','-u',f'{os.getuid()}:{os.getgid()}','-e','HOME=/home/wangwy',
            '-e','SNPSLMD_LICENSE_FILE=27000@t7920','-w',str(out),'synopsys_workspace',
            '/usr/bin/timeout','--signal=TERM','--kill-after=20','3600','/bin/bash','-c',
            'sha256sum -c "$1" || exit 1; exec "$2" '+' '.join(d.DC_FLAGS)+' -f "$3"',
            'power-dc',str(out/'inputs/container-pins.sha256'),str(d.DC_SHELL),str(out/'inputs/power.tcl')]
        roles.update(phase_audit=dict(path=str(out/'phase-audit.json'),sha256=sha(out/'phase-audit.json')),
            initialization='Actual native reset-only VRF seed0; baseline initialization must be checked from its own producer',
            phase='Actual CSR-bounded matmul including command/setup/waits, quantization excluded',
            boundary_error=phase['boundary_duration_uncertainty_cycles'],cold_warm_equivalence=False)
        dcplan = dict(schema='power-real-pin-load-run-v1',role='native',pair=str(pair),command=command,
            high_fanout_net_threshold=0,execute_seconds=3600,service_unit=job['service_unit'],
            original_result=proof['parent_capture'],proof_roles=roles,saif_unknowns=d.saif_unknown_fraction(saif),
            period_ns=1,library_sha256=job['library_sha256'],limitations=job['limitations'],
            ddc_sha256=sha(out/'inputs/design.ddc'),saif_sha256=sha(out/'inputs/activity.saif'))
        d.validate_real_load_plan(dcplan)
        save(out/'plan.json',dcplan)
        pins.update(cpins)
        pins.update(read(out/'post-pins.json'))
        pins.update({str(p):sha(p) for p in (out/'inputs').iterdir() if p.is_file()})
        pins.update({str(out/'plan.json'):sha(out/'plan.json'),str(docker):sha(docker)})
        save(out/'source-pins.json',pins)
        status('WAITING_BOUNDED_SHARED_DC_SLOT')
        with d.activity_dc_slot(time.monotonic()+14400):
            rc = d.execute_real_load(argparse.Namespace(output=out,authorize_dc=True))
        status('DC_POSTPROCESS_COMPLETE_PROVISIONAL_NOT_SIGNOFF' if rc == 0 else 'DC_POSTPROCESS_FAILED_PRESERVED')
        return rc
    except Exception as error:
        d.atomic_save(out/'post-result.json',dict(state='FAIL_STOP_NO_GLS_RETRY',error=repr(error),
            parent_unchanged=True,new_GLS_launched=False,power_acceptance=False))
        status('POSTPROCESS_REJECTED_NO_RETRY')
        raise


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action',choices=('probe-history','prepare','follow'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--parent',type=Path,default=OUT/'power_gls_20261117_long_q8_02')
    parser.add_argument('--probe',type=Path,default=OUT/'power_vcd_history_probe_20261117_01')
    parser.add_argument('--authorize-post',action='store_true')
    args = parser.parse_args()
    if args.action == 'probe-history':
        print(json.dumps(probe_history(args.output.resolve())))
    elif args.action == 'prepare':
        prepare(args.output.resolve(),args.parent.resolve(),args.probe.resolve())
    else:
        return follow(args.output.resolve(),args.authorize_post)
    return 0


if __name__ == '__main__':
    sys.exit(main())
