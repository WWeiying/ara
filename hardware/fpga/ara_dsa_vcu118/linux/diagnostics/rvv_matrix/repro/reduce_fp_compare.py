"""Reduce measured comparison failures using their original SoftFloat tables."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import fp_comparisons


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remaining_results(report, excluded):
    inputs = {c['name']: c['sha256'] for c in report['inputs']['cases']}
    if len(inputs) != len(report['inputs']['cases']):
        raise ValueError('Duplicate deployed case identity')
    skip = set()
    for manifest in excluded:
        for c in manifest['cases']:
            name, digest = c['original_name'], c['original_elf_sha256']
            if name in inputs and inputs[name] != digest:
                raise ValueError('Excluded parent ELF differs from measured original')
            if name in inputs:
                skip.add(name)
    return [r for r in report['results'] if r['status'] == 'failed' and
            r['name'].startswith('rvv_fp_compare_') and r['name'] not in skip]


def single_trial(source, fields):
    required = ('seed', 'op', 'vl', 'mask', 'sticky')
    if any(k not in fields or type(fields[k]) is not int or fields[k] < 0 for k in required):
        raise ValueError('Missing measured comparison stimulus')
    first = source.index('    unsigned lengths[]=')
    last = source.index('        for(unsigned i=0;i<128;++i)', first)
    variables = dict(seed=fields['seed'], op=fields['op'], vl=fields['vl'],
                     mode=fields['mask'], sticky=fields['sticky'], start=fields.get('vstart', 0))
    block = '    unsigned bytes=(cap+7)/8;\n    {\n'
    block += ''.join(f'        unsigned {k}={v};\n' for k, v in variables.items())
    block += '        unsigned prior=errors,flags=sticky;\n'
    block += '        text("RVV_REDUCED_BEGIN cases=1\\n");\n'
    return source[:first]+block+source[last:]


def with_data_detail(source):
    call = '        unsigned long status=functions[op](a,b,output+1,vl,cap,mask,start,sticky);\n'
    if source.count(call) != 1:
        raise ValueError('Expected one original comparison call')
    detail = '''        text("RVV_FP_COMPARE_RAW cap=");num(cap);
        text(" returned_vstart=");num((uint32_t)status);
        text(" actual_flags=");num(status>>32);
        text(" guard_before=");num(output[0]);
        text(" guard_after=");num(output[bytes+1]);text("\\n");
        for(unsigned d=0;d<bytes;++d) {
            text("RVV_FP_COMPARE_BYTE index=");num(d);
            text(" actual=");num(output[d+1]);text("\\n");
        }
'''
    return source.replace(call, call+detail)


def prefix_full_alias(source, fields):
    """Retain the measured first 50 calls; only this observed sequence is supported."""
    wanted = dict(op=0, seed=0, vl=512, mask=0, sticky=1)
    if any(fields.get(k) != v for k, v in wanted.items()) or 'vstart' in fields:
        raise ValueError('Outside measured full-capacity alias prefix')
    condition = 'seed==0 && op==0 && l==6 && mode==0 && sticky==1'
    detailed = with_data_detail(source)
    begin = '        text("RVV_FP_COMPARE_RAW cap=");num(cap);'
    end = '        if((uint32_t)status)++errors;'
    if detailed.count(begin) != 1 or detailed.count(end) != 1:
        raise ValueError('Comparison detail structure changed')
    detailed = detailed.replace(begin, '        if(' + condition + ') {\n' + begin)
    detailed = detailed.replace(end, '        }\n' + end)
    point = '        ++cases;\n    }\n'
    if detailed.count(point) != 1:
        raise ValueError('Comparison loop structure changed')
    return detailed.replace(point, '        ++cases;\n        if(' + condition +
        ')goto prefix_done;\n    }\nprefix_done:\n')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--report', type=Path, required=True)
    cli.add_argument('--campaign', type=Path, required=True)
    cli.add_argument('--cross', required=True)
    cli.add_argument('--out', type=Path, required=True)
    cli.add_argument('--exclude-manifest', type=Path, action='append', default=[],
                     help='Skip already reduced parents only when their original ELF hashes agree')
    cli.add_argument('--reconstructed-only', action='store_true',
                     help='Use current oracle only for changed-source parents; require identical archived assembly')
    cli.add_argument('--data-detail', action='store_true',
                     help='Emit raw destination bytes and returned CSR values after the same target call')
    cli.add_argument('--only-nonflag-failures', action='store_true',
                     help='Select measured failures whose expected and actual flags agree')
    cli.add_argument('--prefix-full-alias', action='store_true',
                     help='Retain the measured e16/m8 unmasked-v8 first50-call sequence')
    args = cli.parse_args()
    raw = args.report.read_bytes()
    report = json.loads(raw)
    report = report.get('report', report)
    results = remaining_results(report, [json.loads(p.read_text()) for p in args.exclude_manifest])
    if args.prefix_full_alias:
        if not args.reconstructed_only or not args.data_detail:
            raise ValueError('Prefix requires explicit reconstructed raw diagnostic mode')
        results = [r for r in results if r['name'] == 'rvv_fp_compare_unmasked_alias_v8_e16_m8']
    names = {r['name'] for r in results}
    originals = {}
    for path in sorted(args.campaign.glob('*/manifest.json')):
        original = json.loads(path.read_text())
        if not isinstance(original.get('source_sha256'), dict) or 'fp_compare_oracle.c' not in original['source_sha256']:
            continue
        for case in original['cases']:
            if case['name'] in names:
                originals[case['name']] = path, original, case
    if set(originals) != names or not names:
        raise ValueError('Missing original build manifests: '+str(names-set(originals)))
    args.out.mkdir(parents=True, exist_ok=False)
    binaries = args.out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    (args.out/'original_board_report.json').write_bytes(raw)
    source = TOOLS/'fp_compare_oracle.c'
    manifest = dict(scope='One actual comparison failure stimulus per parent ELF', cases=[],
        original_report_sha256=hashlib.sha256(raw).hexdigest(),
        source_sha256={p.name: sha(p) for p in (source, Path(__file__), Path(fp_comparisons.__file__))},
        original_preceding_trials_removed=True, board_reproduction_confirmed=False,
        excluded_manifests={str(p):sha(p) for p in args.exclude_manifest},
        deferred_source_mismatch=[])
    if args.prefix_full_alias:
        manifest.update(scope='Measured first50-call comparison prefix; source reconstruction',
                        original_preceding_trials_removed=False)
    for result in results:
        path, original, parent = originals[result['name']]
        changed = [name for name, digest in original['source_sha256'].items()
                   if sha(TOOLS/name) != digest]
        if changed and not args.reconstructed_only:
            manifest['deferred_source_mismatch'].append(dict(original_name=parent['name'],
                original_manifest=str(path), changed_sources=changed))
            continue
        if not changed and args.reconstructed_only:
            continue
        case, = [c for c in report['inputs']['cases'] if c['name']==result['name']]
        assert parent['sha256'] == case['sha256']
        detail = next(line for line in result['output'].splitlines()
                      if line.startswith('RVV_FP_COMPARE_DETAIL '))
        fields = {k: int(v) for k,v in re.findall(r'(\w+)=(\d+)', detail)}
        assert fields['errors'] > 0
        if args.only_nonflag_failures and fields['expected_flags'] != fields['actual_flags']:
            continue
        sew, lmul = parent['sew'], parent['lmul']
        name = parent['name'].replace('rvv_', 'rvv_detail_' if args.data_detail else 'rvv_small_', 1)
        if args.prefix_full_alias:
            name = parent['name'].replace('rvv_', 'rvv_prefix_', 1)
        directory = args.out/name
        directory.mkdir()
        c, asm = directory/'scenario.c', directory/'scenario.S'
        if args.prefix_full_alias:
            c.write_text(prefix_full_alias(source.read_text(), fields))
        else:
            reduced_source = single_trial(source.read_text(), fields)
            c.write_text(with_data_detail(reduced_source) if args.data_detail else reduced_source)
        unmasked = original.get('unmasked', False)
        destination = original.get('destination', 'v24')
        restart = original.get('restart_tested', False)
        unboxed = original.get('unboxed_scalar', False)
        assembly = fp_comparisons.assembly(sew, lmul, unmasked, destination, restart, unboxed)
        archived_assembly = path.parent/(parent['name']+'.S')
        assert archived_assembly.read_text() == assembly
        asm.write_text(assembly)
        for header in ('fixtures.h', 'operations.h'):
            shutil.copy2(path.parent/f'e{sew}'/header, directory/header)
        binary = binaries/name
        subprocess.run([args.cross+'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d',
            '-nostdlib', '-static', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
            '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
            '-Wl,--build-id=none', '-Wall', '-Wextra', '-Werror', f'-DSEW={sew}',
            '-DUNMASKED_COMPARISONS='+str(int(unmasked)),
            '-DUNBOXED_COMPARISONS='+str(int(unboxed)),
            '-DRESTART_COMPARISONS='+str(int(restart)),
            '-DDESTINATION_KIND='+str({'v24':0,'v8':1,'v16':2,'v0':3}[destination]),
            '-I'+str(directory), str(c), str(asm), '-o', str(binary)], check=True)
        with (directory/'scenario.dis').open('w') as output:
            subprocess.run([args.cross+'objdump','-d',str(binary)],stdout=output,check=True)
        manifest['cases'].append(dict(name=name, sew=sew, lmul=lmul, configurations=1,
            scenario_role='single_trial_raw_result' if args.data_detail else 'single_stimulus',
            sha256=sha(binary), pass_marker='RVV_FP_COMPARE_PASS', timeout_seconds=30,
            original_name=parent['name'], original_elf_sha256=parent['sha256'],
            original_manifest_sha256=sha(path), original_failure_detail=detail,
            oracle_provenance='current_reconstruction' if changed else 'original_source_hash_verified',
            changed_original_sources=changed, archived_assembly_sha256=sha(archived_assembly),
            measured_stimulus=fields, scenario_sources={p.name:sha(p) for p in
                (c, asm, directory/'fixtures.h', directory/'operations.h')}))
        if args.prefix_full_alias:
            manifest['cases'][-1].update(configurations=50, scenario_role='measured_prefix_raw_result',
                measured_board_vlen=1024, prefix_end='first full-capacity length, mask0, sticky1',
                reference_capacity_relative=True)
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (args.out/'overlay.cpio').open('wb') as output:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=args.out/'overlay',
            input=('\n'.join(entries)+'\n').encode(),stdout=output,check=True)
    print(json.dumps(dict(cases=len(manifest['cases']),
        deferred=len(manifest['deferred_source_mismatch']),output=str(args.out))))


if __name__=='__main__':
    main()
