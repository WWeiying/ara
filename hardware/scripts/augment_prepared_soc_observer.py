#!/usr/bin/env python3
"""Append frozen simulation observers to an unexecuted SoC preparation."""
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', type=Path)
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--define', action='append', default=[], help='Macro name or name=value; +define+ is added')
    parser.add_argument('--sim-arg', action='append', default=[], help='Audit simulator argument, typically +observer_enable')
    args = parser.parse_args()
    out = args.prepared.resolve()
    manifest_path = out/'manifest.json'
    prepared = json.loads(manifest_path.read_text())
    assert prepared['state'] == 'PREPARED_ONLY'
    assert not prepared['compiler_started'] and not prepared['simulator_started']
    assert not (out/'execution.json').exists(), 'Cannot augment an attempted execution'
    assert not (out/'before_observer').exists(), 'Observer augmentation already attempted'
    for path, digest in {**prepared['dependencies'], **prepared['frozen_files']}.items():
        assert sha(Path(path)) == digest, 'Frozen input changed: '+path
    sources = [source.resolve() for source in args.source]
    assert all(source.is_file() for source in sources)
    assert len(sources) == len(set(sources)), 'Duplicate observer source'
    assert len(args.define) == len(set(args.define)), 'Duplicate observer define'
    assert all(not value.startswith('+') and value for value in args.define)
    backup = out/'before_observer'
    backup.mkdir()
    shutil.copy2(manifest_path, backup/'manifest.json')
    changes = {'prepared_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'command':[sys.executable,*sys.argv], 'original_manifest_sha256':sha(backup/'manifest.json'),
        'production_rtl_recopied':False,'compiler_started':False,'simulator_started':False,'candidates':{}}
    shutil.copy2(Path(__file__), out/Path(__file__).name)
    for mode, entry in prepared['candidates'].items():
        directory = Path(entry['cwd'])
        saved = backup/mode
        saved.mkdir()
        for name in ('filelist','source_manifest.json'):
            shutil.copy2(directory/name, saved/name)
        filelist = directory/'filelist'
        lines = filelist.read_text().splitlines()
        extra = []
        provenance = []
        for index, source in enumerate(sources):
            frozen = directory/f'observer_{index}_{source.name}'
            assert not frozen.exists(), str(frozen)
            shutil.copy2(source, frozen)
            extra.append(str(frozen))
            provenance.append({'source':str(source),'frozen':str(frozen),'sha256':sha(frozen)})
        filelist.write_text('\n'.join(lines+extra)+'\n')
        command = list(entry['compile_command'])
        flags = ['+define+'+value for value in args.define]
        assert not set(flags)&set(command), 'Observer define already present in compiler command'
        command.extend(flags)
        hashes = dict(entry['sources'])
        hashes.update({path:sha(Path(path)) for path in extra})
        (directory/'source_manifest.json').write_text(json.dumps({'command':command,'sources':hashes},indent=2)+'\n')
        entry['compile_command'] = command
        entry['sources'] = hashes
        entry['audit_command'] = list(entry['audit_command'])+['--sim-arg='+value for value in args.sim_arg]
        entry['unique_changes']['all_other_filelist_lines_identical_except_recorded_production_rtl'] = False
        entry['unique_changes']['all_compile_arguments_identical_except_filelist'] = not flags
        entry['observer_augmentation'] = {'sources':provenance,'compile_defines':flags,
            'simulator_args':args.sim_arg,'original_filelist_prefix_identical':True,
            'all_preexisting_source_hashes_unchanged':True}
        changes['candidates'][mode] = {**entry['observer_augmentation'],
            'before_filelist_sha256':sha(saved/'filelist'),'after_filelist_sha256':sha(filelist),
            'before_source_manifest_sha256':sha(saved/'source_manifest.json'),
            'after_source_manifest_sha256':sha(directory/'source_manifest.json')}
    (out/'observer_augmentation.json').write_text(json.dumps(changes,indent=2)+'\n')
    prepared['observer_augmentation'] = str(out/'observer_augmentation.json')
    prepared['frozen_files'] = {str(path):sha(path) for path in out.rglob('*')
                                if path.is_file() and path != manifest_path}
    manifest_path.write_text(json.dumps(prepared,indent=2)+'\n')
    print(f'Appended frozen observers in {out}; preserved before_observer/; no compiler or simulator launched')


if __name__ == '__main__':
    main()
