"""Explicit process receipt and sealed741 cache+45 suffix diagnostic for entropy64."""
import argparse
import json
import os
from pathlib import Path
import signal
import shlex
import subprocess
import time
from types import FunctionType
import xml.etree.ElementTree as ET

import run_scalar_entropy64 as runner
import collect_scalar_entropy64 as collector

life, need = runner.life, runner.need
CACHE = runner.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_SHA = '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'
SERVICE = 'ara-scalar-entropy64-786-parent-20261008-01.service'


def service_cgroup(text,expected):
    need(expected == SERVICE, 'Foreign configured service')
    rows = [line.split(':',2) for line in text.splitlines()]
    need(rows and all(len(row) == 3 and row[2].startswith('/') and
                     Path(row[2]).name == expected for row in rows), 'Foreign/missing systemd cgroup')


def cache_prefix(runtime, cache):
    need(cache['schema'] == 'RAW741_TOGGLE_SERIALIZED_CAPACITY_V1' and cache['tests'] == 741,
         'Wrong sealed cache schema/population')
    expected = []
    for member in runtime['input_ledger'][1:742]:
        files = list((Path(member)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(files) == 1, 'Ambiguous cached native member')
        expected.append(str(files[0]))
    cached = {p for p in cache['input_pins'] if p.endswith('/tgl.verilog.data.xml')}
    need(cached == set(expected) and len(expected) == len(set(expected)) == 741, 'Cache not exact741 prefix')
    for p,sha in cache['input_pins'].items():
        need(runtime['pins'].get(p) == sha, 'Cache/source authority conflicts: '+p)
    merged = {}
    for scope in runner.SCOPES:
        row = cache['instances'][scope]
        need(row['checksum'] == runner.CHECKSUMS[scope] and
             int(row['bits'],16).bit_length() <= row['width'], 'Cached typed identity differs')
        merged[scope] = {k:row[k] for k in ('width','checksum','bits')}
    return merged


def prepare(out):
    out, runtime = runner.prepare(out)
    need(runtime['pins'].get(str(CACHE)) == CACHE_SHA, 'Cache not in formal786 authority')
    cache = life.read_bound(CACHE,CACHE_SHA)
    cache_prefix(runtime,cache)
    for name in ('scalar_entropy64_reviewed.py','test_scalar_entropy64_reviewed.py'):
        path = runner.ROOT/'verification/coverage'/name
        runtime['pins'] = life.merge_pins(runtime['pins'],{str(path):runner.toggle.digest(path)})
    runtime['process_receipt_required'] = True
    runtime['expected_systemd_service'] = SERVICE
    runtime['toggle_cache'] = dict(path=str(CACHE),sha256=CACHE_SHA,prefix_tests=741,suffix_tests=45)
    runner.check(runtime['pins'])
    return out,runtime


def identity(pid, command, cwd, service):
    proc = Path('/proc')/str(pid)
    executable = (proc/'exe').resolve(strict=True)
    actual_cwd = (proc/'cwd').resolve(strict=True)
    actual_command = (proc/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
    actual_command = [x.decode() for x in actual_command]
    need(executable == Path(command[0]).resolve(strict=True) and actual_cwd == cwd and actual_command == command,
         'Live executable/cwd/command differs')
    stat = (proc/'stat').read_text().rsplit(')',1)[1].split()
    st = executable.stat()
    cgroup = (proc/'cgroup').read_text()
    service_cgroup(cgroup,service)
    return dict(pid=pid,executable=str(executable),exe_sha256=runner.toggle.digest(executable),
        cwd=str(actual_cwd),command=actual_command,cgroup=cgroup,expected_systemd_service=service,
        starttime_ticks=int(stat[19]),device=st.st_dev,inode=st.st_ino)


def execute(out,runtime):
    runner.check(runtime['pins'])
    need(not out.exists(), 'Runtime output already exists')
    out.mkdir()
    life.save(out/'manifest.json',runtime)
    started = time.monotonic()
    timed_out, code, error = False, None, None
    process = None
    try:
        with (out/'console.log').open('x') as log:
            process = subprocess.Popen(runtime['command'],cwd=out,stdout=log,stderr=subprocess.STDOUT,
                                       start_new_session=True)
            deadline = started+runtime['timeout_s']
            launch_identity = None
            while time.monotonic() < min(deadline,started+3):
                try:
                    launch_identity = identity(process.pid,runtime['command'],out,runtime['expected_systemd_service'])
                    break
                except (OSError,ValueError):
                    if process.poll() is not None:
                        break
                    time.sleep(.01)
            need(launch_identity is not None, 'No exact live simulator identity')
            need(launch_identity['exe_sha256'] == runtime['pins'][str(life.IMAGE)], 'Live image SHA differs')
            life.save(out/'launch-identity.json',launch_identity)
            print(json.dumps(dict(status='ACTUAL_SIMULATOR_STARTED',pid=process.pid,cwd=str(out))),flush=True)
            try:
                code = process.wait(timeout=max(.001,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid,signal.SIGTERM)
                try:
                    code = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    code = process.wait()
            need(not timed_out and type(code) is int and code == 0, 'Nonzero/timeout simulator terminal')
    except Exception as exc:
        error = '%s: %s'%(type(exc).__name__,exc)
        if process is not None and process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL)
            code = process.wait()
    try:
        runner.check(runtime['pins'])
    except Exception as exc:
        error = (error or '')+'; post-run pin rejection: '+str(exc)
    good = error is None and not timed_out and code == 0
    life.save(out/'execution-receipt.json',dict(schema='ENTROPY64_PROCESS_TERMINAL_V1',
        pid=process.pid if process else None,returncode=code,timed_out=timed_out,timeout_seconds=600,
        elapsed_seconds=time.monotonic()-started,reason=error,complete=good,
        launch_identity_sha256=runner.toggle.digest(out/'launch-identity.json') if (out/'launch-identity.json').exists() else None))
    life.save(out/'simulation-status.json',dict(status='SIMULATION_EXITED_NOT_ADMITTED' if good else 'SIMULATION_NOT_ADMITTED',
        returncode=code,timed_out=timed_out,case=runtime['case'],coverage_admitted=False,admission_performed=False))
    need(good,error or 'Failed terminal')


def verify_receipt(out,runtime):
    receipt = json.loads((out/'execution-receipt.json').read_bytes())
    launch = json.loads((out/'launch-identity.json').read_bytes())
    need(receipt['schema'] == 'ENTROPY64_PROCESS_TERMINAL_V1' and receipt['complete'] is True and
         type(receipt['timed_out']) is bool and receipt['timed_out'] is False and
         type(receipt['returncode']) is int and receipt['returncode'] == 0 and receipt['reason'] is None and
         receipt['timeout_seconds'] == runtime['timeout_s'] == 600 and
         receipt['launch_identity_sha256'] == runner.toggle.digest(out/'launch-identity.json'), 'Terminal receipt differs')
    need(type(launch['pid']) is int and launch['pid'] > 1 and launch['pid'] == receipt['pid'] and
         launch['command'] == runtime['command'] and launch['cwd'] == str(out) and
         launch['executable'] == str(life.IMAGE) and launch['exe_sha256'] == runtime['pins'][str(life.IMAGE)] and
         type(launch['starttime_ticks']) is int and launch['starttime_ticks'] > 0 and launch['cgroup'],
         'Recorded process identity differs')
    need(launch['expected_systemd_service'] == runtime['expected_systemd_service'] == SERVICE,
         'Recorded service differs')
    service_cgroup(launch['cgroup'],runtime['expected_systemd_service'])


def native_identity(sim,args,runtime,out):
    tests = sim.findall('srctest')
    need(sim.tag == 'test' and len(tests) == 1, 'Exactly one native test required')
    node = tests[0]
    need(shlex.split(node.get('cmdline','')) == runtime['command'] and node.get('workdir') == str(out) and
         node.get('seed') == '1' and node.get('teststatus') == 'unknown', 'Native command/cwd/seed identity differs')
    start,end = node.get('starttime',''),node.get('finishtime','')
    need(start.isdecimal() and end.isdecimal() and 0 < int(end)-int(start) <= 600000000,
         'Native duration missing/nonterminal/over budget')
    need(args.tag == 'vcm_args' and args.get('compvdbpath') == runtime['input_ledger'][0] and
         sorted(n.get('vcm_opt') for n in args.findall('vcm_arg_data') if n.get('vcm_opt')) ==
         ['-cm branch','-cm cond','-cm fsm','-cm line','-cm tgl'], 'Native compiled VDB/five metrics differ')
    return dict(seed=1,command=runtime['command'],workdir=str(out),compvdb=runtime['input_ledger'][0],
                starttime_us=int(start),finishtime_us=int(end),duration_seconds=(int(end)-int(start))/1000000,
                XML_teststatus='unknown',XML_status_not_claimed_as_PASS=True)


def read_native_identity(out,runtime):
    folders = [p for p in (out/'code.vdb/snps/coverage/db/testdata').iterdir() if p.is_dir()]
    need(len(folders) == 1 and folders[0].name == 'scalar_entropy64', 'Native test folder identity differs')
    return native_identity(runner.toggle.xml(folders[0]/'siminfo.xml'),
                           runner.toggle.xml(folders[0]/'vcmArguments.xml'),runtime,out)


def typed_sample(path,definitions):
    binary,_ = runner.toggle.rows(path,runner.SCOPES)
    root = runner.toggle.xml(path)
    intervals = {}
    for scope in runner.SCOPES:
        definition = definitions[scope]
        need(binary[scope]['checksum'] == definition['checksum'], 'Native binary checksum differs')
        arrays = [n for n in ET.fromstring(definition['shape']).find('tglshape') if n.tag == 'arrays']
        nodes = [n for n in root.iter('instance_intervaldata') if n.get('name') == scope]
        if not arrays:
            need(not nodes, 'Foreign MDA groups on compiled non-array scope')
            intervals[scope] = []
            continue
        need(len(nodes) == 1 and nodes[0].get('chksum') == definition['checksum'], 'Missing/foreign MDA identity')
        groups = runner.mda.intervals(nodes[0].get('value',''))
        need(len(groups) == len(arrays) and sorted(g['extent'] for g in groups) ==
             sorted(runner.mda.dimensions(n)[1] for n in arrays), 'Exact MDA array extent universe differs')
        intervals[scope] = groups
    return binary,intervals


def measure(out,runtime,run_dir,pins):
    verify_receipt(run_dir,runtime)
    native = read_native_identity(run_dir,runtime)
    before = json.loads((runner.BASE/'combined-bits.json').read_bytes())
    ledger = runtime['input_ledger']
    need(ledger == [ledger[0],*before['tests']] and len(before['tests']) == 786, 'Exact baseline lost')
    vdb = run_dir/'code.vdb'
    need(str(vdb) not in before['tests'], 'Duplicate VDB')
    listing = out/'single-inputs.txt'
    listing.write_text(ledger[0]+'\n'+str(vdb)+'\n')
    single = runner.bitmap.collect(listing)
    after = runner.bitmap.combine(before,single)
    need(after['tests'] == before['tests']+[str(vdb)] and len(set(after['tests'])) == 787, 'Unique prefix lost')
    count = 0
    for metric,scopes in before['metrics'].items():
        need(set(scopes) == set(single['metrics'][metric]) == set(after['metrics'][metric]), 'Metric universe differs')
        for scope,old in scopes.items():
            new,merged = single['metrics'][metric][scope],after['metrics'][metric][scope]
            need((old['width'],old['checksum']) == (new['width'],new['checksum']), 'Native metric identity differs')
            need(int(merged['bits'],16) == int(old['bits'],16)|int(new['bits'],16), 'Independent OR differs')
            count += 1
    need(count == 6162, 'Full6162 independent OR required')
    cache = life.read_bound(CACHE,CACHE_SHA)
    merged = cache_prefix(runtime,cache)
    for member in ledger[742:]:
        files = list((Path(member)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(files) == 1 and str(files[0]) in pins, 'Unbound suffix Toggle')
        binary,_ = typed_sample(files[0],runtime['compiled_definitions'])
        merged = runner.toggle.union(merged,binary)
    files = list((vdb/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(files) == 1, 'Ambiguous candidate Toggle')
    binary,intervals = typed_sample(files[0],runtime['compiled_definitions'])
    union = runner.toggle.union(merged,binary)
    for name,obj in (('single-bits.json',single),('combined-bits.candidate.json',after),
        ('native-runtime-identity.json',native),
        ('raw-delta.json',runner.bitmap.delta(before,after)),('typed-toggle.json',dict(before=merged,single=binary,
        after=union,new_serialized_positions=runner.toggle.gains(merged,union),singleton_MDA_intervals=intervals,
        cached_prefix_tests=741,decoded_suffix_tests=45,MDA_gain_not_counted=True,
        interval_code_direction_semantics_unknown=True,official_percentage=False))):
        life.save(out/name,obj)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('prepare','run-reviewed','collect'),required=True)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--seal')
    p.add_argument('--output',type=Path)
    a = p.parse_args()
    out = a.run.absolute()
    record = Path(str(out)+'.prepared.json')
    if a.mode == 'prepare':
        need(not record.exists(), 'Prepared record exists')
        _,runtime = prepare(out)
        life.save(record,runtime)
        print(json.dumps(dict(prepared=str(record),seal=runner.toggle.digest(record),pins=len(runtime['pins']))),flush=True)
    else:
        need(a.seal is not None,'Reviewed seal required')
        runtime = life.read_bound(record,a.seal)
        if a.mode == 'run-reviewed':
            _,current = prepare(out)
            need(current == runtime,'Reviewed contract differs')
            execute(out,runtime)
        else:
            need(a.output is not None,'Qualification output required')
            verify_receipt(out,runtime)
            read_native_identity(out,runtime)
            namespace = dict(collector.collect.__globals__,measure=measure)
            private = FunctionType(collector.collect.__code__,namespace,collector.collect.__name__)
            private(out,a.seal,a.output.absolute())


if __name__ == '__main__':
    main()
