#!/usr/bin/env python3
"""Prepare frozen, isolated backend ablations; never compile or simulate."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reference', type=Path, help='Reference build (production default: exact_direct_read_soc_v2/baseline; experiment default: scalar)')
    parser.add_argument('--production', action='store_true', help='Freeze one candidate from current production shared ordered and scalar add RTL')
    parser.add_argument('--production-all-rtl', action='store_true', help='Freeze all uniquely mapped production src/include RTL; implies --production')
    parser.add_argument('--report-cycle-differences', action='store_true', help='Report every cycle difference while requiring functional success')
    parser.add_argument('--prototypes', type=Path, default=root/'hardware/build/shared_add_backend_prototypes_v1')
    parser.add_argument('--priority-app', action='append', default=[], help='Schedule this existing reference app first (repeatable; complete suite is preserved)')
    parser.add_argument('--prepare-only', action='store_true', help='Always prepare only; accepted for clarity')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=3600)
    args = parser.parse_args()
    args.production = args.production or args.production_all_rtl
    assert not args.report_cycle_differences or args.production, 'Cycle reporting requires a production candidate'
    assert args.jobs > 0 and args.timeout > 0
    reference = args.reference or root/('hardware/build/exact_direct_read_soc_v2/baseline' if args.production else
                                      'hardware/build/exact_direct_read_soc_v2/scalar')
    ref, proto, out = reference.resolve(), args.prototypes.resolve(), args.out.resolve()
    original = json.loads((ref/'source_manifest.json').read_text())
    for path, digest in original['sources'].items():
        assert sha(Path(path)) == digest, 'Reference source changed: '+path
    protom = None
    if not args.production:
        protom = json.loads((proto/'manifest.json').read_text())
        for name, digest in protom['sources'].items():
            assert sha(proto/name) == digest, 'Prototype changed: '+name
    lines = (ref/'filelist').read_text().splitlines()
    matches = [i for i,line in enumerate(lines) if line.endswith('/shared_ordered_adder.sv')]
    assert len(matches)==1
    original_backend = Path(lines[matches[0]])
    if protom is not None:
        assert sha(original_backend)==protom['original_sha256'], 'Prototype baseline mismatch'
    assert not any(line.endswith(('/scalar_fp_add.sv','/shared_scalar_fp_add.sv')) for line in lines)
    configuration = json.loads((ref.parent/'configuration.json').read_text())
    apps = configuration['apps']
    assert len(apps)==len(set(apps))
    assert len(args.priority_app)==len(set(args.priority_app)), 'Duplicate priority app'
    assert set(args.priority_app)<=set(apps), 'Priority app is not in reference suite'
    apps = args.priority_app + [app for app in apps if app not in args.priority_app]
    elfsource = ref.parent/'elfs'
    for app in apps:
        assert sha(elfsource/app)==configuration['elf_sha256'][app], 'Reference ELF changed: '+app
    out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),out/Path(__file__).name)
    shutil.copy2(ref/'source_manifest.json',out/'reference_source_manifest.json')
    shutil.copy2(ref/'filelist',out/'reference_filelist')
    shutil.copy2(ref.parent/'configuration.json',out/'reference_configuration.json')
    if protom is not None:
        shutil.copy2(proto/'manifest.json',out/'prototype_manifest.json')
    (out/'elfs').mkdir()
    for app in apps: shutil.copy2(elfsource/app,out/'elfs'/app)
    # Keep all original compile flags and every unaffected source path verbatim.
    dependencies = dict(original['sources'])
    for line in lines:
        if line.startswith('+incdir+'):
            for directory in line[len('+incdir+'):].split('+'):
                for path in Path(directory).rglob('*'):
                    if path.is_file() and path.suffix in ('.sv','.svh','.vh','.h'):
                        dependencies[str(path)]=sha(path)
    dependencies.update({arg:sha(Path(arg)) for arg in original['command']
                         if Path(arg).is_absolute() and Path(arg).is_file()})
    manifest = {'scope':('frozen production shared adder SoC validation' if args.production else
                         'isolated SoC backend arithmetic ablations; no production integration'),
                'prepared_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'state':'PREPARED_ONLY','compiler_started':False,'simulator_started':False,
                'baseline':str(ref),'baseline_source_hashes_verified':len(original['sources']),
                'baseline_validation':'Not asserted; runner requires a complete baseline before comparison.',
                'apps':apps,'priority_apps':args.priority_app,'elf_source':str(elfsource),
                'elf_sha256':{app:sha(out/'elfs'/app) for app in apps},
                'dependencies':dependencies,'candidates':{},
                'comparison_mode':('report_cycle_differences' if args.report_cycle_differences else 'no_regression')}
    modes = [('production','shared_scalar_fp_add')] if args.production else [
        ('scalar_slices','scalar_fp_add'),('shared_add','shared_scalar_fp_add')]
    for mode,arith in modes:
        directory=out/mode
        directory.mkdir()
        selected=lines.copy()
        backend=directory/'shared_ordered_adder.sv'
        srcname='shared_ordered_adder_scalar.sv' if mode=='scalar_slices' else 'shared_ordered_adder_shared.sv'
        backend_source = root/'hardware/src/reduction/shared_ordered_adder.sv' if args.production else proto/srcname
        shutil.copy2(backend_source,backend)
        arithmetic=directory/(arith+'.sv')
        shutil.copy2(root/'hardware/src/reduction'/(arith+'.sv'),arithmetic)
        selected[matches[0]]=str(backend)
        selected.insert(matches[0],str(arithmetic))
        assert [line for line in selected if line not in (str(backend),str(arithmetic))] == [line for i,line in enumerate(lines) if i!=matches[0]]
        production_rtl = {}
        if args.production_all_rtl:
            by_name = {}
            for base in (root/'hardware/src', root/'hardware/include'):
                for source in base.rglob('*'):
                    if source.is_file() and source.suffix in ('.sv','.svh','.vh','.h'):
                        by_name.setdefault(source.name, []).append(source)
            for index, line in enumerate(selected):
                if line in (str(backend), str(arithmetic)) or not Path(line).is_absolute():
                    continue
                matches_by_name = by_name.get(Path(line).name, [])
                if len(matches_by_name) != 1:
                    continue
                source = matches_by_name[0]
                frozen = directory/'production_rtl'/source.relative_to(root/'hardware')
                frozen.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, frozen)
                production_rtl[line] = {'production':str(source),'frozen':str(frozen),
                    'reference_sha256':sha(Path(line)),'production_sha256':sha(source),
                    'identical':sha(Path(line))==sha(source)}
                selected[index] = str(frozen)
        filelist=directory/'filelist'
        filelist.write_text('\n'.join(selected)+'\n')
        build=original['command'].copy()
        build[build.index('-f')+1]=str(filelist)
        source_hashes={line:sha(Path(line)) for line in selected if Path(line).is_absolute() and Path(line).is_file()}
        (directory/'source_manifest.json').write_text(json.dumps({'command':build,'sources':source_hashes},indent=2)+'\n')
        audit=[sys.executable,str(root/'hardware/scripts/run_reduction_audit.py'),
               '--elf-dir',str(out/'elfs'),'--sim',str(directory/'simv'),
               '--out',str(directory/'regression'),'--jobs',str(args.jobs),'--timeout',str(args.timeout),*apps]
        manifest['candidates'][mode]={'state':'PREPARED','cwd':str(directory),'compile_command':build,'audit_command':audit,
            'sources':source_hashes,'production_rtl':production_rtl,'production_sources':({str(backend_source):sha(backend_source),
            str(root/'hardware/src/reduction'/(arith+'.sv')):sha(arithmetic)} if args.production else {}),'unique_changes':{'replaced':{'baseline':str(original_backend),'candidate':str(backend),
            'baseline_sha256':sha(original_backend),'candidate_sha256':sha(backend)},
            'inserted':{str(arithmetic):sha(arithmetic)},'all_other_filelist_lines_identical':not args.production_all_rtl,
            'all_other_filelist_lines_identical_except_recorded_production_rtl':True,
            'all_compile_arguments_identical_except_filelist':True}}
    manifest['frozen_files']={str(path):sha(path) for path in out.rglob('*') if path.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Prepared {len(apps)} frozen ELFs and {len(modes)} candidates in {out}; no compiler or simulator launched')


if __name__=='__main__':
    main()
