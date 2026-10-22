"""RVH0 PTW output constants only; local native capture, never global application."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from types import FunctionType, SimpleNamespace
import xml.etree.ElementTree as ET

import soc_constants61_native as soc
import soc_constants61_native_v2 as aliases

life, need, frozen, primitive = soc.life, soc.need, soc.frozen, soc.primitive
HERE = Path(__file__).resolve().parent
TCL = HERE / 'ptw_rvh0_outputs156_local.tcl'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_ptw'
BASE = life.OUT / 'itlb-ppn-aba-offline-admitted794-parent-20261008-01'
BASE_SHA = '02ee7424a6b21d8073097d8a6389be4393d76fc7a3ab31ce410f1c24f70de8cf'
REPORT = life.OUT / 'current-population794-soc61-parent-20261008-01'
REPORT_SHA = 'fce23ff83487b83e51c069863710f4fad0c11716070ed3d4327aa57470972007'
BOOK = life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
SCHEMA = 'PTW_RVH0_OUTPUTS156_LOCAL_V1'
ANNOTATION = 'RVH0 direct combinational g_content and VMID zero outputs only; unknown internal H state protected'
WIDTHS = {'shared_tlb_update_o.g_content.' + n: w for n, w in
          [('v', 1), ('r', 1), ('w', 1), ('x', 1), ('u', 1), ('g', 1),
           ('a', 1), ('d', 1), ('rsw', 2), ('ppn', 44), ('reserved', 10)]}
WIDTHS['shared_tlb_update_o.vmid'] = 14
STAGES = frozen.STAGES


def source_guard(texts):
    def exact(file, pattern):
        need(re.search(pattern, texts[file], re.S) is not None, 'Source proof: ' + file)
    exact('cv64a6_imafdcv_sv39_config_pkg.sv', r'CVA6ConfigHExtEn\s*=\s*0;')
    exact('cv64a6_imafdcv_sv39_config_pkg.sv', r"RVH:\s*bit'\(CVA6ConfigHExtEn\)")
    exact('cv64a6_imafdcv_sv39_config_pkg.sv', r'CVA6ConfigXlen\s*=\s*64;')
    exact('cv64a6_imafdcv_sv39_config_pkg.sv', r"XLEN:\s*unsigned'\(CVA6ConfigXlen\)")
    exact('build_config_pkg.sv', r'cfg.RVH\s*=\s*CVA6Cfg.RVH;')
    exact('build_config_pkg.sv', r'cfg.VMID_WIDTH\s*=\s*\(CVA6Cfg.XLEN == 64\)\s*\?\s*14\s*:\s*1;')
    exact('build_config_pkg.sv', r'cfg.PPNW\s*=\s*\(CVA6Cfg.XLEN == 32\)\s*\?\s*22\s*:\s*44;')
    fn = texts['ara_soc.sv'].split('function automatic config_pkg::cva6_user_cfg_t gen_usr_cva6_config', 1)[1].split('endfunction', 1)[0]
    need(not re.search(r'cfg\.(RVH|XLEN)\s*=', fn), 'SoC config override forbidden')
    exact('ara_soc.sv', r'CVA6AraConfig_user\s*=\s*gen_usr_cva6_config\(cva6_config_pkg::cva6_cfg\)')
    exact('ara_soc.sv', r'CVA6AraConfig\s*=\s*build_config_pkg::build_config\(CVA6AraConfig_user\)')
    exact('ara_soc.sv', r'\.CVA6Cfg\s*\(CVA6AraConfig\s*\)')
    exact('ara_system.sv', r'\.CVA6Cfg\(CVA6Cfg\)')
    for file in ('cva6.sv', 'ex_stage.sv', 'load_store_unit.sv', 'cva6_mmu.sv'):
        exact(file, r'\.CVA6Cfg\s*\(CVA6Cfg\)')
    ptw = re.sub(r'//[^\n]*|/\*.*?\*/', '', texts['cva6_ptw.sv'], flags=re.S)
    for name, expected in [('g_content', ['pte', "'0"]),
                           ('vmid', ["CVA6Cfg.RVH ? tlb_update_vmid_q : '0"])]:
        writes = re.findall(r'shared_tlb_update_o\.' + name + r'\s*=\s*([^;]+);', ptw)
        need([' '.join(x.split()) for x in writes] == expected, 'Exact complete writer set: ' + name)
        need(not re.search(r'shared_tlb_update_o\s*(?:<=|=)', ptw), 'Whole output override forbidden')
        need(not re.search(r'shared_tlb_update_o\.' + name + r'(?:\.|\[)[^;]*?(?:<=|=(?!=))', ptw),
             'Partial output override forbidden')
    exact('cva6_ptw.sv', r"if \(\(enable_g_translation_i \|\| en_ld_st_g_translation_i\) && CVA6Cfg.RVH\) begin\s*shared_tlb_update_o.content\s*=.*?;\s*shared_tlb_update_o.g_content = pte;\s*end else begin\s*shared_tlb_update_o.content\s*=.*?;\s*shared_tlb_update_o.g_content = '0;\s*end")
    mmu = re.sub(r'//[^\n]*|/\*.*?\*/', '', texts['cva6_mmu.sv'], flags=re.S)
    need(re.search(r'logic \[9:0\] reserved;\s*logic \[CVA6Cfg.PPNW-1:0\] ppn;\s*logic \[1:0\] rsw;\s*logic d;\s*logic a;\s*logic g;\s*logic u;\s*logic x;\s*logic w;\s*logic r;\s*logic v;', mmu), 'Exact PTE type')


def collision_gate(text):
    others, masks = soc.source.native.semantic(text)
    for scope, checksum, metric, directive in others:
        need(not (directive == 'WHOLE_SCOPE' and (SCOPE == scope or SCOPE.startswith(scope + '.'))),
             'Existing whole-scope ownership')
    for scope, checksum, name, kind, dims, pos, value in masks:
        if scope == SCOPE:
            need(not any(name == n or n.startswith(name + '.') or name.startswith(n + '.') for n in WIDTHS),
                 'Existing parent/field/partial ownership')


def evidence():
    pins = {}
    def read(p, sha):
        need(life.digest(p) == sha, 'Frozen input drift: ' + str(p))
        pins[str(p)] = sha
        return p.read_bytes()
    book = json.loads(read(BOOK, BOOK_SHA))
    paths = ['hardware/src/ara_soc.sv', 'hardware/src/ara_system.sv']
    paths += ['hardware/deps/cva6/core/' + s for s in
              ['cva6.sv', 'ex_stage.sv', 'load_store_unit.sv', 'cva6_mmu/cva6_ptw.sv', 'cva6_mmu/cva6_mmu.sv',
               'include/build_config_pkg.sv', 'include/cv64a6_imafdcv_sv39_config_pkg.sv']]
    texts = {Path(p).name: read(life.ROOT / p, book[str(life.ROOT / p)]).decode() for p in paths}
    source_guard(texts)
    admission = json.loads(read(BASE / 'admission-manifest.json', BASE_SHA))
    need(admission['coverage_admitted'] is True, 'Formal794 admitted baseline')
    authority = life.merge_pins(admission['input_pins'], admission['output_pins'])
    raw = json.loads(read(BASE / 'combined-toggle-bits.json', authority[str(BASE / 'combined-toggle-bits.json')]))
    q = json.loads(read(REPORT / 'qualification.json', REPORT_SHA))
    el = REPORT / 'applied.el'
    collision_gate(read(el, q['output_pins'][str(el)]).decode())
    db = Path(str(life.IMAGE) + '.vdb') / 'snps/coverage/db'
    trees = []
    for rel in ('design/verilog.design.xml', 'shape/tgl.verilog.info.xml', 'shape/tgl.verilog.shape.xml'):
        p = db / rel
        read(p, authority[str(p)])
        trees.append(soc.source.t.xml(p))
    checks, defs = soc.source.t.definitions(*trees, [SCOPE])
    d = defs[SCOPE]
    need(d['module']['name'] == 'cva6_ptw' and d['module']['chksum'] == '4218964517'
         and checks[SCOPE] == raw[SCOPE]['checksum'] == '313685876', 'Exact native compiled PTW identity')
    nodes = [dict(kind=n.tag, **n.attrib) for n in ET.fromstring(d['shape']).find('tglshape')]
    typed, arrays = soc.source.typed.typed_nodes(d['shape'], raw[SCOPE])
    signals = []
    for n in nodes:
        if n['name'] not in WIDTHS:
            continue
        w = WIDTHS[n['name']]
        need(n['type'] == '1' and n['portnode'] == '3' and n['excluded'] == '0'
             and (n['kind'] == 'node' if w == 1 else n['kind'] == 'vectornode'
                  and n['left'] == str(w - 1) and n['right'] == '0'), 'Exact compiled output geometry')
        v = next(x for x in typed if x['name'] == n['name'])
        need(v['logical_width'] == w and v['missing_slots'] == 2 * w, 'All serialized target slots remain missing')
        signals.append(dict(name=n['name'], left=w-1, right=0, kind=n['kind'],
                            missing_coordinates=v['missing_coordinates']))
    need(len(nodes) == 149 and len(signals) == 12 and {s['name'] for s in signals} == set(WIDTHS),
         'Full PTW149 / exact12 fields')
    life.check(pins)
    return dict(status='SOURCE_PROVEN_RVH0_OUTPUTS156_NOT_NATIVE_QUALIFIED', population=794,
                pins=pins, instance=dict(scope=SCOPE, design_module_checksum=d['module']['chksum'],
                toggle_checksum=checks[SCOPE], signals=signals, typed_objects=nodes),
                fields=12, bits=78, directions=156, protected_objects=137,
                writer_proof={'g_content': 'RVH0 makes guarded nonzero branch false; else writes whole PTE zero',
                              'vmid': 'RVH0 constant ternary selects zero, independent of unreset VMID register'},
                X_boundary='Combinational output constant after settling, not startup/delta X suppression',
                MDA_HOLD=arrays, unknown_internal_H_state_protected=True,
                EDA_started=False, population_application=False)


def labels(i):
    return [s['name'] if s['kind'] == 'node' else s['name'] + '[%d:%d]' % (s['left'], s['right']) for s in i['signals']]


def candidate(ii):
    i, = ii
    lines = ['CHECKSUM: "%s %s"' % (i['design_module_checksum'], i['toggle_checksum']),
             'INSTANCE: ' + i['scope'], 'ANNOTATION: "' + ANNOTATION + '"']
    for s, label in zip(i['signals'], labels(i)):
        lines.append('Toggle %s "logic %s"' % (s['name'], label))
    return '\n'.join(lines) + '\n'


def el_gate(text, c):
    i, = c['instances']
    targets = {s['name']: s for s in i['signals']}
    actual = {}; checksum = scope = annotation = False
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith('CHECKSUM:'):
            need(not checksum and line == 'CHECKSUM: "%s %s"' %
                 (i['design_module_checksum'], i['toggle_checksum']), 'Exact unique checksum')
            checksum = True
        elif line.startswith('INSTANCE:'):
            need(checksum and not scope and line == 'INSTANCE: ' + i['scope'], 'Exact unique scope')
            scope = True
        elif line.startswith('ANNOTATION:'):
            need(scope and not annotation and line == 'ANNOTATION: "' + ANNOTATION + '"', 'Exact annotation')
            annotation = True
        else:
            m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+) "logic ([^"\n]+)"', line)
            need(annotation and m is not None, 'Only complete typed Toggle directives')
            direction, name, signature = m.groups()
            need(name in targets, 'No protected/internal/parent field')
            s = targets[name]
            expected = name if s['kind'] == 'node' else name + '[%d:%d]' % (s['left'], s['right'])
            need(signature == expected, 'Exact scalar/vector declaration')
            ds = {direction} if direction else {'0to1', '1to0'}
            need(not actual.get(name, set()) & ds, 'Duplicate physical direction')
            actual.setdefault(name, set()).update(ds)
    need(set(actual) == set(WIDTHS) and all(ds == {'0to1', '1to0'} for ds in actual.values()),
         'Exact156 paired directions, no missing fields')
    return sorted(actual)


def bind(i, text):
    # Existing complete typed binder, with precisely the SOC protected singleton alias.
    indexed = SimpleNamespace(**dict(vars(primitive.indexed), Resolver=aliases.Resolver))
    p = SimpleNamespace(**dict(vars(primitive), indexed=indexed))
    fn = frozen.bind
    return FunctionType(fn.__code__, dict(fn.__globals__, primitive=p, labels=labels))(i, text)


def before_gate(out, c):
    return [bind(i, (out / ('native_before_%d.tsv' % n)).read_text()) for n, i in enumerate(c['instances'])]


def selection(c):
    text = ''.join('set mq_%s {%s}\n' % (k, c[k]) for k in ('design', 'vdb', 'test'))
    text += 'set mq_instances [list [list {%s} [list %s]]]\n' % (SCOPE, ' '.join('{%s}' % x for x in labels(c['instances'][0])))
    return text + 'set tied_python {%s}\nset tied_helper {%s}\nset tied_seal $env(TIED90_CONFIG_SEAL)\n' % (sys.executable, Path(__file__).resolve())


def host_hook(c, text, el):
    fn = soc.host_hook
    return FunctionType(fn.__code__, dict(fn.__globals__, TCL=TCL, labels=labels, bind=bind,
                        before_gate=before_gate, el_gate=el_gate))(c, text, el)


def prepare(out):
    need(out.parent == life.OUT and not out.exists(), 'Fresh local output only')
    proof = evidence()
    template = life.read_bound(primitive.old.RUN / 'config.json', primitive.old.SEAL)
    pins = life.merge_pins(proof['pins'], template['pins'])
    pins[str(primitive.old.RUN / 'config.json')] = primitive.old.SEAL
    for m in list(sys.modules.values()):
        p = getattr(m, '__file__', None)
        if p and Path(p).resolve().parent == HERE:
            pins[str(Path(p).resolve())] = life.digest(p)
    pins.update(frozen.tcl_pins(TCL))
    p = HERE / 'test_ptw_rvh0_outputs156_local.py'
    pins[str(p)] = life.digest(p)
    c = dict(schema=SCHEMA, output=str(out), population_application=False, automatic_retry=False,
             timeout_seconds=900, instances=[proof['instance']], fields=12, directions=156,
             protected_objects=137, pins=pins, **{k: template[k] for k in ('identity', 'design', 'vdb', 'test')})
    el = candidate(c['instances']); el_gate(el, c)
    text = selection(c); host = host_hook(c, text, el)
    life.check(pins)
    out.mkdir()
    for name, value in [('source-proof.json', proof), ('host-evidence.json', host)]:
        life.save(out / name, value); pins[str(out / name)] = life.digest(out / name)
    for name, data in [('candidate.el', el), ('selection.tcl', text), ('native-bind.tcl', TCL.read_text())]:
        with (out / name).open('x') as f: f.write(data)
        pins[str(out / name)] = life.digest(out / name)
        if name.endswith('.tcl'): primitive.check_generated_tcl.check(out / name)
    life.save(out / 'config.json', c)
    return dict(output=str(out), seal=life.digest(out / 'config.json'), EDA_started=False)


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal); life.check(c['pins'])
    need(c['schema'] == SCHEMA and c['output'] == str(out) and c['timeout_seconds'] == 900
         and c['population_application'] is False and c['automatic_retry'] is False
         and (c['fields'], c['directions'], c['protected_objects']) == (12, 156, 137), 'Closed local config')
    need(c['instances'] == [evidence()['instance']], 'Exact source/compiled full complement')
    primitive.old.frozen.tools.revalidate(c['identity'])
    for p, sha in frozen.tcl_pins(TCL).items(): need(c['pins'].get(p) == sha, 'Sourced Tcl pin')
    el_gate((out / 'candidate.el').read_text(), c)
    return c


def command(c, out):
    return [c['identity']['roles']['xvfb_run'], '-a', '-e', str(out/'xvfb.log'),
            '-s', '-screen 0 1280x1024x24', c['identity']['roles']['launcher'],
            '-full64', '-cov', '-script', str(out/'native-bind.tcl')]


def terminal_gate(c, seal, out, t, live, execution):
    need(type(t['returncode']) is int and t['returncode'] == 0 and t['timeout'] is False,
         'Real terminal0, never timeout or boolean substitute')
    primitive.terminal_gate(t, c, live)
    need(type(live[0]['pid']) is int and live[0]['pid'] > 0, 'Actual native PID')
    need(execution['config_seal'] == seal and execution['cwd'] == str(out)
         and execution['timeout_seconds'] == 900 and execution['command'] == command(c, out),
         'Exact complete native launch roles/arguments/config')


def verify(out, seal):
    c = check(out, seal)
    need(not (out / 'error.txt').exists(), 'Recorded GUI failure')
    t = json.loads((out / 'terminal.json').read_text()); live = json.loads((out / 'live-identity.json').read_text())
    e = json.loads((out / 'execution.json').read_text())
    terminal_gate(c, seal, out, t, live, e)
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('PTW_RVH0_OUTPUTS156_FIVE_PHASE_DONE') == 1
         and not any(x.startswith('PTW_RVH0_OUTPUTS156_FAILED') for x in log.splitlines()), 'Actual five stages complete')
    ref = before_gate(out, c)
    for stage in STAGES:
        soc.stage_gate(c['instances'][0], ref[0], bind(c['instances'][0],
                       (out / ('native_%s_0.tsv' % stage)).read_text()), stage)
    need(el_gate((out / 'first.el').read_text(), c) == el_gate((out / 'second.el').read_text(), c), 'Exact native reload')
    for n in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        need((out / n).read_bytes() == b'', 'Full empty EL reset')
    files = ['config.json', 'execution.json', 'terminal.json', 'live-identity.json', 'first.el', 'second.el',
             'initial-empty.el', 'reset-empty.el', 'final-empty.el', 'launcher.log', 'DVEfiles/dve_gui.log']
    files += ['native_%s_0.tsv' % s for s in STAGES]
    result = dict(status='PTW_RVH0_OUTPUTS156_LOCAL_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED',
                  config_seal=seal, fields=12, directions=156, protected_objects=137,
                  native_bit_direction_order_inferred=False, X_MDA_internal_H_waived=False,
                  population_application=False, pins=life.merge_pins(c['pins'], {str(out/n): life.digest(out/n) for n in files}))
    life.check(result['pins']); p = out / 'capture-result.json'
    if p.exists(): need(json.loads(p.read_text()) == result, 'Existing qualification differs')
    else: life.save(p, result)
    return result


def run(out, seal, reviewed):
    need(seal and reviewed == seal, 'Exact parent-reviewed seal required')
    c = check(out, seal); need(not (out / 'execution.json').exists(), 'No retries')
    paths = os.environ.get('PYTHONPATH', '').split(os.pathsep)
    need(paths and all(p and Path(p).is_absolute() and Path(p).is_dir() for p in paths), 'Absolute child PYTHONPATH required')
    env = primitive.old.frozen.tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None); env.update(DVE_COVERAGE_OUTPUT=str(out), TIED90_CONFIG_SEAL=seal)
    xvfb = shutil.which('xvfb-run')
    need(xvfb == c['identity']['roles']['xvfb_run'], 'Sealed xvfb role')
    cmd = command(c, out)
    life.save(out/'execution.json', dict(command=cmd, cwd=str(out), config_seal=seal, timeout_seconds=900))
    with (out/'launcher.log').open('x') as log:
        proc = subprocess.Popen(cmd, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(10); live = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit(): continue
            try:
                if (p/'exe').resolve() == Path(c['identity']['executable']) and (p/'cwd').resolve() == out:
                    live.append(dict(pid=int(p.name), exe=str((p/'exe').resolve()), cwd=str(out)))
            except OSError: pass
        life.save(out/'live-identity.json', live); print(json.dumps(live), flush=True)
        timeout = False
        try: proc.wait(timeout=890)
        except subprocess.TimeoutExpired:
            timeout = True; os.killpg(proc.pid, signal.SIGTERM)
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(proc.pid, signal.SIGKILL); proc.wait()
    life.save(out/'terminal.json', dict(returncode=proc.returncode, timeout=timeout, actual_dve=live))
    return verify(out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'before', 'first', 'second', 'verify', 'run'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seal'); p.add_argument('--parent-reviewed-seal')
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare': print(json.dumps(prepare(out)), flush=True)
    elif a.mode == 'run': print(json.dumps(run(out, a.seal, a.parent_reviewed_seal)))
    else:
        c = check(out, a.seal)
        if a.mode == 'before': before_gate(out, c)
        elif a.mode in ('first', 'second'): el_gate((out/(a.mode+'.el')).read_text(), c)
        elif a.mode == 'verify': verify(out, a.seal)
        print(a.mode + '_PASS')
