"""Build one-call preparation-trap candidates from measured original assembly."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from audit_segment_setup import inspect
from audit_slide import require
from trace_masks import sha


def first_operation(source):
    require(source.startswith('.text\n.global capacity\ncapacity:'), 'Capacity entry changed')
    require(source.count('.global op_0\n') == 1 and source.count('.global op_1\n') == 1,
            'Missing unique operation boundaries')
    prefix, _ = source.split('.global op_1\n', 1)
    require(prefix.rstrip().endswith('ret'), 'First operation does not terminate')
    return prefix


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('original', 'report', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--cross', required=True)
    a = p.parse_args()
    m = json.loads((a.original/'manifest.json').read_text())
    raw = json.loads(a.report.read_text()); report = raw.get('report', raw)
    inputs = {c['name']: c for c in report['inputs']['cases']}
    results = {r['name']: r for r in report['results']}
    require(len(inputs)==len(report['inputs']['cases']) and len(results)==len(report['results']),
            'Duplicate report identity')
    a.out.mkdir(exist_ok=False)
    binaries = a.out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source = Path(__file__).with_name('segment_setup.c')
    out = dict(scope='One archived preparation call; same board trap still requires measurement',
               original_report_sha256=sha(a.report), original_manifest_sha256=sha(a.original/'manifest.json'),
               original_c_source_equivalence_proven=False, board_reproduction_confirmed=False,
               generator_sha256=sha(Path(__file__)), cases=[])
    for parent in m['cases']:
        name = parent['name']; original = a.original/'overlay/opt/ara-tests'/name
        require(sha(original)==parent['sha256']==inputs[name]['sha256'], 'Original ELF identity mismatch')
        dis = subprocess.check_output([a.cross+'objdump','-d',str(original)],text=True)
        measured = inspect(parent,results[name],dis)
        candidate = name.replace('rvv_', 'rvv_small_', 1)
        directory = a.out/candidate;directory.mkdir()
        archived = a.original/(name+'.S')
        (directory/'scenario.S').write_text(first_operation(archived.read_text()))
        shutil.copy2(source,directory/'scenario.c')
        shutil.copy2(original,directory/'original.elf')
        (directory/'original.dis').write_text(dis)
        binary = binaries/candidate
        subprocess.run([a.cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none',
            '-Wall','-Wextra','-Werror',f'-DSEW={parent["sew"]}',
            str(directory/'scenario.c'),str(directory/'scenario.S'),'-o',str(binary)],check=True)
        out['cases'].append(dict(parent,name=candidate,sha256=sha(binary),configurations=1,
            pass_marker='RVV_SETUP_PASS',timeout_seconds=30,scenario_role='single_preparation_call',
            original_name=name,original_elf_sha256=parent['sha256'],measured_original=measured,
            archived_assembly_sha256=sha(archived),
            scenario_sources={f:sha(directory/f) for f in ('scenario.c','scenario.S')}))
    (a.out/'manifest.json').write_text(json.dumps(out,indent=2)+'\n')
    (a.out/'original_report.json').write_bytes(a.report.read_bytes())
    with (a.out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=a.out/'overlay',
            input=('opt\nopt/ara-tests\n'+''.join('opt/ara-tests/'+c['name']+'\n' for c in out['cases'])).encode(),
            stdout=stream,check=True)
    print('PREPARATION_TRAP_CANDIDATES',len(out['cases']))


if __name__=='__main__':main()
