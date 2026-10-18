#!/usr/bin/env python3
"""Restore/build archived probes, or run one frozen ELF on two existing simulators."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
APPS=('perf_exact_seed_fallback_latency','perf_exact_dense_seed_latency','perf_packet_normal_overlap')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('build','run'))
    parser.add_argument('--app',choices=APPS,default=APPS[0])
    parser.add_argument('--out',type=Path,help='New evidence directory, required for run')
    parser.add_argument('--baseline',type=Path,default=ROOT/'hardware/build/exact_direct_read_soc_v2/baseline/simv')
    parser.add_argument('--candidate',type=Path,default=ROOT/'hardware/build/production_tail_integrated_soc_20261017_v1/production/simv')
    parser.add_argument('--profile',action='store_true')
    args=parser.parse_args()
    if args.stage=='build':
        destination=ROOT/'apps'/args.app
        destination.mkdir(exist_ok=True)
        shutil.copy2(HERE/args.app/'main.c',destination/'main.c')
        if args.app==APPS[0]:
            subprocess.run([sys.executable,str(HERE/'gen_exact_seed_fallback_oracle.py'),
                            '--out',str(destination/'oracle.h')],check=True)
        subprocess.run(['make','-C',str(ROOT/'apps'),'bin/'+args.app],check=True)
        print('ELF_SHA256',sha(ROOT/'apps/bin'/args.app))
        return
    if args.out is None:
        parser.error('run requires --out')
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    (out/'elfs').mkdir()
    elf=out/'elfs'/args.app
    shutil.copy2(ROOT/'apps/bin'/args.app,elf)
    shutil.copy2(HERE/args.app/'main.c',out/'main.c')
    if args.app==APPS[0]:
        shutil.copy2(HERE/'gen_exact_seed_fallback_oracle.py',out/'gen_exact_seed_fallback_oracle.py')
        shutil.copy2(ROOT/'apps'/args.app/'oracle.h',out/'oracle.h')
    commands=[]
    for mode,sim in (('baseline',args.baseline),('integrated',args.candidate)):
        commands.append([sys.executable,str(ROOT/'hardware/scripts/run_reduction_audit.py'),
                         '--sim',str(sim.resolve()),'--elf-dir',str(out/'elfs'),
                         '--out',str(out/mode),'--jobs','1','--timeout','1800',
                         *(['--sim-arg','+PACKET_WB_PROFILE'] if args.profile else []),args.app])
    provenance={'elf_sha256':sha(elf),'source_sha256':sha(out/'main.c'),
                'simulator_sha256':{'baseline':sha(args.baseline.resolve()),'integrated':sha(args.candidate.resolve())},
                'commands':commands,'scope':'One identical frozen ELF; only this selected app. No compiler/synthesis/50-test runner.'}
    (out/'input_manifest.json').write_text(json.dumps(provenance,indent=2)+'\n')
    # Two independent existing simulators; no source edits during a run.
    children=[subprocess.Popen(command,cwd=ROOT) for command in commands]
    statuses=[child.wait() for child in children]
    if any(statuses):
        raise SystemExit('Failed selected probe run; evidence preserved: '+str(statuses))
    if args.app==APPS[0]:
        subprocess.run([sys.executable,str(HERE/'collect_fallback_results.py'),str(out),
                        '--out',str(out/'comparison.json')],check=True)


if __name__=='__main__':
    main()
