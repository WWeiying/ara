#!/usr/bin/env python3
"""One bounded real operand_queue/VMFPU/FPnew minmax campaign; stop on failure."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = Path('/home/wangwy/fpga_runs/reduction_epoch_unit_20261010/preserve80')
VMFPU_SHA = 'e9b8c8c2aa952b76661b01fa0a4b53d87e2f1d7219beb40a42a4d6998c5f7b12'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2) + '\n')


def nan(width, signaling=False, payload=0x55, negative=False):
    fraction = {16: 10, 32: 23, 64: 52}[width]
    exponent = ((1 << (width - fraction - 1)) - 1) << fraction
    return (int(negative) << (width - 1)) | exponent | (0 if signaling else 1 << (fraction - 1)) | payload


def source(width, pattern, index):
    signaling = pattern == 11 and index % 2 == 1 or pattern == 12 and index == 33
    return nan(width, signaling, 0x25 + index % 32, bool(index % 2))


def oracle(width, seed, sources, active):
    fraction = {16: 10, 32: 23, 64: 52}[width]
    frac_mask = (1 << fraction) - 1
    exp_mask = ((1 << (width - fraction - 1)) - 1) << fraction
    quiet = 1 << (fraction - 1)
    operands = [seed] + [x for i, x in enumerate(sources) if active[i]]
    assert all(x & exp_mask == exp_mask and x & frac_mask for x in operands)
    if not any(active):
        return seed, 0
    return exp_mask | quiet, 16 if any(not x & quiet for x in operands) else 0


def cases():
    result = []
    # First four profiles prioritize all-qNaN and unchanged all-off payloads.
    profiles = [('qq_remote', 10, False, False, 1 << 33),
                ('qq_all', 10, False, True, 0),
                ('alloff_q', 11, False, False, 0),
                ('alloff_s', 11, True, False, 0),
                ('mixed_remote', 12, False, False, 1 << 33),
                ('mixed_all', 11, False, True, 0),
                ('seed_snan_remote', 10, True, False, 1 << 33)]
    for label, pattern, signaling, vm, mask in profiles:
        for width in (16, 32, 64):
            seed = nan(width, signaling, negative=True)
            sources = [source(width, pattern, i) for i in range(35)]
            active = [vm or bool(mask >> i & 1) for i in range(35)]
            expected, flags = oracle(width, seed, sources, active)
            for op, name in ((2, 'min'), (3, 'max')):
                result.append(dict(id=len(result), name=f'{name}_fp{width}_{label}',
                                   width=width, op=op, pattern=pattern, seed=seed,
                                   vm=int(vm), mask=mask, vl=35, source=sources,
                                   active=active, expected=expected, flags=flags))
    return result


def successor_tb():
    text = (BASE / 'inputs/test/reduction_tb.sv').read_text()

    def replace(old, new, count=1):
        nonlocal text
        assert text.count(old) == count, old
        text = text.replace(old, new)

    replace('localparam int N=4, VLEN=1024;',
            'parameter int N=4;\n  localparam int VLEN=1024, Rounds=$clog2(N)+1;')
    replace('int cycle=0, cid=-1, trace_fd, results_fd, count=0;',
            'int cycle=0, cid=-1, trace_fd, results_fd, probe_fd, count=0;')
    replace('elen_t [N-1:0] a, b, c, fp_result;',
            'elen_t [N-1:0] a, b, c, fp_result, neutral, saved_seed;\n'
            '  logic [N-1:0] epoch_active;')
    replace('assign state[l]=dut.mfpu_state_q;',
            'assign neutral[l]=dut.ntr_val;\n'
            '    assign saved_seed[l]=dut.reduction_seed_q;\n'
            '    assign epoch_active[l]=dut.reduction_epoch_any_active_q;\n'
            '    assign state[l]=dut.mfpu_state_q;')
    replace('if (pattern==1 && index==pos_idx) return inf;',
            "if (pattern>=10) return inf |\n"
            "      (((pattern==11 && index%2==1) || (pattern==12 && index==33)) ? 64'b0 :\n"
            "        (64'b1 << (sw==16 ? 9 : sw==32 ? 22 : 51))) |\n"
            "      (64'(index%2) << (sw-1)) | 64'(37+index%32);\n"
            '    if (pattern==1 && index==pos_idx) return inf;')
    replace('if (stage<3 && !(|response_valid) && &tx_valid)',
            'if (stage<Rounds && !(|response_valid) && &tx_valid)')
    replace('flags[0] | flags[1] | flags[2] | flags[3]', 'flag_bus', 2)
    replace('// Match ara_dispatcher: valid is ORed, but data is ORed without lane gating.',
            "logic [4:0] flag_bus;\n      flag_bus='0;\n"
            '      for (int l=0;l<N;l++) flag_bus |= flags[l];\n'
            '      // Match the real dispatcher OR-data / OR-valid contract.')
    replace('(l+N-(stage==1 ? 2 : 1))%N',
            '(l+N-((stage==Rounds-1 ? 1 : 1<<stage)%N))%N')
    replace('(ordered ? vl : 12)', '(ordered ? vl : N*Rounds)')
    replace('count++; running=0;',
            '$fflush(results_fd); $fflush(trace_fd); $fflush(probe_fd);\n'
            '    if ((observed&bitmask) !== expected || accrued !== expected_flags)\n'
            '      $fatal(1,"NAN_MINMAX_FIRST_FAILURE case=%s",name);\n'
            '    count++; running=0;')
    replace('if (&done_seen && !captured_done_flags)',
            '''for (int l=0;l<N;l++)
        $fdisplay(probe_fd,"%0d,%0d,%0d,%016h,%016h,%0d,%0d,%0d,%0d,%016h,%016h,%016h,%016h,%0d,%0d,%0d,%0d,%02h,%016h,%02h,%0d,%02h",
          cid,cycle,l,neutral[l],saved_seed[l],any_active[l],|any_active,epoch_active[l],first[l],
          qin[l][0],qin[l][1],qout[l][0],qout[l][1],qpush[l][0],qpush[l][1],
          qvalid[l][0]&&qconsume[l][0],qvalid[l][1]&&qconsume[l][1],mask[l],
          result[l],result_be[l],result_req[l]&&result_gnt[l],flags[l]);
      if (&done_seen && !captured_done_flags)''')
    replace('trace_fd=$fopen("trace.csv","w"); results_fd=$fopen("results.csv","w");',
            'trace_fd=$fopen("trace.csv","w"); results_fd=$fopen("results.csv","w");\n'
            '    probe_fd=$fopen("probe.csv","w");\n'
            '    $fdisplay(probe_fd,"case_id,cycle,lane,ntr,seed_q,local_active,global_active,epoch_active,first,seed_input,source_input,queue_seed,queue_source,seed_push,source_push,seed_fire,source_fire,mask,wb_data,wb_be,wb_fire,published_flags");')
    replace('$fclose(trace_fd); $fclose(results_fd); $finish;',
            '$fclose(trace_fd); $fclose(results_fd); $fclose(probe_fd); $finish;')
    return text


def main():
    out = HERE / 'run01'
    out.mkdir(exist_ok=False)
    status = dict(state='PREPARING', scope='directed module tests, not archived source or SoC closure', runs=[])
    save(out/'status.json', status)
    pins = {}

    def pin(name, source):
        target = out/'inputs'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        pins[name] = dict(source=str(source), sha256=sha(target))
        return str(target)

    try:
        assert sha(ROOT/'hardware/src/lane/vmfpu.sv') == VMFPU_SHA
        for name, entry in json.loads((BASE/'pins.json').read_text()).items():
            assert sha(BASE/'inputs'/name) == entry['sha256'], name
            if name.startswith('hardware/'):
                assert sha(ROOT/name) == entry['sha256'], name
                pin(name, ROOT/name)
        pin('provenance/base_tb.sv', BASE/'inputs/test/reduction_tb.sv')
        pin('provenance/base_command.json', BASE/'command.json')
        pin('provenance/run.py', Path(__file__))
        tb = out/'inputs/test/reduction_tb.sv'
        tb.parent.mkdir(parents=True)
        tb.write_text(successor_tb())
        pins['test/reduction_tb.sv'] = dict(source='bounded successor generated by pinned run.py', sha256=sha(tb))
        suite = cases()
        save(out/'cases.json', suite)
        calls = []
        for c in suite:
            calls.append(f'run_case({c["id"]}, "{c["name"]}", {c["width"]}, {c["width"]}, '
                         f'35, {c["op"]}, {c["pattern"]}, 33, -1, 512\'h{c["mask"]:x}, '
                         f'1\'b{c["vm"]}, 64\'h{c["seed"]:x}, 1, 0, 0, '
                         f'64\'h{c["expected"]:x}, 5\'h{c["flags"]:x}, 0);')
        callfile = out/'inputs/cases.svh'
        callfile.write_text('\n'.join(calls)+'\n')
        pins['cases.svh'] = dict(source='independent IEEE-bit oracle/cases.json', sha256=sha(callfile))
        save(out/'pins.json', pins)
        command = json.loads((BASE/'command.json').read_text())
        sources = [str(out/'inputs'/s.split('/inputs/')[1]) for s in command
                   if '/inputs/hardware/' in s and s.endswith(('.sv', '.v'))]
        vcs = '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
        env = dict(os.environ, VCS_HOME=vcs, SNPSLMD_LICENSE_FILE='27000@t7920',
                   VERDI_HOME='/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1')
        env['PATH'] = vcs+'/bin:'+env['PATH']
        for lanes in (4, 1):
            work = out/f'lane{lanes}'
            work.mkdir()
            compile_cmd = [vcs+'/bin/vcs', '-full64', '-sverilog', '-timescale=1ns/1ps', '-debug_access+all',
                           '-top', 'reduction_tb', '-pvalue+reduction_tb.N='+str(lanes),
                           '+incdir+'+str(out/'inputs/hardware/deps/common_cells/include'),
                           '+incdir+'+str(out/'inputs/hardware/include'), '+incdir+'+str(out/'inputs'),
                           *sources, str(tb), '-o', str(work/'simv'), '-l', str(work/'compile.log')]
            save(work/'compile_command.json', compile_cmd)
            status['state'] = f'COMPILING_LANE{lanes}'
            save(out/'status.json', status)
            start = time.monotonic()
            with (work/'compile.console.log').open('w') as log:
                compiled = subprocess.run(compile_cmd, cwd=work, env=env, stdout=log,
                                          stderr=subprocess.STDOUT, timeout=300)
            entry = dict(lanes=lanes, compile_rc=compiled.returncode,
                         compile_seconds=time.monotonic()-start)
            status['runs'].append(entry)
            if compiled.returncode:
                raise RuntimeError('COMPILE_FAILED; no retry')
            status['state'] = f'RUNNING_LANE{lanes}'
            save(out/'status.json', status)
            run = [str(work/'simv'), '-no_save', '+DEFERRED_FLAGS']
            save(work/'run_command.json', run)
            start = time.monotonic()
            with (work/'run.console.log').open('w') as log:
                ran = subprocess.run(run, cwd=work, env=env, stdout=log,
                                     stderr=subprocess.STDOUT, timeout=120)
            entry.update(run_rc=ran.returncode, run_seconds=time.monotonic()-start)
            if ran.returncode:
                raise RuntimeError('DUT_OR_HARNESS_FIRST_FAILURE; preserve outputs, no retry')
            log = (work/'run.console.log').read_text()
            rows = list(csv.DictReader((work/'results.csv').open()))
            assert 'REDUCTION_COMPLETE cases=42' in log
            assert not re.search(r'(?im)(fatal|error-|NAN_MINMAX_FIRST_FAILURE)', log)
            assert [r['name'] for r in rows] == [c['name'] for c in suite]
            assert all(r['result_match'] == r['flags_match'] == '1' for r in rows)
            entry.update(state='PASS', cases=len(rows), min_cycles=min(int(r['cycles']) for r in rows),
                         max_cycles=max(int(r['cycles']) for r in rows))
            print(json.dumps(entry), flush=True)
        for name, entry in pins.items():
            assert sha(out/'inputs'/name) == entry['sha256'], name
            if name.startswith('hardware/'):
                assert sha(ROOT/name) == entry['sha256'], name
        status.update(state='PASS_84_REAL_RTL_NAN_MINMAX', cases=84, pins_unchanged=True)
    except Exception as error:
        status.update(state='NOT_ACCEPTED', error=repr(error))
    save(out/'status.json', status)
    print(json.dumps(status, indent=2), flush=True)
    return 0 if status['state']=='PASS_84_REAL_RTL_NAN_MINMAX' else 1


if __name__ == '__main__':
    raise SystemExit(main())
