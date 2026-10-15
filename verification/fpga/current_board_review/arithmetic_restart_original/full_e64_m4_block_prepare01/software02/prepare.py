"""One approved sticky-comparator candidate, using frozen software01 machinery."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode = True
H = Path(__file__).resolve().parent
OLD = H.parent/'software01'
P = H.parent/'static_sticky01'
A = H.parents[1]
spec = importlib.util.spec_from_file_location('software01_utilities', OLD/'prepare.py')
old = importlib.util.module_from_spec(spec); sys.modules[spec.name] = old; spec.loader.exec_module(old)
old.HERE = H
sha, read, emit, save, need, replace = old.sha, old.read, old.emit, old.save, old.require, old.replace


def materialize():
    need(not (H/'source_entry.json').exists(), 'Single candidate materialization')
    review = A/'e64_m4_source_review01/STICKY_SOURCE_REVIEW.md'
    need(sha(review)=='dd0cd7e1cf6d3a55590af9d89ebf923f4f39754b9b3113909925f2ecf4e9fc2c', 'Exact source review')
    need(sha(P/'proposed_comparator.h')=='d62ed3b0ad63bff1df0ba5cf78497cf3d85df309a6caa016774fdfb54edae17f', 'Approved comparator')
    pins=read(OLD/'pins.json')
    for p,h in pins.items(): need(sha(p)==h, 'Old candidate unchanged '+p)
    for name in ['case.c','original_case.c','dictionary.h','mask_setup.h','fp_period.h','host_fixture.h']:
        shutil.copyfile(OLD/name,H/name)
    (H/'original').mkdir()
    for name in ['scenario.S','operations.h']:shutil.copyfile(OLD/'original'/name,H/'original'/name)
    original_header=(OLD/'packed_output.h').read_text()
    prefix=original_header.split('/* Volatile scalar reads',1)[0]
    sticky=replace((P/'proposed_comparator.h').read_text(), 'e64m4_sticky_mismatch_proposal(', 'e64m4_packed_mismatch(')
    packed=prefix+sticky+'\n#undef E64M4_OUTPUT_EIGHT\n#undef E64M4_OUTPUT_STORE\n#endif\n'
    emit(H/'packed_output.h',packed)
    emit(H/'comparator.diff',''.join(difflib.unified_diff(original_header.splitlines(True),packed.splitlines(True),fromfile='software01/packed_output.h',tofile='software02/packed_output.h')))
    # Only Host observation instrumentation differs outside the production comparator.
    host=(OLD/'host.c').read_text()
    host=replace(host, '#include "host_case.c"',
        'static void observe_actual(const volatile uint64_t *, uint64_t);\n'
        'static void expected_event(const volatile uint64_t *, uint64_t);\n'
        'static unsigned expected_count, total_expected;\n#include "host_case.c"')
    host=replace(host, 'static void mask_event(unsigned kind, unsigned index, const uint8_t *p) {',
        '#include "host_extra.h"\nstatic void mask_event(unsigned kind, unsigned index, const uint8_t *p) {')
    host=replace(host, 'need(read_count==(calls?66u:0u),"previous complete66 output reads"); read_count=0;',
        'need(read_count==(calls?66u:0u),"previous complete66 output reads"); read_count=0;\n'
        '    need(expected_count==(calls?66u:0u),"previous complete66 expected reads"); expected_count=0;')
    host=replace(host, 'memset(mask,setup_variant==7?0:0xa7,128);monitoring=1;',
        'sticky_load_probes();\n    memset(mask,setup_variant==7?0:0xa7,128);monitoring=1;')
    host=replace(host, 'need(read_count==66 && total_reads==395010,"full66 observed reads per call");',
        'need(read_count==66 && total_reads==395010,"full66 observed reads per call");\n'
        '    need(expected_count==66 && total_expected==395010,"full66 expected reads per call");')
    emit(H/'host.c',host)
    emit(H/'host_delta.diff',''.join(difflib.unified_diff((OLD/'host.c').read_text().splitlines(True),host.splitlines(True))))
    for p in [review, P/'proposed_comparator.h',P/'PROPOSAL.md',OLD/'prepare.py',OLD/'execute_software.py',OLD/'host_packed/fp_period.h',OLD/'host_packed/mask_setup.h']:
        pins[str(p)]=sha(p)
    for p in H.rglob('*'):
        if p.is_file():pins[str(p)]=sha(p)
    save(H/'source_entry.json',dict(status='SOFTWARE02_MATERIALIZED_NO_REFERENCE_NO_DUT',pins=pins,
         scope=read(OLD/'source_entry.json')['scope'],only_firmware_change='approved fixed-block sticky comparator; identifier remapped to existing callsite',
         predecessor=str(OLD),reference=False,DUT=False))
    print('MATERIALIZED_SOFTWARE02_ONCE')


def host_headers(directory):
    for name in ['fp_period.h','mask_setup.h']:
        shutil.copyfile(OLD/'host_packed'/name,directory/name)
    shutil.copyfile(H/'host_extra.h',directory/'host_extra.h')
    packed=(H/'packed_output.h').read_text()
    packed=replace(packed,'    output[(index)] = UINT64_C(0x5b); \\',
        '    if(!skip_fresh(index)){output[(index)] = UINT64_C(0x5b); fresh_event(output+(index),output[(index)]);} \\')
    packed=replace(packed,'    const uint64_t actual = current[(index)]; \\',
        '    const uint64_t actual = current[(index)]; observe_actual(current+(index),actual); \\')
    packed=replace(packed,'    const uint64_t wanted = expected[(index)]; \\',
        '    const uint64_t wanted = expected[(index)]; expected_event(expected+(index),wanted); \\')
    packed=replace(packed,'        E64M4_STICKY_WORD(0);\n        E64M4_STICKY_WORD(1);',
        '        E64M4_STICKY_WORD(0);\n        if(monitoring && setup_variant==13){E64M4_STICKY_WORD(0);}\n        else {E64M4_STICKY_WORD(1);}')
    emit(directory/'packed_output.h',packed)


if __name__=='__main__':
    need(sys.argv[1:] in (['materialize'],['software']), 'Explicit single stage')
    if sys.argv[1]=='materialize':materialize()
    else:
        old.host_headers=host_headers
        old.software()
