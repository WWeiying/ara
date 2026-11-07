#!/usr/bin/env python3
"""Build only: original Output-Tile object plus an exactly anchored phase probe."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from audit import digest, require, verify_pins

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OUT = VERIFY/'verification/out'
NATIVE = OUT/'e2e_output_native_q8_20261106_02'
GQA6 = OUT/'e2e_output_gqa6_build_20261106_01'
AUDIT = OUT/'e2e_output_gqa6_audit_20261106_01/result.json'
WORKER = OUT/'e2e_output_gqa6_vcs_20261106_01/result.json'
Q = 'software/akv/experimental/quantized_kv/'
EXPECTED = {
    NATIVE/'build.json': '42696486791401111b72bb4c6a49ce95af5d687de038e668f19f7581e7889288',
    GQA6/'build.json': '1122f019d880f32eac7830c21a21f4364e9e2a3e3e774b659459e5f38f0bdc3e',
    AUDIT: '3531a68d86d3f776feb4e6dc5e15a8974ce21ed4c03515103356c375b037192e',
    WORKER: '0091308118b39b5782885efe013f0b99f4b5e01d02522e1450d602ad907c1981',
}
SOURCE_SHAS = {
    Q+'output_tile/runtime.c': '9abf059dd273c1818b227a2c5bec2d24d165372b041a6d78136d2548c2fe2ba0',
    Q+'output_tile/online.h': '9433b6af6d3593c9267408586227cc886a01463e7356940d41e852775977dea0',
    Q+'runtime_strided.c': '8631575f5ba5c455540d71a0b4629aa157099bc3da2fab09b89fcdd1b740f088',
    Q+'native.h': 'c9c6edacc3a7f1d605c182cd9cd0e031d416c4038585a8ebb9561c45d159081a',
}


def transforms():
    # Every operation inserts observations; original arithmetic/callback text is
    # retained verbatim. A changed/missing/duplicated anchor is a build failure.
    return [
        (Q+'output_tile/runtime.c', '#include "runtime.h"\n',
         '#include "verification/performance/end_to_end_baseline/output_phase_probe.h"\n#include "runtime.h"\n'),
        (Q+'output_tile/online.h',
         '  akv_quant_online_init(p,output,stride,w);',
         '  const uint64_t phase_init=output_phase_stamp();\n  akv_quant_online_init(p,output,stride,w);\n  output_phase_end(OUTPUT_PHASE_INIT,phase_init);'),
        (Q+'output_tile/online.h',
         '    for (unsigned head=0; head<p->heads;) {',
         '    const uint64_t phase_qk=output_phase_stamp();\n    for (unsigned head=0; head<p->heads;) {'),
        (Q+'output_tile/online.h',
         '      head+=rows;\n    }\n    for (unsigned token=0; token<tokens; ++token) {',
         '      head+=rows;\n    }\n    output_phase_end(OUTPUT_PHASE_QK,phase_qk);\n    const uint64_t phase_coefficients=output_phase_stamp();\n    for (unsigned token=0; token<tokens; ++token) {'),
        (Q+'output_tile/online.h',
         '    const size_t offset=first*view->token_stride;',
         '    output_phase_end(OUTPUT_PHASE_COEFFICIENTS,phase_coefficients);\n    const uint64_t phase_pv=output_phase_stamp();\n    const size_t offset=first*view->token_stride;'),
        (Q+'output_tile/online.h',
         '      return AKV_QUANT_VALUE_FAILED;\n  }\n  akv_quant_online_finish(p,output,stride,w);',
         '      return AKV_QUANT_VALUE_FAILED;\n    output_phase_end(OUTPUT_PHASE_PV,phase_pv);\n  }\n  const uint64_t phase_finish=output_phase_stamp();\n  akv_quant_online_finish(p,output,stride,w);\n  output_phase_end(OUTPUT_PHASE_FINISH,phase_finish);'),
        (Q+'runtime_strided.c',
         '    for (unsigned head = 0; head < selection.group_heads; ++head)',
         '    const uint64_t phase_quantize=output_phase_stamp();\n    for (unsigned head = 0; head < selection.group_heads; ++head)'),
        (Q+'runtime_strided.c',
         '          w->core.query + head * selection.query_quant_row_bytes, selection.dim);',
         '          w->core.query + head * selection.query_quant_row_bytes, selection.dim);\n    output_phase_end(OUTPUT_PHASE_QUANTIZE,phase_quantize);'),
        (Q+'native.h',
         '  c->report->executor_status = c->bindings->execute(c->bindings->executor_context,',
         '  const uint64_t phase_binding=output_phase_stamp();\n  c->report->executor_status = c->bindings->execute(c->bindings->executor_context,'),
        (Q+'native.h',
         '      scores, stride, tokens, 0);',
         '      scores, stride, tokens, 0);\n  output_phase_end(OUTPUT_PHASE_BINDING,phase_binding);'),
    ]


def transform_sources(sources):
    result = dict(sources)
    records = []
    for path, before, after in transforms():
        require(result[path].count(before) == 1, 'Exact unique transform anchor: '+path)
        retained = [line for line in after.splitlines() if not (
            'const uint64_t phase_' in line or 'output_phase_end(' in line or
            line == '#include "verification/performance/end_to_end_baseline/output_phase_probe.h"')]
        require(retained == before.splitlines(), 'Transform must only insert observation lines')
        result[path] = result[path].replace(before, after, 1)
        records.append(dict(path=path, before=before, after=after, occurrences=1))
    return result, records


def remap_input(value, copies, out):
    if value.startswith('-I'):
        directory = Path(value[2:])
        for root, label in ((ROOT,'main'),(VERIFY,'verify')):
            if directory.is_relative_to(root):
                return '-I'+str(out/'inputs'/label/directory.relative_to(root))
    return str(copies.get(value,value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(OUT), 'Fresh sole verification output')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(state='PREPARING', performance_measured=False, target_executed=False,
                  production_changes=False, simulation_count=0, whole_model=False)
    pins, commands = {}, []

    def pin(path, expected=None):
        path = str(Path(path).resolve(strict=True))
        sha = digest(path)
        require(expected is None or sha == expected, 'Identity: '+path)
        require(path not in pins or pins[path] == sha, 'Input drift: '+path)
        pins[path] = sha

    def run(argv, label):
        argv = list(map(str, argv))
        pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv))
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        completed = subprocess.run(argv, cwd=out, capture_output=True, timeout=180)
        (out/(label+'.log')).write_bytes(completed.stdout+completed.stderr)
        require(completed.returncode == 0, label+' failed')
        return completed.stdout.decode()

    try:
        for path, sha in EXPECTED.items(): pin(path, sha)
        native = json.loads((NATIVE/'build.json').read_text())
        prior = json.loads((GQA6/'build.json').read_text())
        require(native['state'] == 'BUILT_NOT_EXECUTED' and native['kind'] == 'q8_0' and
                prior['state'] == 'GQA6_NATIVE_BUILT_NOT_EXECUTED', 'Accepted build recipes')
        known = {}
        for directory, record in ((NATIVE,native),(GQA6,prior)):
            pin(directory/'source-pins.json',record['source_pins_sha256'])
            previous = json.loads((directory/'source-pins.json').read_text())
            verify_pins(previous); verify_pins(record['artifacts'])
            for path, sha in {**previous,**record['artifacts']}.items():
                require(path not in known or known[path] == sha, 'Conflicting prior identity')
                known[path] = sha
            pin(directory/'commands.json',record['artifacts'][str(directory/'commands.json')])
        for path, sha in known.items(): pin(path,sha)
        for name in ('build_output_phase.py','output_phase_main.c','output_phase_probe.h',
                     'check_output_phase.py','test_output_phase.py','audit.py',
                     'check_output_gqa6.py','check_projection_native.py'):
            pin(HERE/name)

        # Snapshot only actual source/dependency inputs, not another worktree or
        # an inherited model/QEMU tree. Reused objects stay pinned in place.
        copies = {}
        for path, sha in known.items():
            source = Path(path)
            if source.suffix not in ('.c','.h','.cpp','.S','.ld'): continue
            for root, label in ((ROOT,'main'),(VERIFY,'verify')):
                if source.is_relative_to(root):
                    target = out/'inputs'/label/source.relative_to(root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read_bytes()); pin(target,sha)
                    copies[path] = target
                    break
        for name in ('output_phase_main.c','output_phase_probe.h'):
            target = out/'inputs/main'/HERE.relative_to(ROOT)/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((HERE/name).read_bytes()); pin(target,pins[str(HERE/name)])
            copies[str(HERE/name)] = target
        probe_copies = {}
        for original, target in copies.items():
            if not target.is_relative_to(out/'inputs/main'): continue
            probe = out/'inputs/probe'/target.relative_to(out/'inputs/main')
            probe.parent.mkdir(parents=True,exist_ok=True)
            probe.write_bytes(target.read_bytes()); pin(probe,digest(target))
            probe_copies[original] = probe
        sources = {}
        for rel, sha in SOURCE_SHAS.items():
            source = ROOT/rel
            require(known.get(str(source)) == sha, 'Transform source is not accepted identity')
            sources[rel] = probe_copies[str(source)].read_text()
        changed, registration = transform_sources(sources)
        for rel, text in changed.items():
            target = probe_copies[str(ROOT/rel)]
            # These copies alone become generated, explicitly registered probe
            # sources. Never update an original source pin to absorb drift.
            del pins[str(target)]
            target.write_text(text); pin(target)
        (out/'transform.json').write_text(json.dumps(dict(
            scope='observation-only exact-anchor clone; no math or approximation changes',
            original_sha256=SOURCE_SHAS, operations=registration,
            generated_sha256={rel:digest(probe_copies[str(ROOT/rel)]) for rel in SOURCE_SHAS}),indent=2)+'\n')
        pin(out/'transform.json')

        def remap(value):
            return remap_input(value,copies,out)

        records = json.loads((NATIVE/'commands.json').read_text())
        recipes = {r['label']:r['argv'] for r in records}
        source_jobs = [
            ('caller',recipes['compile-1'],copies[str(HERE/'output_phase_main.c')],[]),
            ('probe',recipes['compile-17'],probe_copies[str(ROOT/(Q+'output_tile/runtime.c'))],[
                '-Dquant_output_tile_execute=output_phase_execute',
                '-Dquant_output_tile_workspace_bytes=output_phase_workspace_bytes',
                '-Dquant_output_tile_inner_execute=output_phase_inner_execute',
                '-Dquant_output_tile_unused_grouped_execute=output_phase_unused_grouped_execute']),
        ]
        compiled = {}
        for label, recipe, source, defines in source_jobs:
            cmd = [remap(v) for v in recipe]
            if label == 'probe':
                cmd = [v.replace('-I'+str(out/'inputs/main'),'-I'+str(out/'inputs/probe'),1)
                       if v.startswith('-I'+str(out/'inputs/main')) else v for v in cmd]
            cmd[cmd.index('-c')+1] = str(source)
            obj = out/(label+'.o'); cmd[cmd.index('-o')+1] = str(obj)
            cmd[1:1] = defines
            dep = [v for i,v in enumerate(cmd) if i not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
            dependency_text = run([*dep,'-M','-MT','object'],'deps-'+label)
            for name in shlex.split(dependency_text.replace('\\\n',' ').split(':',1)[1]):
                dependency = Path(name).resolve(strict=True)
                require(str(dependency) in pins, 'Unpinned actual dependency: '+str(dependency))
                pin(dependency)
            run(cmd,'compile-'+label); pin(obj); compiled[label] = obj
        records = json.loads((GQA6/'commands.json').read_text())
        link = list(next(r['argv'] for r in records if r['label'] == 'link'))
        objects = [v for v in link if v.endswith('.o')]
        require(len(objects) == 17 and objects.count(str(GQA6/'1.o')) == 1 and
                str(NATIVE/'17.o') in objects, 'Original Output-Tile and common object inventory')
        for obj in objects: pin(obj,known[obj])
        link = [str(compiled['caller']) if v == str(GQA6/'1.o') else remap(v) for v in link]
        link.insert(link.index('-Wl,--gc-sections'),str(compiled['probe']))
        elf = out/'output_phase.elf'
        link[link.index('-o')+1] = str(elf)
        link = ['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        compiler = link[0]
        for name in ('cc1','as','collect2','ld'):
            pin(run([compiler,'-print-prog-name='+name],'tool-'+name).strip())
        for name in ('libm.a','libgcc.a'):
            lib = run([compiler,'-march=rv64gcv_zfh_zvfh','-mabi=lp64d',
                       '-print-file-name='+name],'library-'+name).strip()
            pin(lib,known[str(Path(lib).resolve())])
        run(link,'link'); pin(elf)
        objdump = Path(compiler).with_name('riscv64-unknown-elf-objdump')
        dis = run([objdump,'-d',elf],'disassembly')
        for symbol in ('main','quant_output_tile_execute','output_phase_execute',
                       'qbs_native_execute_command','expf'):
            require('<'+symbol+'>:' in dis,'Missing actual symbol: '+symbol)
        require('<qbs_ref_execute>:' not in dis,'Reference executor in native image')
        readelf = run(['/usr/bin/readelf','-SWl',elf],'elf-sections')
        require('.text' in readelf and 'LOAD' in readelf,'ELF section/program headers')
        verify_pins(pins)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        report.update(state='OUTPUT_PHASE_ELF_BUILT_NOT_EXECUTED', elf=str(elf),elf_sha256=digest(elf),
            source_pins_sha256=digest(out/'source-pins.json'), golden=prior['golden'],
            original_elf=prior['elf'],original_elf_sha256=prior['elf_sha256'],
            reused_objects=16,rebuilt_objects=2,baseline='output_tile_original_object',
            candidate='output_tile_observation_only_clone',heads=6,dim=128,visible=128,
            trials=4,order=[0,1,1,0],commands_per_trial=8,outputs_per_trial=768,
            internal_timestamps_per_probed_call=46, binding_nested_in_qk=True,
            quantitative_phase_interpretation_requires_measured_overhead_at_most=0.05,
            limitations=['coefficients includes expf and recurrence, not expf-only time',
                         'PV includes value decoding and accumulation; logical decode count is not physical',
                         'same-ELF probe perturbation includes extra serialization and code layout',
                         'not production/default integration or whole-model timing'],
            artifacts={str(p):digest(p) for p in out.rglob('*') if p.is_file() and p.name!='build.json'})
    except BaseException as exc:
        report.update(state='FAIL',error=repr(exc))
        raise
    finally:
        (out/'build.json').write_text(json.dumps(report,indent=2)+'\n')
        print(report['state'])


if __name__ == '__main__':
    main()
