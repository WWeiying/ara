#!/usr/bin/env python3
"""Strict context-specific log/build checker. No cross-capture checksum contract."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from context_spec import HERE, ROOT, ORDER, CAPTURE_ROOT, NAMES, expected, sequence, subset, old_build, shared as s

BEGIN = re.compile(r'CONTEXT_THREEWAY_BEGIN trial=([0-5]) variant=(rvv|generic|paired)')
END = re.compile(r'CONTEXT_THREEWAY_END trial=([0-5]) variant=(rvv|generic|paired) executed=1 '
    r'native=([01]) admitted_groups=([02]) outputs=512 cycles=([1-9][0-9]*) '
    r'fcsr=([0-9]+) vcsr=5 checksum=([0-9a-f]{16}) guardbytes=384 errors=0')
SUITE = ('CONTEXT_THREEWAY_SUITE_PASS trials=6 outputs_per_trial=512 within_variant_exact=1 '
         'generic_paired_exact=1 rvv_tolerance_only=1 guards=1 derived_subset=1')


def check_log(text, kv):
    exp = expected(kv)
    records, trials, group, severity = [], [], [], set()
    active = declared = suite = terminal = False
    summary = None
    for line in text.splitlines():
        s.require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b',line,re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            m = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0',line)
            s.require(m is not None and m[1] not in severity,'UVM failure or duplicate summary')
            severity.add(m[1])
        if 'Core Test' in line:
            s.require(line == s.TERMINAL and suite and not terminal,'Malformed/duplicate core success')
            terminal = True
        if ('QBS_PERF' in line or 'AKV_PAIR_' in line) and not line.startswith('Command:'):
            raise ValueError('Unexpected other workload')
        if 'AKV_PERF' in line and not line.startswith('Command:'):
            if line.startswith('[AKV_PERF] '):
                s.require(active and not suite,'Command outside trial')
                variant = ORDER[len(trials)]
                commands = sequence(kv,variant)
                s.require(len(group) < len(commands),'Unexpected RVV AKV work or extra command')
                row = s.numeric_fields(line[len('[AKV_PERF] '):],s.PERF_FIELDS)
                s.check_record(row,commands[len(group)],int(variant == 'paired'),len(records)+1)
                records.append(row)
                group.append(row)
            elif line.startswith('[AKV_PERF_SUMMARY] '):
                s.require(suite and not active and summary is None,'Premature/duplicate raw summary')
                summary = s.numeric_fields(line[len('[AKV_PERF_SUMMARY] '):],s.SUMMARY_FIELDS)
            else:
                raise ValueError('Malformed AKV evidence')
        if 'THREEWAY_' in line:
            begin,end = BEGIN.fullmatch(line),END.fullmatch(line)
            if line == subset(kv):
                s.require(not declared and not active and not trials,'Duplicate subset')
                declared = True
            elif begin:
                i = len(trials)
                s.require(declared and not active and not suite and i < 6 and
                          (int(begin[1]),begin[2]) == (i,ORDER[i]),'Trial order/nesting')
                active,group = True,[]
            elif end:
                i = len(trials)
                s.require(active and (int(end[1]),end[2]) == (i,ORDER[i]),'Wrong trial end')
                variant = ORDER[i]
                s.require(int(end[3]) == int(variant != 'rvv') and int(end[4]) == 2*int(variant == 'paired'), 'Native/admission mismatch')
                s.require(len(group) == len(sequence(kv,variant)), 'Missing commands')
                totals = s.totals(group) if group else dict.fromkeys(s.SUMMARY_FIELDS,0)
                if variant != 'rvv':
                    wanted = dict(exp['per_native_trial'],records=exp[variant]['commands'],
                        v2_logical_column=exp[variant]['logical_columns'],replay_bytes=exp[variant]['replay_bytes'])
                    s.require(all(totals[k] == v for k,v in wanted.items()),'Context work totals')
                s.require(int(end[6]) <= 31 and int(end[5]) >= totals['busy_cycles'],'FRM or impossible cycles')
                trials.append(dict(trial=i,variant=variant,native=int(end[3]),admitted_groups=int(end[4]),
                    cycles=int(end[5]),fcsr=int(end[6]),vcsr=5,checksum=end[7],derived_hardware_totals=totals))
                active = False
            elif line == SUITE:
                s.require(declared and not active and len(trials) == 6 and not suite,'Premature/duplicate suite')
                suite = True
            else:
                raise ValueError('Unknown/malformed or wrong-context program record')
    s.require(declared and suite and terminal and not active and len(records) == exp['commands'] and
              severity == {'UVM_ERROR','UVM_FATAL'},'Incomplete evidence')
    s.require(summary == s.totals(records),'Raw hardware summary mismatch')
    identity = {}
    for variant in ('rvv','generic','paired'):
        values = {(t['checksum'],t['fcsr'],t['vcsr']) for t in trials if t['variant'] == variant}
        s.require(len(values) == 1,'Within-variant repeat mismatch')
        identity[variant] = next(iter(values))
    s.require(identity['generic'] == identity['paired'],'Generic/paired bits or CSR mismatch')
    for field in ('ar','r_beats','q_external_bytes','kv_external_bytes','read_ranges','read_payload_bytes'):
        s.require(len({t['derived_hardware_totals'][field] for t in trials if t['native']}) == 1,'External traffic mismatch')
    sums = {v:sum(t['cycles'] for t in trials if t['variant'] == v) for v in ('rvv','generic','paired')}
    return dict(state='PASS',visible_kv=kv,trials=trials,raw_hardware_summary=summary,sums=sums,
        paired_speedup_vs_generic=sums['generic']/sums['paired'],paired_speedup_vs_ordinary_rvv=sums['rvv']/sums['paired'],
        performance_vs_ordinary_rvv='improved' if sums['paired'] < sums['rvv'] else 'neutral' if sums['paired'] == sums['rvv'] else 'regressed',
        deployment_approved=False, provenance=f'Derived Qwen2.5 KV{kv} heads0,1,6,7; not Qwen3 or original GQA6',
        numerical='All512 original tolerance/finite; own repeats exact; generic/paired exact; RVV may differ. No KV128 checksum comparison.',
        scope='Actual ordinary RVV, not tiled RVV; record sums/max are derived, only final summary hardware-emitted')


def checked_build(build):
    build = build.resolve(strict=True)
    r = s.read_json(build/'build.json')
    kv = r['visible_kv']
    s.require(r.get('schema_version') == 1 and r.get('state') == 'BUILT_NOT_EXECUTED' and
        r.get('execution') == 'NOT_RUN' and r.get('post_pins_match') is True and r.get('expected') == expected(kv) and
        r.get('source_heads') == [0,1,6,7] and r.get('source_kv_heads') == [0,1] and
        r.get('output_capacity') == 2048 and r.get('shared_output_all_paths') is True and
        r.get('linked_abi_and_all_blob_bytes_verified') is True and r.get('tolerance') == dict(atol=.004,rtol=.002), 'Wrong context build')
    receipt = build/'source-pins.json'
    s.require(r['source_pins'] == str(receipt) and s.digest(receipt) == r['source_pins_sha256'],'Source manifest drift')
    pins = s.read_json(receipt)
    s.merge_pins(pins,r['artifact_sha256'])
    s.require(pins.get(r['elf']) == r['elf_sha256'] == s.digest(Path(r['elf'])),'ELF drift')
    capture = (CAPTURE_ROOT/f'kv{kv}').resolve(strict=True)
    s.require(r['capture'] == str(capture),'Wrong context capture root')
    # Revalidate original tensor manifest, mask, metadata and every cropped byte.
    from build_context import validate_capture
    capture_info = validate_capture(capture,kv)
    s.require(r['capture_provenance'] == capture_info['provenance'],'Capture provenance changed')
    s.require(r['scale'] == capture_info['case']['scale'],'Capture scale mismatch')
    for p in capture_info['files']:
        s.require(pins.get(str(p)) == s.digest(p),'Unpinned capture input')
    for name in ('input_a','golden'):
        original = capture/'decode/block'/(NAMES[name]+'.bin')
        crop = build/(name+'.bin')
        old_build.validate_crop(original.read_bytes(),crop.read_bytes())
    proof = s.read_json(build/'data-proof.json')
    s.require(proof['visible_kv'] == kv and proof['args'] == [128,1,4,256,2,0,0,0] and
              proof['flag'] == 1 and proof['params'] == [.004,.002,r['scale'],0.,0.,0.,0.,0.] and
              proof['config_sha256'] == s.digest(build/'config.bin'),'Wrong ABI proof')
    s.merge_pins(pins,s.hashes([receipt,build/'build.json']))
    s.verify_pins(pins)
    return r,pins


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--log',type=Path,required=True)
    p.add_argument('--vector-trace',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    report,pins = checked_build(a.build)
    image,accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',Path(report['simv']))
    s.require(image == report['accepted_image_pins'],'Image drift')
    s.merge_pins(pins,accepted)
    s.merge_pins(pins,s.hashes([a.log.resolve(strict=True),a.vector_trace.resolve(strict=True)]))
    parsed = check_log(a.log.read_text(),report['visible_kv'])
    out = a.output.resolve()
    s.require(not out.is_relative_to(a.build.resolve()),'Do not write inside sealed build')
    out.mkdir(parents=True,exist_ok=False)
    command = [sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
        '--require-axi','--require-axi-write','--log',str(a.log.resolve()),'--vector-trace',str(a.vector_trace.resolve()),
        '--elf',report['elf'],'--simv',report['simv'],'--output',str(out/'uvm_result.json')]
    import os
    env = dict(os.environ,PYTHONPATH=str(ROOT/'verification'),PYTHONDONTWRITEBYTECODE='1')
    with (out/'uvm-check.log').open('x') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=600,check=True)
    s.check_result(out/'uvm_result.json',report['elf_sha256'],image)
    uvm = s.read_json(out/'uvm_result.json')
    s.require(uvm['log_sha256'] == s.digest(a.log) and uvm['vector_trace_sha256'] == s.digest(a.vector_trace),'UVM log/trace identity')
    s.verify_pins(pins)
    s.require(s.hashes(s.image_files(Path(report['simv']))) == image,'Post-check image drift')
    parsed.update(state='NUMERIC_WORK_AND_UVM_CHECKED',post_pins_match=True,
        acceptance='Final worker must additionally verify simulator exit0, bounded cleanup and source inventory before/after execution',
        elf_sha256=report['elf_sha256'],evidence_sha256=s.hashes([a.log,a.vector_trace,out/'uvm_result.json']))
    (out/'pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
    parsed['pins_sha256'] = s.digest(out/'pins.json')
    (out/'result.json').write_text(json.dumps(parsed,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(state=parsed['state'],result=str(out/'result.json'))))


if __name__ == '__main__':
    main()
