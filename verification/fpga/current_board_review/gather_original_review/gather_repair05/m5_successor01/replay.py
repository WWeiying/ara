#!/usr/bin/env python3
"""One M5 focused round; same ELFs, full scalar gate, first error cancels this scope."""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BEFORE = HERE.parent
sys.path.insert(0, str(BEFORE.parent.parent/'integration'))
import run as integration
preparation_spec = importlib.util.spec_from_file_location('m5_preparation', HERE/'prepare.py')
preparation = importlib.util.module_from_spec(preparation_spec)
preparation_spec.loader.exec_module(preparation)
sha, read, save, endpoint = preparation.sha, preparation.read, preparation.save, preparation.endpoint


def require(value, message):
    if not value:
        raise ValueError(message)


def pins(plan):
    for path, digest in plan['pins'].items():
        require(sha(Path(path)) == digest, 'Input/before pin drift: '+path)


def resources():
    live = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc/'comm').read_text().strip()
        except FileNotFoundError:
            continue
        if not comm.startswith('simv'):
            continue
        try:
            executable = str((proc/'exe').resolve(strict=True))
            group = (proc/'cgroup').read_text()
        except (FileNotFoundError,ProcessLookupError):
            continue
        require('ara-gather-focused-candidate05-01.service' not in group, 'Existing owned simv, refuse duplicate')
        if Path(executable).name == 'simv':
            live.append(dict(pid=int(proc.name),executable=executable,cgroup=group))
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:')))*1024
    require(len(live)+2 <= 24 and available >= 32*1024**3, 'Fresh capacity admission failed')
    return dict(live=live,own_reserved=2,total=len(live)+2,cap=24,mem_available_bytes=available,
                whole59_reserved=0,whole59_parent_confirmed_terminal=True)


def gate(folder, spec):
    text = (folder/'console.log').read_text()
    require(not re.search(r'RVV_PERMUTE_DETAIL|RVV_PERMUTE_FAIL|BOARD_CASE_FAIL|Core Test \*\*\* FAILED|\bTRAP\b|\bMISMATCH\b',text), 'Original failure veto')
    for marker in ('RVV_PERMUTE_PASS sew=8 cases=1 errors=0', 'BOARD_CASE_PASS '+spec['name'], 'BOARD_REPLAY_PASS'):
        require(text.splitlines().count(marker) == 1, 'Missing/duplicate '+marker)
    require('Core Test *** SUCCESS ***' in text, 'Simulator exit0 marker missing')
    expected = read(BEFORE/(spec['name']+'.expected.json'))['rows'][0]
    routine = {item['pc']:i for i,item in enumerate(spec['soc_routine'])}
    regs, indices, asm, returned, exited, count = {}, set(), [], None, False, 0
    with (folder/'commit_trace.csv').open() as stream:
        for row in csv.DictReader(stream):
            if row['event'] != 'retire':
                require(row['event'] != 'cvx_exception', 'CVX exception event')
                continue
            require(int(row['trap']) == 0 and int(row['order']) == count, 'Trap/noncontiguous retirement')
            count += 1
            pc, insn = int(row['pc'],16), int(row['insn'],16)
            rd, value, address = int(row['rd']), int(row['rd_wdata'],16), int(row['mem_addr'],16)
            if pc in routine:
                step = routine[pc]
                require(step == len(asm) and insn == int(spec['soc_routine'][step]['insn'],16), 'Original13asm/count/order drift')
                if step == 0:
                    require(all(regs.get(reg) == want for reg,want in (
                        (10,spec['input_address']), (11,spec['index_address']), (12,spec['output_address']+1),
                        (13,256), (14,512), (15,spec['predicate_address']), (16,0), (17,spec['actual_vstart']))), 'Original setup differs')
                if step == 9:
                    require(rd == 10 and value == 0, 'Returned vstart nonzero')
                    returned = value
                asm.append(row)
            if int(row['mem_rmask'],16) and spec['output_address'] <= address < spec['output_address']+514 and asm:
                require(len(asm) == 13, 'Oracle load before original asm return')
                index = address-spec['output_address']
                want = 91 if index in (0,513) else expected['output'][index-1]
                require(index not in indices and value & 255 == want, 'Fullcap/guard duplicate/mismatch')
                indices.add(index)
            if address == 0xd0000000 and int(row['mem_wmask'],16):
                require(int(row['mem_wdata'],16) == 0, 'CTRL exit nonzero')
                exited = True
            if rd:
                regs[rd] = value
    require(indices == set(range(514)) and len(asm) == 13 and returned == 0 and exited, 'Incomplete full514/CSR/asm/exit')
    require(sha(folder/'input.elf') == spec['soc_elf_sha256'], 'Private ELF changed')
    return dict(status='PASS_SINGLE_FULL514_ORIGINAL13ASM_EXIT0', returned_vstart=returned,
                fullcap_scalar_checks=512, guards=2, scalar_loads=514,
                target=asm[8], **endpoint(folder/'commit_trace.csv'))


def image_check(plan, expected_sha):
    image = Path(plan['image'])
    require(sha(image/'image.json') == expected_sha, 'Wrong/missing accepted M5 image')
    ledger = read(image/'image.json')
    snapshot = Path(ledger['snapshot'])
    require(sha(snapshot/'snapshot.json') == plan['source_delta']['snapshot_hashes'][1] == ledger['snapshot_sha256'], 'M5 snapshot drift')
    m4 = read(Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image/image.json'))
    require(ledger['configuration_sha256'] == m4['configuration_sha256'], 'M4/M5 simulator configuration differs')
    # The existing integration runner verifies all sealed source/image/manifest bytes before launch.
    return dict(image_sha256=expected_sha, snapshot_sha256=ledger['snapshot_sha256'],
                configuration_sha256=ledger['configuration_sha256'], simv=ledger['simv'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    require(args.execute, 'Preparation only; explicit execution flag required')
    plan = read(HERE/'focus_plan.json')
    pins(plan)
    admitted_image = image_check(plan,args.image_sha256)
    out = Path(plan['output'])
    out.mkdir(exist_ok=False)
    save(out/'image_admission.json', admitted_image)
    save(out/'plan.json', plan)
    spec = importlib.util.spec_from_file_location('m4_capture_profile', BEFORE/'capture.py')
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    save(out/'resources.json', resources())
    signals = [name for name in previous.profile() if name != previous.ARA+'.i_masku.vrgat_res']
    save(out/'signals.json', signals)
    tcl = out/'capture.tcl'
    with tcl.open('x') as stream:
        stream.write('\n'.join(['onerror {quit}', 'set fid [dump -file focused.fsdb -type FSDB]',
            *['dump -add {'+name+'} -aggregates -fid $fid' for name in signals],
            'run -absolute 90000ns', 'dump -disable -fid $fid', 'dump -flush $fid', 'run', 'quit'])+'\n')
    ledger = read(Path(plan['image'])/'image.json')
    integration.framework(Path(ledger['snapshot'])/'sources')
    import ara_verify.runner as engine
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern+'|RVV_PERMUTE_DETAIL|RVV_PERMUTE_FAIL|BOARD_CASE_FAIL',engine.FAIL_RE.flags)
    monitor, run_test = engine._run_monitored, engine.RegressionRunner._run_test
    checked = {}

    def capture(command, cwd, console, timeout, cancel):
        command = [*command, '-ucli', '-do', str(tcl)]
        (console.parent/'command.json').write_text(json.dumps(dict(command=command,cwd=str(cwd)),indent=2)+'\n')
        return monitor(command,cwd,console,timeout,cancel)

    def strict(self,test,image):
        result = run_test(self,test,image)
        if result.status == 'PASS':
            try:
                case = next(case for case in plan['cases'] if case['name'] == test.name)
                checked[test.name] = gate(result.artifact_dir,case)
                save(result.artifact_dir/'full514_gate.json',checked[test.name])
            except Exception as error:
                result.status,result.reason = 'FAIL',str(error)
        if result.status != 'PASS':
            self.cancel_event.set()
        return result

    engine._run_monitored, engine.RegressionRunner._run_test = capture, strict
    started = time.time()
    rc = integration.run_programs(SimpleNamespace(image=Path(plan['image']),programs=Path(plan['programs']),
        out=out/'replay',case=[case['name'] for case in plan['cases']],jobs=2,timeout=180,execute=True))
    pins(plan)
    image_check(plan,args.image_sha256)
    accepted = rc == 0 and set(checked) == {case['name'] for case in plan['cases']}
    save(out/'complete.json',dict(status='FOCUS_FULL514_PASS2_PENDING_WAVE' if accepted else 'NOT_ACCEPTED',
        runner_returncode=rc, checked=checked, results=read(out/'replay/summary.json'), elapsed_s=time.time()-started,
        before_endpoints=plan['m4_endpoints'], retries=0, prefix_closed=False,
        image=admitted_image, plan_sha256=sha(HERE/'focus_plan.json')))
    return 0 if accepted else 1


if __name__ == '__main__':
    env = integration.environment()
    os.environ.clear()
    os.environ.update(env)
    sys.exit(main())
