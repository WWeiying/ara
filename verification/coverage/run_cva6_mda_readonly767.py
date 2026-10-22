"""One bounded read-only singleton native MDA probe, never a population report."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import dve_tool_identity as tools
import inspect_cva6_mda767 as source

t, OUT = source.t, source.rank.OUT
EVIDENCE = OUT / 'cva6-mda-structure767-agent-20261007-01.json'
EVIDENCE_SHA = '56575b82687d84542272a3eaec6e85519b998fb4b34cad9cc939f51f40c20a78'
HERE = Path(__file__).resolve().parent


def save(path, value):
    with path.open('x') as stream: json.dump(value, stream, indent=2); stream.write('\n')


def check(pins):
    for path, sha in pins.items(): t.require(t.digest(path) == sha, 'Probe pin drift: ' + path)


def prepare(out):
    t.require(out.parent == OUT and not out.exists(), 'Fresh independent output')
    t.require(t.digest(EVIDENCE) == EVIDENCE_SHA, 'Static MDA binding changed')
    evidence = json.loads(EVIDENCE.read_bytes()); pins = dict(evidence['input_pins'])
    pins[str(EVIDENCE)] = EVIDENCE_SHA
    mpath = source.rank.BASE / 'admission-manifest.json'
    manifest = json.loads(mpath.read_bytes())
    vdb = Path(evidence['sample_vdb'])
    data = list((vdb / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    t.require(len(data) == 1, 'One singleton test')
    for p in vdb.rglob('*'):
        if p.is_file():
            t.require(str(p) in manifest['input_pins'], 'Unsealed sample VDB file: ' + str(p))
            pins[str(p)] = manifest['input_pins'][str(p)]
    for p in (Path(__file__), HERE / 'test_run_cva6_mda_readonly767.py', HERE / 'probe_cva6_mda_readonly.tcl'):
        pins[str(p)] = t.digest(p)
    identity = tools.prepare('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve', '/usr/bin/xvfb-run')
    check(pins)
    out.mkdir()
    entry = out / 'entry.tcl'
    design = OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb'
    selected = str(vdb.with_suffix('') / data[0].parent.name)
    body = 'source {' + str(HERE / 'probe_cva6_mda_readonly.tcl') + '}\n'
    body += 'set code [catch {\n'
    body += 'gui_open_cov -hier {' + str(design) + '} -testdir [list {' + str(vdb) + '}] -test [list {' + selected + '}] -merge ReadonlyMDA767Singleton\n'
    body += 'gui_list_expand -id CoverageTable.1 -all {<root>}\n'
    for i, scope in enumerate(source.SCOPES):
        body += 'mda_read_scope {' + scope + '} {' + str(out / ('scope_%d.tclrows' % i)) + '}\n'
    body += 'puts MDA_READONLY_DONE\n} message]\n'
    body += 'if {$code} {set f [open {' + str(out / 'error.txt') + '} w]; puts $f $message; puts $f $::errorInfo; close $f; puts MDA_READONLY_FAILED}\n'
    body += 'gui_exit -noprompt\n'
    with entry.open('x') as stream: stream.write(body)
    pins[str(entry)] = t.digest(entry)
    config = dict(schema='CVA6_MDA_SINGLETON_READONLY767_V1', static_binding_seal=EVIDENCE_SHA,
        sample_vdb=str(vdb), selected_test=selected, scopes=source.SCOPES,
        entry=str(entry), output=str(out), identity=identity, pins=pins, timeout_seconds=180,
        population_report=False, exclusion_operations=False, sim_launched=False)
    save(out / 'config.json', config)
    print('READONLY_PREPARED', t.digest(out / 'config.json'), flush=True)


def run(out, seal):
    t.require(t.digest(out / 'config.json') == seal, 'Exact prepared config seal')
    c = json.loads((out / 'config.json').read_bytes())
    t.require(c['schema'] == 'CVA6_MDA_SINGLETON_READONLY767_V1' and c['output'] == str(out), 'Wrong read-only plan')
    check(c['pins']); tools.revalidate(c['identity'])
    env = tools.controlled_environment(c['identity'], os.environ); env.pop('DVE', None)
    command = tools.launch_command(c['identity'], c['entry'])
    save(out / 'execution.json', dict(command=command, cwd=str(out), timeout=180, retry=False))
    live = []
    with (out / 'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        start = tools.process_info(process.pid)['starttime']
        time.sleep(8)
        for p in Path('/proc').iterdir():
            if not p.name.isdigit(): continue
            try:
                if (p / 'exe').resolve() == Path(c['identity']['executable']) and (p / 'cwd').resolve() == out:
                    live.append(tools.verify_live_executable(int(p.name), c['identity'], process.pid, start))
            except (OSError, ValueError): continue
        save(out / 'live-identity.json', live)
        print('ACTUAL_DVE', json.dumps(live), flush=True)
        timeout = False
        try: process.wait(timeout=172)
        except subprocess.TimeoutExpired:
            timeout = True; os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()
    save(out / 'terminal.json', dict(returncode=process.returncode, timeout=timeout, actual_dve=live))
    check(c['pins']); tools.revalidate(c['identity'])
    gui = out / 'DVEfiles/dve_gui.log'
    ok = process.returncode == 0 and not timeout and len(live) == 1 and not (out / 'error.txt').exists() and gui.is_file() and gui.read_text().splitlines().count('MDA_READONLY_DONE') == 1
    save(out / 'status.json', dict(status='NATIVE_READONLY_EXPORTED_NOT_ENCODING_QUALIFIED' if ok else 'READONLY_PROBE_FAILED',
        config_seal=seal, files={str(p): t.digest(p) for p in out.glob('scope_*.tclrows')},
        no_VCS=True, no_exclusions=True, physical_encoding_qualified=False))
    t.require(ok, 'Read-only native probe failed; preserved evidence')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    args = parser.parse_args(); out = args.output.resolve()
    if args.mode == 'prepare': prepare(out)
    else:
        t.require(args.seal is not None, 'Explicit seal required'); run(out, args.seal)
