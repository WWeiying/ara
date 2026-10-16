"""Separate signal-frame and replay-result failures without changing recovery."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from trace_masks import sha, TOOLS
from fault_replay import LMULS, assembly


def unit_shape(manifest, case):
    if any(manifest.get(k, False) for k in ('indexed', 'strided', 'zero_stride',
           'negative_stride', 'negative_restart', 'negative_skip', 'trace')):
        raise ValueError('Only original single-field unit-stride replay is supported')
    sew, lmul = case['sew'], case['lmul']
    if manifest.get('fields', 1) != 1 or case.get('fields', 1) != 1:
        raise ValueError('Segment replay needs separate diagnostic semantics')
    if sew not in (8, 16, 32, 64) or lmul not in LMULS:
        raise ValueError('Unsupported unit shape')
    num, den, code = LMULS[lmul]
    if sew * den > 64 * num or case['name'] != f'rvv_fault_replay_e{sew}_{lmul}':
        raise ValueError('Reserved or mismatched unit shape')
    return sew, lmul, num, den, code


def segment_shape(manifest, case):
    fields = manifest.get('fields', 1)
    if fields not in range(2, 9) or case.get('fields', fields) != fields:
        raise ValueError('Missing or conflicting segment field count')
    sew, lmul = case['sew'], case['lmul']
    if case['name'] != f'rvv_fault_replay_segment_nf{fields}_e{sew}_{lmul}':
        raise ValueError('Mismatched segment case identity')
    unit_manifest = dict(manifest, fields=1)
    unit_case = dict(case, fields=1, name=f'rvv_fault_replay_e{sew}_{lmul}')
    shape = unit_shape(unit_manifest, unit_case)
    assembly(sew, lmul=lmul, fields=fields)  # Validate segment register-group legality.
    return shape, fields


def strided_shape(manifest, case):
    fields = manifest.get('fields', 1)
    if type(fields) is not int or fields not in range(1, 9) or case.get('fields', fields) != fields:
        raise ValueError('Missing or conflicting strided field count')
    if manifest.get('strided') is not True:
        raise ValueError('Strided layout must be explicit')
    negative, zero = manifest.get('negative_stride', False), manifest.get('zero_stride', False)
    if type(negative) is not bool or type(zero) is not bool or negative and zero:
        raise ValueError('Conflicting stride direction')
    sew, lmul = case['sew'], case['lmul']
    prefix = 'rvv_fault_replay' + (f'_segment_nf{fields}' if fields > 1 else '')
    expected = prefix + '_strided' + ('_negative_stride' if negative else '') + ('_zero_stride' if zero else '') + f'_e{sew}_{lmul}'
    if case['name'] != expected:
        raise ValueError('Mismatched strided case identity')
    plain = dict(manifest, strided=False, negative_stride=False, zero_stride=False)
    canonical = dict(case, name=prefix + f'_e{sew}_{lmul}')
    return segment_shape(plain, canonical) if fields > 1 else (unit_shape(plain, canonical), fields)


INSERTS={
    '    unsigned address_matches=0;': '''    text("RVV_FAULT_CONTEXT sig=");num(sig);text(" code=");num(info->si_code);
    text(" address=");num((uintptr_t)info->si_addr);text(" expected_address=");num(expected_address);
    text(" pc=");num(uc->uc_mcontext.sc_regs.pc);text(" expected_pc=");num((uintptr_t)(store_case ? fault_1_pc:fault_0_pc));
    text(" vstart=");num(state->vstart);text(" expected_start=");num(expected_start);
    text(" vl=");num(state->vl);text(" vtype=");num(state->vtype);text("\\n");
''',
    '        long address=call(222,0,8192,3,0x22,-1,0);': '''        unsigned prior_errors=errors;
        text("RVV_FAULT_BEGIN unmapped=");num(unmapped);text(" store=");num(store_case);
        text(" boundary=");num(boundary);text(" mode=");num(mode);text(" split=");num(split);text("\\n");
''',
    '        if(status || faults!=(expected_start<REPLAY_ELEMENTS))++errors;': '''        text("RVV_FAULT_RETURN status=");num(status);text(" faults=");num(faults);
        text(" expected_faults=");num(expected_start<REPLAY_ELEMENTS);
        text(" handler_errors=");num(handler_errors);text("\\n");
''',
    '        call(215,mapping,8192,0,0,0,0);++cases;': '''        text("RVV_FAULT_CHECK errors=");num(errors-prior_errors);text("\\n");
'''}


def restore_unit_handler(source):
    start = '    unsigned address_matches=0;'
    end = '    if(sig!=SIGSEGV || !address_matches ||'
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('Address validation block changed')
    before, tail = source.split(start)
    _, after = tail.split(end)
    return before + '    if(sig!=SIGSEGV || (uintptr_t)info->si_addr!=expected_address ||' + after


def instrument(source, strided=False):
    inserts = dict(INSERTS)
    if strided:
        point = '        long address=call(222,0,8192,3,0x22,-1,0);'
        inserts[point] = inserts[point].replace('num(split);text("\\n");', '''num(split);
#if !ZERO_STRIDE
        text(" gap=");num(gap);
#endif
        text("\\n");''')
    if '    unsigned address_matches=0;' not in source:
        context = inserts.pop('    unsigned address_matches=0;')
        inserts['    if(sig!=SIGSEGV || (uintptr_t)info->si_addr!=expected_address ||'] = context
    for point,insert in inserts.items():
        if source.count(point)!=1:raise ValueError('Original replay structure changed')
        source=source.replace(point,insert+point)
    return source


def main():
    p=argparse.ArgumentParser()
    for key in ('original','report','out'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--cross',required=True)
    p.add_argument('--case',default='rvv_fault_replay_e8_mf8')
    p.add_argument('--restore-unit-handler', action='store_true',
                   help='Reconstruct archived direct-address handler; requires byte-identical original ELF')
    p.add_argument('--compare-current-oracle',action='store_true',
                   help='Include immutable original and current baseline; do not claim source equivalence')
    p.add_argument('--segment-controls', action='store_true',
                   help='Unit-stride segment three-way controls only; no single-field reduction claim')
    p.add_argument('--strided-controls', action='store_true',
                   help='Positive, negative or zero-stride three-way controls; preserve gap and layout')
    a=p.parse_args()
    m=json.loads((a.original/'manifest.json').read_text())
    raw=json.loads(a.report.read_text());report=raw.get('report',raw)
    parent,=[c for c in m['cases'] if c['name']==a.case]
    fields = 1
    if a.strided_controls:
        if a.segment_controls or not a.compare_current_oracle or a.restore_unit_handler:
            raise ValueError('Strided diagnostics require separate three-way controls')
        shape, fields = strided_shape(m, parent)
    elif a.segment_controls:
        if not a.compare_current_oracle or a.restore_unit_handler:
            raise ValueError('Segment diagnostics require three-way controls and segment-aware handler')
        shape, fields = segment_shape(m, parent)
    else:
        shape = unit_shape(m, parent)
    sew,lmul,num,den,code=shape
    suffix=(f'segment_nf{fields}_' if fields > 1 else '')+f'e{sew}_{lmul}'
    if a.strided_controls:
        suffix = parent['name'].removeprefix('rvv_fault_replay_')
    deployed,=[c for c in report['inputs']['cases'] if c['name']==parent['name']]
    result,=[r for r in report['results'] if r['name']==parent['name']]
    if parent['sha256']!=deployed['sha256'] or result['status']!='failed':raise ValueError('Missing original failure')
    a.out.mkdir(exist_ok=False)
    name='rvv_trace_fault_replay_'+suffix
    d=a.out/name;d.mkdir()
    shutil.copy2(a.original/(parent['name']+'.S'),d/'scenario.S')
    flags=[a.cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
        '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
        '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
        '-Wall','-Wextra','-Werror',f'-DSEW={sew}','-DTRACE_REPLAY=0','-DNEGATIVE_RESTART=0',
        '-DINDEXED_REPLAY=0',f'-DINDEX_SEW={sew}',f'-DLMUL_NUM={num}',f'-DLMUL_DEN={den}',f'-DLMUL_CODE={code}',f'-DREPLAY_FIELDS={fields}']
    if a.strided_controls:
        flags += ['-DSTRIDED_REPLAY=1', f'-DNEGATIVE_STRIDE={int(m.get("negative_stride", False))}',
                  f'-DZERO_STRIDE={int(m.get("zero_stride", False))}']
    source=TOOLS/'fault_replay_oracle.c'
    source_code=source.read_text()
    if a.restore_unit_handler:
        if a.compare_current_oracle:
            raise ValueError('Restored source must pass strict original identity, not aggregate controls')
        source_code=restore_unit_handler(source_code)
    (d/'baseline.c').write_text(source_code)
    rebuilt=d/'original_rebuilt.elf'
    subprocess.run(flags+[str(d/'baseline.c'),str(d/'scenario.S'),'-o',str(rebuilt)],check=True)
    identical=sha(rebuilt)==parent['sha256']
    if not identical and not a.compare_current_oracle:raise ValueError('Original ELF rebuild differs')
    (d/'scenario.c').write_text(instrument(source_code, a.strided_controls))
    binaries=a.out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    binary=binaries/name
    subprocess.run(flags+[str(d/'scenario.c'),str(d/'scenario.S'),'-o',str(binary)],check=True)
    with (d/'scenario.dis').open('w') as stream:
        subprocess.run([a.cross+'objdump','-d',str(binary)],stdout=stream,check=True)
    manifest=dict(scope='Original replay with read-only signal/context/error diagnostics; timing may change',
        board_reproduction_confirmed=False,original_report_sha256=sha(a.report),
        original_manifest_sha256=sha(a.original/'manifest.json'),reducer_sha256=sha(Path(__file__)),
        cases=[dict(parent,name=name,sha256=sha(binary),original_name=parent['name'],
            original_elf_sha256=parent['sha256'],original_rebuild_byte_identical=identical,
            scenario_role='original_sequence_trace',
            scenario_sources={f:sha(d/f) for f in ('scenario.c','scenario.S','baseline.c')})])
    if a.compare_current_oracle:
        archived=a.original/'overlay/opt/ara-tests'/parent['name']
        if sha(archived)!=parent['sha256']:raise ValueError('Immutable original ELF changed')
        original_name='rvv_trace_fault_original_'+suffix
        baseline_name='rvv_trace_fault_baseline_'+suffix
        shutil.copy2(archived,binaries/original_name)
        shutil.copy2(rebuilt,binaries/baseline_name)
        controls=[dict(parent,name=original_name,original_name=parent['name'],
                       original_elf_sha256=parent['sha256'],scenario_role='immutable_original_control'),
                  dict(parent,name=baseline_name,sha256=sha(rebuilt),original_name=parent['name'],
                       original_elf_sha256=parent['sha256'],original_rebuild_byte_identical=identical,
                       scenario_role='current_oracle_control',source_directory=name,
                       scenario_sources={f:sha(d/f) for f in ('baseline.c','scenario.S')})]
        manifest['cases']=controls+manifest['cases']
        manifest['scope']='Original ELF versus current oracle versus instrumented oracle; semantic equivalence unproven'
        manifest['original_source_equivalence_confirmed']=identical
    if fields > 1:
        manifest['diagnostic_layout'] = dict(fields=fields, indexed=False, strided=False,
            fault_address_semantics='Any protected field within the expected segment; raw address differences are not necessarily errors',
            single_field_reducer_compatible=False)
    if a.strided_controls:
        manifest['diagnostic_layout'] = dict(fields=fields, indexed=False, strided=True,
            negative_stride=m.get('negative_stride', False), zero_stride=m.get('zero_stride', False),
            single_field_reducer_compatible=False)
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (a.out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=a.out/'overlay',
            input=('opt\nopt/ara-tests\n'+''.join('opt/ara-tests/'+c['name']+'\n' for c in manifest['cases'])).encode(),stdout=stream,check=True)
    print('ORIGINAL_REBUILD_IDENTICAL' if identical else 'ORIGINAL_SOURCE_EQUIVALENCE_UNPROVEN; THREE_WAY_CONTROL_READY')


if __name__=='__main__':main()
