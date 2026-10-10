"""One independent VCS sampling experiment; never merged into product coverage."""
import argparse
import gzip
import json
import os
from pathlib import Path
import shlex
import subprocess
import xml.etree.ElementTree as ET

import run_gap95_simulation as life

HERE = Path(__file__).resolve().parent
BUILD = life.OUT / 'repaired-aligned-build-20260930-01'
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')


def read_xml(p):
    return ET.fromstring(gzip.decompress(p.read_bytes()))


def run(out):
    if out.parent != life.OUT or out.exists():
        raise ValueError('Fresh independent output required')
    rebuild = BUILD / 'sim/simv.daidir/vcs_rebuild'
    words = shlex.split(next(s for s in rebuild.read_text().splitlines() if s.startswith('vcs ')))
    if any(w in words for w in ('-cm_fsmopt', '-cm_fsmresetfilter')):
        raise ValueError('Unexpected product FSM filters; review required')
    common = ['-full64', '-sverilog', '+v2k', '-Mupdate', '-j64', '-lca', '-kdb',
              '-debug_access+all', '+nospecify', '+notimingchecks', '+lint=TFIPC-L', '+vpi', '+lint=PCWM', '+error+30']
    for flag in common:
        if flag not in words:
            raise ValueError('Frozen compile flag missing: ' + flag)
    for flag, value in (('-cm', 'line+cond+fsm+tgl+branch'), ('-ntb_opts', 'uvm-1.2')):
        if words[words.index(flag) + 1] != value:
            raise ValueError('Frozen compile value differs')
        common.extend([flag, value])
    if '-timescale=1ns/100fs' not in words:
        raise ValueError('Frozen timescale differs')
    common.append('-timescale=1ns/100fs')
    common.extend(w for w in words if w.startswith('+define+'))
    source = HERE / 'fsm_async_reset_probe.sv'
    pins = {str(p): life.digest(p) for p in (source, Path(__file__).resolve(), rebuild,
        BUILD / 'compile.command.json', BUILD / 'sim/comp.vcs.log', VCS,
        Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/doc/UserGuide/pdf/cov_ug_vcsmx.pdf'))}
    life.check(pins)
    out.mkdir()
    command = [str(VCS), *common, '-Mlib=./incremental_db', '-top', 'fsm_reset_probe_tb',
               '-cm_dir', str(out / 'probe.vdb'), '-o', str(out / 'simv'), str(source)]
    env = dict(os.environ, VCS_HOME=str(VCS.parent.parent))
    env['PATH'] = str(VCS.parent) + os.pathsep + env.get('PATH', '')
    simcmd = [str(out / 'simv'), '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'probe.vdb'), '-cm_name', 'reset_sampling_probe']
    life.save(out / 'plan.json', dict(compile=command, simulation=simcmd, pins=pins,
        timeout_seconds_per_phase=120, independent_tool_probe=True, product_application=False,
        no_fsm_filter_options=True, hypothesis='Static reset arcs may be extracted but runtime sampling may not count asynchronous reset changes',
        witnesses='A/B/C non-IDLE at off-clock reset, immediate IDLE after NBA; all normal loop arcs positive controls',
        doc_pages=[77, 78, 84, 85, 86]))
    with (out / 'compile.log').open('x') as f:
        compile_result = subprocess.run(command, cwd=out, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=120)
    life.save(out / 'compile-terminal.json', dict(returncode=compile_result.returncode))
    if compile_result.returncode:
        raise ValueError('Compile failed; no retry')
    with (out / 'simulation.log').open('x') as f:
        simulation = subprocess.run(simcmd, cwd=out, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=120)
    life.save(out / 'simulation-terminal.json', dict(returncode=simulation.returncode))
    log = (out / 'simulation.log').read_text()
    if simulation.returncode or log.splitlines().count('FSM_RESET_PROBE_FUNCTIONAL_PASS') != 1 or log.count('RESET_BEFORE ') != 3 or log.count('RESET_AFTER ') != 3:
        raise ValueError('Missing exact functional witnesses')
    shape = out / 'probe.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml'
    data_files = list((out / 'probe.vdb/snps/coverage/db/testdata').glob('*/fsm.verilog.data.xml'))
    if len(data_files) != 1:
        raise ValueError('No unique native FSM bitmap')
    row = next(x for x in read_xml(data_files[0]).iter('instance_data') if x.get('name') == 'fsm_reset_probe_tb.dut')
    definition = next(x for x in read_xml(shape).iter('fsmdef') if x.get('chksum') == row.get('chksum'))
    bits, offset, records = row.get('value'), 0, []
    if set(bits) - {'0', '1'}:
        raise ValueError('Non-binary native FSM data')
    for fsm in definition.iter('fsmfsm'):
        states = list(fsm.findall('state'))
        names = {s.get('id'): s.get('name') for s in states}
        for index, edge in enumerate(fsm.findall('transition'), offset + len(states)):
            records.append(dict(fsm=fsm.get('name'), raw_index=index, source=names[edge.get('fromid')],
                destination=names[edge.get('toid')], hit=bits[index] == '1', shape=dict(edge.attrib)))
        offset += len(states) + len(fsm.findall('transition'))
    if offset != len(bits):
        raise ValueError('Native shape/bitmap length mismatch')
    life.check(pins)
    normal = [r for r in records if (r['source'], r['destination']) in [('A', 'B'), ('B', 'C'), ('C', 'A')]]
    reset = [r for r in records if r['source'] in ('A', 'B', 'C') and r['destination'] == 'IDLE']
    if len(normal) != 3 or not all(r['hit'] for r in normal) or len(reset) != 3:
        raise ValueError('Missing positive controls/reset shape; experiment inconclusive')
    result = dict(status='ONE_STANDALONE_FSM_RESET_SAMPLING_EXPERIMENT_COMPLETE', normal_edges=normal,
        reset_edges=reset, reset_edges_hit=sum(r['hit'] for r in reset), all_native_edges=records,
        raw_bitmap=bits, product_waiver_approved=False, product_application=False,
        conclusion='ASYNC_RESET_ARCS_ARE_COUNTED' if all(r['hit'] for r in reset) else
                   ('ASYNC_RESET_ARCS_NOT_COUNTED_IN_THIS_PROBE' if not any(r['hit'] for r in reset) else 'MIXED_RESET_ARC_SAMPLING'),
        pins={**pins, **{str(p): life.digest(p) for p in out.rglob('*') if p.is_file() and not p.is_symlink()}})
    life.save(out / 'result.json', result)
    print(json.dumps(dict(output=str(out), conclusion=result['conclusion'], reset_hit=result['reset_edges_hit'], seal=life.digest(out / 'result.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run(args.output.absolute())
