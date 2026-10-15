#!/usr/bin/env python3
"""Pinned final04 baseline only: validate, then three isolated host-VCS runs."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import sv39_adapter as ref

IMAGE = Path('/home/wangwy/fpga_runs/current_board_integration_final04/campaign/image')
REFERENCE = ref.HERE / 'sv39_reference02'
RUNNER = ref.BASE / 'run.py'
PYTHON = Path('/usr/bin/python3')


def command(out, names, execute):
    cmd = [str(PYTHON), '-B', str(RUNNER), 'run', '--image', str(IMAGE),
           '--programs', str(REFERENCE/'soc'), '--jobs', '1', '--timeout', '600',
           '--out', str(out)]
    for name in names:
        cmd += ['--case', name]
    if execute:
        cmd += ['--execute']
    return cmd


def check_reference():
    status = json.loads((REFERENCE/'status.json').read_text())
    ref.require(status['status'] == 'HOST_SPIKE_PASS_NOT_DUT', 'Reference not passing')
    for name in ref.NAMES:
        ref.require(status['spike'][name]['status'] == 'HOST_SPIKE_PASS_NOT_DUT', 'Missing reference case')
    for name, digest in status['outputs'].items():
        ref.require(ref.sha(REFERENCE/name) == digest, 'Reference output drift: '+name)
    for path, digest in json.loads((REFERENCE/'input_pins.json').read_text()).items():
        ref.require(ref.sha(path) == digest, 'Reference input drift: '+path)


def preflight(out):
    ref.require(not out.exists(), 'Fresh independent output directory required')
    check_reference()
    out.mkdir(parents=True)
    ledger = json.loads((IMAGE/'image.json').read_text())
    snapshot = Path(ledger['snapshot'])
    repo = snapshot/'sources'
    simv = Path(ledger['simv'])
    config = dict(line.split('=',1) for line in (simv.parent/'simulator.conf').read_text().splitlines())
    for key,value in dict(nr_lanes='4',vlen='1024',sim_l2_bytes='2097152').items():
        ref.require(config[key] == value, 'Image/ELF geometry mismatch: '+key)
    ref.require(ref.sha(repo/'hardware/src/vlsu/addrgen.sv') ==
                'a339e5fe0c96728e4e97e21139b03649121a6c37ba765a4ee62f261c7e14f988',
                'Not the unfixed AddrGen baseline')
    soc = (repo/'hardware/src/ara_soc.sv').read_text()
    ref.require(re.search(r'OSSupport\s*=\s*1',soc) and 'cfg.NrPMPEntries          = 0;' in soc,
                'Expected OS/PMP setup changed')
    readelf = ref.CC.with_name('riscv64-unknown-elf-readelf')
    nm = ref.CC.with_name('riscv64-unknown-elf-nm')
    programs = json.loads((REFERENCE/'soc/programs.json').read_text())
    ref.require(programs['backend'] == 'vcs-soc', 'Wrong ELF backend')
    bindings = {}
    for name in ref.NAMES:
        entry = programs['programs'][name]
        elf = Path(entry['path'])
        ref.require(ref.sha(elf) == entry['sha256'], 'ELF changed: '+name)
        header = subprocess.check_output([str(readelf),'-h',str(elf)],text=True,timeout=15)
        layout = subprocess.check_output([str(readelf),'-Wl',str(elf)],text=True,timeout=15)
        symbols_text = subprocess.check_output([str(nm),'-n',str(elf)],text=True,timeout=15)
        symbols = {m[2]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+\w\s+(\S+)$',symbols_text,re.M)}
        ref.require('ELF64' in header and 'RISC-V' in header and
                    re.search(r'Entry point address:\s+0x80000000',header), 'Wrong executable ABI/entry')
        ref.require('tohost' not in symbols and 'replay_exit' in symbols, 'HTIF ELF on SoC')
        loads = re.findall(r'^\s*LOAD\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)',layout,re.M)
        ref.require(bool(loads), 'No ELF load segments')
        for va,pa,size in loads:
            va,pa,size = int(va,16),int(pa,16),int(size,16)
            ref.require(va == pa and 0x80000000 <= pa and pa+size <= 0x80200000,
                        'ELF load segment outside frozen L2')
        (out/(name+'.readelf.txt')).write_text(header+'\n'+layout)
        ref.save(out/(name+'.symbols.json'),symbols)
        bindings[name] = dict(elf=str(elf),sha256=entry['sha256'],
                              target_pc=hex(symbols['mt_target']),handler_pc=hex(symbols['mt_handler']))
    dry = command(out/'validate_before',ref.NAMES,False)
    ref.save(out/'validate_command.json',dry)
    with (out/'validate_before.log').open('x') as log:
        subprocess.run(dry,cwd=ref.ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    pins = {str(p):ref.sha(p) for p in (IMAGE/'image.json',snapshot/'snapshot.json',
            REFERENCE/'status.json',REFERENCE/'soc/programs.json',RUNNER,
            ref.BASE/'prepare.py',Path(__file__),ref.HERE/'sv39_adapter.py',
            repo/'verification/ara_verify/runner.py',repo/'hardware/tb/ara_commit_monitor.sv')}
    ref.save(out/'preflight.json',dict(status='PINNED_FINAL04_BASELINE_READY_NOT_CANDIDATE',
        image=str(IMAGE),simv=str(simv),configuration=config,bindings=bindings,pins=pins,
        interface='RV64 ELF/PRELOAD; UART0xc0000000; CTRL0xd0000000; commit CSV',
        real_S_mode=True,PMP_entries=0,timeout_per_case_s=600,max_parallel=3,
        reference_status='HOST_SPIKE_PASS_NOT_DUT',VCS_started=False,RTL_build=False))
    print(json.dumps(dict(status='PREFLIGHT_PASS',output=str(out),bindings=bindings),indent=2))


def verify_preflight(out):
    pre = json.loads((out/'preflight.json').read_text())
    ref.require(pre['status'] == 'PINNED_FINAL04_BASELINE_READY_NOT_CANDIDATE','Wrong preflight')
    for p,digest in pre['pins'].items():
        ref.require(ref.sha(p) == digest,'Preflight input drift: '+p)
    for entry in pre['bindings'].values():
        ref.require(ref.sha(entry['elf']) == entry['sha256'],'ELF drift')
    return pre


def launch(out):
    verify_preflight(out)
    ref.require(not (out/'launch.json').exists(),'Baseline already launched')
    cmd = [str(PYTHON),'-B',str(Path(__file__).resolve()),'worker','--out',str(out)]
    with (out/'supervisor.log').open('x') as log:
        child = subprocess.Popen(cmd,cwd=ref.ROOT,stdout=log,stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL,start_new_session=True)
    ref.save(out/'launch.json',dict(pid=child.pid,command=cmd,started_unix=time.time(),
             scope='final04 baseline only, not candidate',max_parallel=3,timeout_per_case_s=600))
    print(json.dumps(dict(supervisor_pid=child.pid,output=str(out))))


def worker(out):
    verify_preflight(out)
    ref.require(not (out/'worker.json').exists(),'Duplicate supervisor')
    ref.save(out/'worker.json',dict(pid=os.getpid(),started_unix=time.time()))
    processes, streams, launches = {}, {}, {}
    try:
        # Separate sealed runners preserve their checks without cross-case fail-fast.
        for name in ref.NAMES:
            cmd = command(out/name,[name],True)
            stream = (out/(name+'.runner.log')).open('x')
            streams[name] = stream
            processes[name] = subprocess.Popen(cmd,cwd=ref.ROOT,stdout=stream,
                stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
            launches[name] = dict(pid=processes[name].pid,command=cmd,started_unix=time.time())
        ref.save(out/'children.json',launches)
        results = {}
        for name, process in processes.items():
            rc = process.wait()
            results[name] = dict(returncode=rc,completed_unix=time.time(),
                                 runner_output=str(out/name))
            ref.save(out/'progress.json',results)
        verify_preflight(out)
        check_reference()
        ref.save(out/'complete.json',dict(status='FINAL04_BASELINE_RUNS_FINISHED_NOT_CANDIDATE',
             results=results,finished_unix=time.time(),RTL_changed=False,RTL_build=False,
             image_ledger_sha256=ref.sha(IMAGE/'image.json')))
    except Exception as error:
        ref.save(out/'failure.json',dict(error=str(error),time=time.time()))
        raise
    finally:
        for stream in streams.values():
            stream.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['preflight','launch','worker'])
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    globals()[args.command](ref.inside(args.out))


if __name__ == '__main__':
    main()
