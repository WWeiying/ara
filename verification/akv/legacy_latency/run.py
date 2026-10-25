#!/usr/bin/env python3
"""Prepare only by default; explicit reviewed-manifest execution runs two units.

No SoC, model, PPA or production-promotion acceptance is inferred.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INTEGRATION = HERE.parent/'shared_reader_integration'
sys.path.insert(0, str(INTEGRATION))
import prepare_storage as storage
import compose_canonical_standalone as composer
import run_canonical_standalone as tools
sys.path.insert(0, str(HERE))
# Do not import a generic cached check.py from another fixture.
spec = importlib.util.spec_from_file_location('legacy_latency_checker', HERE/'check.py')
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)

SCHEMA = 'akv_legacy_latency_pair_v1'
MODULES = ('hardware/src/vlsu/qbs/qbs_engine.sv', 'hardware/src/vlsu/akv/akv_engine.sv',
           'hardware/src/vlsu/vlsu.sv')
BENCH = ROOT/'verification/akv/akv_engine_tb.sv'
TLB_RELATIVE = 'source/hardware/deps/cva6/core/cva6_mmu/cva6_shared_tlb.sv'
TLB_SHA256 = '2e46b236d59f27fb23e5e073daaa665a4a3ca5fb22d8a17a867e6504b575576a'
WARNING_PRIOR = ROOT/'verification/out/shared-storage-standalone-akv-20261025-01'
WARNING_PINS = {
    str(WARNING_PRIOR/'compile.log'): '3b1d2e27a19e480a1694593fabd29ab19292a1e09e18542344c39b01f9bea39d',
    str(WARNING_PRIOR/'result.json'): '8706f74d63c4ab5c2dc26602f8d63a4f9eab878b34c1e8d0d573eb89483a81a0',
}


def admitted_warning(source):
    return ("Warning-[IPDW] Identifier previously declared\n"
            f"{source}, 458\n"
            "  Second declaration for identifier 'i' ignored\n"
            "  Identifier 'i' previously declared as genvar. \n"
            f"  [{source},\n  168]\n")


def check_compile(log, code, source):
    checker.require(tools.digest(source) == TLB_SHA256, 'Admitted TLB source drift')
    warning = admitted_warning(source)
    checker.require(log.count(warning) == 1 and '\n'+warning+'\n' in log,
                    'Expected exactly one inherited TLB genvar diagnostic')
    remaining = log.replace(warning, '', 1)
    checker.require(code == 0 and not re.search(
        r'Error-|Error:|Fatal:|\b(?:IPDW|PCWM|PINMISSING)\b', remaining),
        'Compilation or port-width contract failure')
    return dict(code='IPDW', source=str(source), source_sha256=TLB_SHA256,
                identifier='i', previous_line=168, redeclaration_line=458, count=1)


def paired_lists(text, mapping):
    checker.require(len(mapping) == 3 and len(set(mapping.values())) == 3, 'Need exactly three module mappings')
    lines = text.splitlines(keepends=True)
    for before, after in mapping.items():
        checker.require(sum(line.strip() == before for line in lines) == 1 and
                        all(line.strip() != after for line in lines), 'Missing/duplicate/aliased overlay module')
    result = []
    for line in lines:
        token = line.strip()
        if token in mapping:
            result.append(line.replace(token, mapping[token], 1))
        else:
            result.append(line)
    baseline = ''.join(result)
    inverse = {v:k for k,v in mapping.items()}
    restored = ''.join(line.replace(line.strip(), inverse[line.strip()], 1)
                       if line.strip() in inverse else line for line in baseline.splitlines(keepends=True))
    checker.require(restored == text, 'Non-module filelist drift')
    return baseline, text


def graph_pins(filelist, extras, source_root):
    sources = []
    cleaned = []
    for line in filelist.read_text().splitlines():
        token = line.strip()
        if not token or token.startswith(('//','#')):
            continue
        if token.startswith('+define+'):
            definitions = token[len('+define+'):].split('+')
            checker.require(all(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:=\S+)?', d) and
                                d.split('=',1)[0] != 'SYNTHESIS' for d in definitions), 'Unsupported define')
        elif token.startswith('+incdir+'):
            value = token[len('+incdir+'):]
            checker.require('+' not in value and Path(value).is_absolute() and Path(value).is_dir(), 'Include grammar')
        else:
            path = Path(token)
            checker.require(path.is_absolute() and path.suffix in ('.sv','.v') and path.is_file(), 'Source grammar')
            sources.append(path.resolve())
        cleaned.append(line)
    tools.admitted_repeats(source_root, sources)
    # Match the accepted inventory utility's comment normalization only.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='legacy-latency-inventory-') as directory:
        normalized = Path(directory)/'sources.f'
        normalized.write_text('\n'.join(cleaned)+'\n')
        pins = {row['path']:row['sha256'] for row in tools.collect(normalized, source_root, extras)}
        pins.pop(str(normalized))
    pins[str(filelist)] = tools.digest(filelist)
    for source in sources:
        for path in source.parent.iterdir():
            if path.is_file() and path.suffix.lower() in ('.h','.hpp','.vh','.svh'):
                pins[str(path.resolve())] = tools.digest(path)
    return pins


def prepare(snapshot, out):
    checker.require(not out.is_relative_to(snapshot) and not snapshot.is_relative_to(out), 'Independent output required')
    report = storage.validate_snapshot(snapshot)
    tools.verify(WARNING_PINS)
    prior = json.loads((WARNING_PRIOR/'result.json').read_text())
    checker.require(prior['state'] == 'PASS' and prior['evidence'][str(WARNING_PRIOR/'compile.log')]
                    == WARNING_PINS[str(WARNING_PRIOR/'compile.log')], 'Warning provenance not accepted')
    warning_admission = check_compile((WARNING_PRIOR/'compile.log').read_text(), 0,
                                     snapshot/TLB_RELATIVE)
    entry, _ = composer.contract('akv')
    checker.require(tools.digest(BENCH) == entry['tb_sha256'], 'Original full AKV suite changed')
    mapping = {report['source_mapping'][str(ROOT/relative)]:str(ROOT/relative) for relative in MODULES}
    for original in mapping.values():
        checker.require(report['input_pins'].get(original) == tools.digest(original), 'Canonical original not pinned')
    old_engine = (ROOT/MODULES[1]).read_text()
    checker.require('qbs_read_engine #(' in old_engine and 'akv_context i_context (' in old_engine,
                    'Baseline must be original private reader and storage')
    source_list = Path(report['compile_filelist'])
    old, new = paired_lists(source_list.read_text(), mapping)
    vcs = shutil.which('vcs')
    if not vcs:
        raise RuntimeError('VCS unavailable; no tool invoked')
    tool = Path(vcs).resolve()
    files = [*HERE.glob('*.py'), HERE/'monitor.sv', HERE/'README.md', BENCH,
             composer.CONTRACTS/'manifest.json', composer.CONTRACTS/'akv_engine_legacy_header.svh',
             Path(sys.executable).resolve(), Path(vcs), tool, tool.parents[1]/'linux64/bin/vcs1',
             snapshot/'manifest.json']
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).resolve().is_relative_to(ROOT):
            files.append(Path(name).resolve())
    pins = storage.merge_pins(report['input_pins'], report['artifact_pins'], WARNING_PINS,
                             {str(path):tools.digest(path) for path in files})
    tools.verify(pins)
    out.mkdir(parents=True, exist_ok=False)
    (out/'baseline').mkdir(); (out/'candidate').mkdir()
    (out/'baseline.f').write_text(old)
    (out/'candidate.f').write_text(new)
    (out/'original_suite.sv').write_bytes(BENCH.read_bytes())
    (out/'adapted_suite.sv').write_text(composer.adapt_tb(BENCH.read_text(), 'akv'))
    (out/'composed_engine.sv').write_text(composer.compose('akv'))
    (out/'monitor.sv').write_bytes((HERE/'monitor.sv').read_bytes())
    extra = [out/name for name in ('original_suite.sv','adapted_suite.sv','composed_engine.sv','monitor.sv')]
    graphs = {mode:graph_pins(out/(mode+'.f'), extra, snapshot/'source') for mode in ('baseline','candidate')}
    pins = storage.merge_pins(pins, *graphs.values())
    tools.verify(pins)
    tools.save(out/'source-pins.json', pins)
    manifest = dict(schema=SCHEMA, state='PREPARED_NOT_EXECUTED', output=str(out), snapshot=str(snapshot),
        snapshot_sha256=tools.digest(snapshot/'manifest.json'), mappings=mapping, graphs=graphs,
        extra_sources=list(map(str,extra)), vcs=str(Path(vcs)), source_pins_sha256=tools.digest(out/'source-pins.json'),
        original_tb_sha256=entry['tb_sha256'], compile_timeout_seconds=600, suite_timeout_seconds=600,
        admitted_compile_warning=warning_admission, warning_provenance=WARNING_PINS,
        same_original_stimulus=True, sram='Identical filelist sources/defines on both sides; not a new macro qualification',
        production_promoted=False, soc_verified=False, ppa_measured=False)
    tools.save(out/'manifest.json', manifest)
    tools.save(out/'status.json', dict(state='PREPARED_NOT_EXECUTED', child_pid=None))
    return tools.digest(out/'manifest.json')


def verify_prepared(out, reviewed):
    checker.require(tools.digest(out/'manifest.json') == reviewed, 'Reviewed manifest changed')
    manifest = json.loads((out/'manifest.json').read_text())
    checker.require(manifest['schema'] == SCHEMA and manifest['output'] == str(out), 'Wrong prepared output')
    checker.require(tools.digest(out/'source-pins.json') == manifest['source_pins_sha256'], 'Input receipt drift')
    pins = json.loads((out/'source-pins.json').read_text())
    tools.verify(pins)
    for mode in ('baseline','candidate'):
        current = graph_pins(out/(mode+'.f'), list(map(Path,manifest['extra_sources'])), Path(manifest['snapshot'])/'source')
        checker.require(current == manifest['graphs'][mode], 'Source/header inventory drift')
    return manifest


def execute(out, reviewed):
    checker.require(json.loads((out/'status.json').read_text())['state'] == 'PREPARED_NOT_EXECUTED', 'No in-place rerun')
    manifest = verify_prepared(out, reviewed)
    state = dict(state='BUILDING', child_pid=None)
    parsed = {}
    try:
        for mode in ('baseline','candidate'):
            verify_prepared(out, reviewed)
            state.update(state='BUILDING', variant=mode)
            tools.save(out/'status.json', state)
            tb = out/('original_suite.sv' if mode == 'baseline' else 'adapted_suite.sv')
            inputs = ([out/'composed_engine.sv'] if mode == 'candidate' else [])+[tb,out/'monitor.sv']
            command = [manifest['vcs'],'-full64','-sverilog','-timescale=1ns/1ps','-debug_access+all',
                '+lint=TFIPC-L','-f',str(out/(mode+'.f')),*map(str,inputs),'-top','akv_engine_tb',
                '-Mdir='+str(out/mode/'csrc'),'-o',str(out/mode/'simv')]
            code = tools.run(command, out, mode+'-compile', state)
            log = (out/(mode+'-compile.log')).read_text()
            admission = check_compile(log, code, Path(manifest['snapshot'])/TLB_RELATIVE)
            checker.require(admission == manifest['admitted_compile_warning'], 'Warning admission drift')
            tools.save(out/(mode+'-compile-admission.json'), admission)
            verify_prepared(out, reviewed)
            state['state'] = 'RUNNING'
            code = tools.run([str(out/mode/'simv'),'-no_save'], out, mode+'-suite', state)
            parsed[mode] = checker.check_log((out/(mode+'-suite.log')).read_text(), code)
            tools.save(out/(mode+'-checked.json'), parsed[mode])
            verify_prepared(out, reviewed)
        result = checker.compare(parsed['baseline'], parsed['candidate'])
        result.update(schema=SCHEMA, manifest_sha256=reviewed, post_pins_match=True,
            source_pins_sha256=manifest['source_pins_sha256'],
            evidence={str(p):tools.digest(p) for p in out.rglob('*')
                      if p.is_file() and (p.parent == out and p.name not in ('status.json','result.json') or
                                         p.name == 'simv')})
        tools.save(out/'result.json', result)
        state['state'] = result['state']
        return result
    except BaseException as exc:
        state.update(state='TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else 'FAIL', error=repr(exc))
        tools.save(out/'result.json', dict(state))
        raise
    finally:
        state['child_pid'] = None
        tools.save(out/'status.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-reviewed')
    args = parser.parse_args()
    def interrupted(sig, _frame):
        raise RuntimeError(f'Stop requested by signal {sig}')
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    if args.execute_reviewed:
        checker.require(args.snapshot is None, 'Execution consumes only the reviewed manifest')
        result = execute(args.output.resolve(strict=True), args.execute_reviewed)
        print(result['state'])
        return 0 if result['state'] == 'PASS' else 1
    checker.require(args.snapshot is not None, 'Preparation requires --snapshot')
    sha = prepare(args.snapshot.resolve(strict=True), args.output.resolve())
    print('PREPARED_NOT_EXECUTED manifest_sha256='+sha)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
