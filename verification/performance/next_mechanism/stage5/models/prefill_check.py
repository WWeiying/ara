"""Whole model content plus scoped native-entry TB evidence, never RTL timing."""
import importlib.util
import json
from pathlib import Path
import re
import ast
import hashlib

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BINDING_SHA = '5385247e7032bb09286a53e663efd39666751a3609b45b9bcb4bc58a11f2603b'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def bind_short_prefill(module, out, spec):
    source = Path(module.__file__)
    require(sha(source) == BINDING_SHA, 'Original content checker drift')
    build = OUT/'stage5_libraries_build_20261110_01'
    deps = json.loads((build/'compiler-dependencies.json').read_text())
    root = OUT/'stage5_libraries_prepare_20261110_01/inputs/llama/ggml/src/ggml-cpu'
    common, akv = root/'common.h', root/'arch/riscv/akv.cpp'
    require(sha(common) == deps[str(common)] == 'db7c19747a28c819d18922aa43b91b224df3730e424e6d8a4cf4fd16bfb1db14' and
            sha(akv) == deps[str(akv)] == '656b6e6592316acde7752ea71f953608adf40edc7e4f194e25e6bc061835c0a9',
            'Compiled prefill threshold source drift')
    commands = json.loads((build/'build/compile_commands.json').read_text())
    rows = [r for r in commands if r['file'] == str(akv)]
    require(len(rows) == 1 and 'GGML_FA_TILE_Q' not in rows[0]['command'], 'Threshold override')
    if spec['id'] != 'smol_f16':
        return
    require((spec['prompt_tokens'], spec['head_dim'], spec['cache_k'], spec['cache_v'],
             spec['layers'], spec['kv_heads'], spec['q_heads']) == (63, 64, 'f16', 'f16', 30, 3, 9),
            'Correction applies only to the fixed Smol short-prefill shape')
    tree = ast.parse(source.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'counter_delta')
    before = ast.parse("spec['head_dim'] == 256", mode='eval').body
    after = ast.parse("spec['head_dim'] == 256 or (spec['id'] == 'smol_f16' and step == 0 and spec['prompt_tokens'] == 63)", mode='eval').body
    class Change(ast.NodeTransformer):
        count = 0
        def visit_Compare(self, node):
            if ast.dump(node) == ast.dump(before):
                self.count += 1
                return ast.copy_location(after, node)
            return self.generic_visit(node)
    change = Change(); function = change.visit(function)
    require(change.count == 1, 'Counter predicate identity changed')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                 str(Path(__file__)), 'exec'), module.__dict__)
    # The source branch and the actual fallback reason must agree in each child.
    counts = [0, 0]; mode = step = None
    with (out/'guest.log').open() as stream:
        for line in stream:
            if line.startswith('STAGE5_STEP_BEGIN '):
                fields = dict(w.split('=', 1) for w in line.split()[1:])
                mode, step = int(fields['requested']), int(fields['step'])
            elif line.startswith('STAGE5_STEP_END '):
                mode = step = None
            elif line.startswith('GGML_RISCV_AKV_FALLBACK '):
                require(step == 0 and mode in (0, 1) and
                        line.strip() == 'GGML_RISCV_AKV_FALLBACK mode=prefill reason=size portable=0',
                        'Unexpected fallback outside exact short-prefill size branch')
                counts[mode] += 1
    require(counts == [30, 30], 'Missing/extra short-prefill fallback records')


def require(ok, message):
    if not ok: raise ValueError(message)


def native_entries(lines, symbols):
    mode = step = None; active = False; ended = False
    previous = None
    counts = {(m,s):dict(qbs=0,pv_prepare=0) for m in (0,1) for s in range(3)}
    stopped = {(m,s):dict(qbs=0,pv_prepare=0) for m in (0,1) for s in range(3)}
    starts = {symbols['qbs_native_execute_command'][0]:'qbs',
              symbols['akv_experimental_resident_pv_prepare'][0]:'pv_prepare'}
    for line in lines:
        last, previous = previous, None
        if line.startswith('Stopped execution of TB chain before '):
            match = re.fullmatch(r'Stopped execution of TB chain before ((?:0x)?[0-9a-f]+) \[([0-9a-f]+)\] .*', line.rstrip('\r\n'))
            require(match is not None and last is not None and
                    (match[1], int(match[2], 16)) == last[:2], 'Unpaired/mismatched stopped TB')
            pc, key = last[1], last[2]
            if pc in starts:
                counts[key][starts[pc]] -= 1
                stopped[key][starts[pc]] += 1
            continue
        if line.startswith('STAGE5_STEP_BEGIN '):
            f=dict(word.split('=',1) for word in line.split()[1:]); mode=int(f['requested']); step=int(f['step'])
            require((mode,step) in counts,'Unknown model phase'); active=False
        elif line.startswith('BIND_COUNTER '):
            f=dict(word.split('=',1) for word in line.split()[1:]); active=f['when']=='before'
        elif line.startswith('STAGE5_STEP_END '): mode=step=None
        elif line.startswith('STAGE5_NUMERICAL_PAIR_ONLY '): ended=True
        elif line.startswith('Trace '):
            match=re.fullmatch(r'Trace 0: (?:0x)?[0-9a-f]+ \[[0-9a-f]+/([0-9a-f]+)/[0-9a-f]+/[0-9a-f]+\].*',line.rstrip())
            require(match is not None,'Malformed/wrong-hart TB trace')
            pc=int(match[1],16)
            require(any(a<=pc<b for n,(a,b) in symbols.items() if n in
                ('qbs_native_execute_command','akv_experimental_resident_pv_prepare')), 'Unfiltered native TB')
            require(active and not ended and (mode,step) in counts,'Native entry outside decode snapshot')
            if pc in starts: counts[(mode,step)][starts[pc]]+=1
            pointer = re.match(r'Trace 0: ((?:0x)?[0-9a-f]+)', line)[1]
            previous = (pointer, pc, (mode,step))
    native_entries.stopped = stopped
    return counts


def check(directory):
    out=Path(directory)
    cpu = OUT/'stage5_qemu_prepare_variant_20261110_04/qemu-10.2.0/accel/tcg/cpu-exec.c'
    require(sha(cpu) == '96c9c88df8d0a7b432993f250784e635c810ac1de5552529eae0eb6e1e6886a7',
            'QEMU pre-execution trace/explicit stop semantics source drift')
    spec=json.loads((out/'spec.json').read_text()); pcs=json.loads((out/'pcs.json').read_text())
    symbols=json.loads((out/'symbols.json').read_text())
    module_spec=importlib.util.spec_from_file_location('frozen_model_content_check',out/'inputs/binding_check.py')
    m=importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(m)
    bind_short_prefill(m, out, spec)
    with (out/'guest.log').open() as stream: result=m.check_lines(stream,spec,pcs)
    with (out/'guest.log').open() as stream: entries=native_entries(stream,symbols)
    with (out/'guest.log').open() as stream: exits=[line.strip() for line in stream if line.startswith('GUEST_TEST_EXIT=')]
    require(exits==['GUEST_TEST_EXIT=0'],'Missing/failed/duplicate Linux child exit')
    for phase in result['phases']:
        key=(phase['requested'],phase['step'])
        require(entries[key]['qbs']>0,'No actual QBS native entry for model phase')
        require(entries[key]['pv_prepare']==phase['architectural'].get('pv',0),'PV preparation entry count differs')
    expected=sum(row['native_qbexec'] for row in result['qbs'].values())
    require(all(sum(entries[(mode,s)]['qbs'] for s in range(3))==expected for mode in (0,1)),
            'QBS native-entry hits differ from complete command summaries')
    result.update(native_entry_tb_hits=[dict(requested=k[0],step=k[1],**v) for k,v in entries.items()],
                  explicitly_not_executed_tb_hits=[dict(requested=k[0],step=k[1],**v)
                      for k,v in native_entries.stopped.items()],
                  qemu_tb_semantics_source_sha256=sha(cpu),
                  linux_child_exit_checked=True,scoped_native_entry_hits_checked=True,
                  instruction_retirement_claim=False,rtl_or_model_speed_claim=False)
    return result


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--execution', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); out = args.execution.resolve(); dest = args.output.resolve()
    require(dest.parent == OUT and not dest.exists(), 'Fresh direct audit output required')
    dest.mkdir()
    report = dict(state='FAIL', original_worker_state='FAIL', model_reexecuted=False)
    try:
        original = json.loads((out/'result.json').read_text())
        require(original['state'] == 'FAIL' and original['model_executed'] is True and
                original['error'] == "ValueError('Wrong route, all-fallback positive, or extra work')",
                'Audit is not a relabeling of the original worker')
        evidence = {str(p): sha(p) for p in (out/'guest.log', out/'result.json', Path(__file__))}
        proof = check(out)
        pins = json.loads((out/'source-pins.json').read_text())
        for path, digest in pins.items():
            require(sha(path) == digest, 'Original pin drift: ' + path)
        require(all(sha(path) == digest for path, digest in evidence.items()), 'Audit evidence drift')
        with (dest/'checked.json').open('x') as stream:
            json.dump(proof, stream, indent=2, sort_keys=True)
        report.update(state='SCOPED_MODEL_SHORT_PREFILL_AUDIT_PASS', original_failure_preserved=True,
                      all_original_pins_match=True, pins=len(pins), evidence=evidence,
                      original_source_pins_sha256=sha(out/'source-pins.json'),
                      checked_sha256=sha(dest/'checked.json'), execution=str(out),
                      excluded_expectation='Smol F16 63-query prefill legacy_completed; source threshold is 64')
    except BaseException as exc:
        report['error'] = repr(exc)
    with (dest/'result.json').open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
    print(json.dumps(report, sort_keys=True), flush=True)
    raise SystemExit(report['state'] != 'SCOPED_MODEL_SHORT_PREFILL_AUDIT_PASS')
