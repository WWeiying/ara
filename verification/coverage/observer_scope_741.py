"""One exact four-observer integration-scope batch on admitted historical741."""
import argparse
import csv
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

import run_admitted_741_dve as prior
import prepare_raw715_dve as common

life, require, tools = prior.life, prior.require, prior.tools
HERE = Path(__file__).resolve().parent
RAW = life.OUT / 'raw741-dve-parent-20261007-01'
BOOK = life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
SYSTEM = 'ara_tb.dut.i_ara_soc.i_system'
TARGETS = {
    SYSTEM + '.i_cva6_rvfi': ('cva6_rvfi', '3460467670'),
    SYSTEM + '.i_ariane.i_cva6_rvfi_probes': ('cva6_rvfi_probes', '1089031276'),
    SYSTEM + '.i_ara_commit_monitor': ('ara_commit_monitor', '182875116'),
    SYSTEM + '.i_ara_acc_contract_monitor': ('ara_acc_contract_monitor', '3628195876'),
}
SOURCES = ('hardware/deps/cva6/core/cva6.sv', 'hardware/deps/cva6/core/cva6_rvfi.sv',
           'hardware/deps/cva6/core/cva6_rvfi_probes.sv', 'hardware/src/ara_system.sv',
           'hardware/tb/ara_commit_monitor.sv', 'verification/uvm/ara_acc_contract_monitor.sv')


def native_entries(text):
    result, checksum = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//') or line.startswith('ANNOTATION:'):
            continue
        match = re.fullmatch(r'CHECKSUM:\s*"(\d+)"', line)
        if match:
            require(checksum is None, 'Unused checksum')
            checksum = match[1]
            continue
        if line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
            require(checksum is not None and scope not in result, 'Missing checksum/duplicate scope')
            result[scope], checksum = checksum, None
            continue
        raise ValueError('Non-observer exclusion directive: ' + line)
    require(checksum is None, 'Trailing checksum')
    return result


def source_contract():
    pins = json.loads(BOOK.read_bytes())
    result = {}
    for name in SOURCES:
        path = life.ROOT / name
        require(pins.get(str(path)) == life.digest(path), 'Frozen source differs: ' + name)
        result[str(path)] = pins[str(path)]
    for name in SOURCES[-2:]:
        text = (life.ROOT / name).read_text()
        text = re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)
        require(not re.search(r'\b(output|inout|force|release)\b', text), 'Monitor can drive product')
    return result


def compiled_targets(design):
    data = design.read_bytes()
    root = ET.fromstring(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)
    nodes = {i.get('id'): (i, d) for d in root.findall('srcdef') for i in d.findall('srcinst')}
    def path(key):
        i, _ = nodes[key]
        return (path(i.get('pid')) + '.' if i.get('pid') in nodes else '') + i.get('name')
    resolved = {path(k): (d.get('name'), d.get('chksum')) for k, (_, d) in nodes.items()}
    require(all(resolved.get(k) == v for k, v in TARGETS.items()), '741 native observer identity differs')
    require(not any(p.startswith(t + '.') for p in resolved for t in TARGETS), 'Observer is not a leaf')
    return {k: dict(module=v[0], checksum=v[1], recursive=False) for k, v in TARGETS.items()}


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    book = life.read_bound(prior.BASE / 'admission-manifest.json', prior.SEAL)
    pins = life.merge_pins(book['input_pins'], book['output_pins'])
    pins = life.merge_pins(pins, {str(prior.BASE / 'admission-manifest.json'): prior.SEAL})
    life.check(pins)
    raw = life.read_bound(prior.admission.RAW, prior.admission.RAW_SHA)
    inputs = (prior.BASE / 'combined-inputs.txt').read_text().splitlines()
    require(inputs == raw['input_ledger'] + [str(prior.admission.VDB)] and len(set(inputs)) == 742,
            'Exact admitted741 ledger required')
    require((RAW / 'inputs.txt').read_text().splitlines() == inputs, 'Raw741 population differs')
    result = json.loads((RAW / 'report-result.json').read_bytes())
    require(result['status'] == 'RAW741_DVE_REPORT_VERIFIED' and result['admission_seal'] == prior.SEAL and
            result['summary_sha256'] == life.digest(RAW / 'summary.csv'), 'Raw741 report not verified')
    design = Path(inputs[0]) / 'snps/coverage/db/design/verilog.design.xml'
    targets = compiled_targets(design)
    pins = life.merge_pins(pins, source_contract())
    for path in (BOOK, RAW / 'summary.csv', RAW / 'report-result.json', RAW / 'inputs.txt',
                 RAW / 'selected_tests.txt', HERE / 'observer_scope_741.py', HERE / 'observer_scope_741.tcl',
                 HERE / 'test_observer_scope_741.py', common.EXPORT):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    tools.revalidate(raw['tool_identity'])
    life.check(pins)
    out.mkdir()
    life.save(out / 'inputs.txt', '\n'.join(inputs) + '\n')
    life.save(out / 'observer-plan.tcl', 'set observer_scopes {\n' +
              ''.join('    {' + p + '}\n' for p in TARGETS) + '}\n')
    for p in (out / 'inputs.txt', out / 'observer-plan.tcl'):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    config = dict(schema='OBSERVER_INTEGRATION_SCOPE_741_V1', output=str(out), admission_seal=prior.SEAL,
        population=741, pins=pins, targets=targets, tool_identity=raw['tool_identity'], timeout_seconds=900,
        expected_selected=(RAW / 'selected_tests.txt').read_text().splitlines(),
        raw_reference=str(RAW), reason='Observation-only integration scope; NOT unreachable',
        source_connection_proof={
            'rvfi_probes': 'cva6.sv:1914..1957 -> output rvfi_probes_o -> ara_system.sv:195,226 -> i_cva6_rvfi',
            'rvfi': 'ara_system.sv:223..245: rvfi_instr only feeds commit monitor; rvfi_to_iti and rvfi_csr have no consumer',
            'commit_monitor': 'Input-only ports; log/termination observer, no product signal driver',
            'contract_monitor': 'Input-only bind ara_system; logs/protocol assertions, no product signal driver'},
        functional_IP_exclusions=[], new_RTL_signoff=False, automatic_retry=False)
    life.save(out / 'config.json', config)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), pins=len(pins), observers=4)))


def rows(path):
    with path.open(newline='') as stream:
        data = list(csv.DictReader(stream))
    require(len(data) == 2989, 'Incomplete hierarchy report')
    stack, result = [], {}
    for row in data:
        depth = int(row['Depth'])
        require(depth <= len(stack), 'Invalid hierarchy depth')
        stack = stack[:depth] + [row['Name']]
        scope = '.'.join(stack)
        require(scope not in result, 'Repeated hierarchy scope')
        result[scope] = row
    return result


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    expected = {p: v[1] for p, v in TARGETS.items()}
    require(native_entries((out / 'initial-empty.el').read_text()) == {} and
            native_entries((out / 'final-empty.el').read_text()) == {}, 'Nonempty initial/reset exclusions')
    require(native_entries((out / 'observers.el').read_text()) == expected and
            native_entries((out / 'observers-reloaded.el').read_text()) == expected, 'Non-observer exclusion or checksum mismatch')
    raw, scoped = rows(out / 'summary.csv.partial'), rows(out / 'summary_scoped.csv')
    require(raw == rows(RAW / 'summary.csv') == rows(out / 'summary_reset.csv'), 'Raw/reset drift')
    require(scoped == rows(out / 'summary_reloaded.csv') and list(scoped) == list(raw), 'Reload/hierarchy differs')
    protected = [p for p in raw if p not in TARGETS and not any(t.startswith(p + '.') for t in TARGETS)]
    require(all(raw[p] == scoped[p] for p in protected), 'Product/non-target coverage changed')
    gui = (out / 'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('OBSERVER_741_SAVE_RELOAD_RESET_DONE') == 1 and
            gui.splitlines().count('DVE_COVERAGE_EXPORT_DONE') == 1, 'Incomplete capture')
    require((out / 'selected_tests.txt').read_text().splitlines() == c['expected_selected'], '741 native selection differs')
    diagnostic = re.compile(r'(^|\s)(Warning|Error|Fatal)([\s:-]|$)|EXPORT_FAILED|checksum mismatches\s*:\s*[1-9]|Total unmappable exclusions\s*:\s*[1-9]', re.M)
    require(not diagnostic.search(gui + (out / 'launcher.log').read_text()), 'DVE diagnostics')
    result = dict(status='APPLIED_OBSERVER_ONLY_741_INTEGRATION_SCOPE', tests=741, config_seal=seal,
        observers=c['targets'], protected_report_rows=len(protected), exact_native_EL=True,
        save_reload_semantic_parity=True, raw_reset_report_parity=True,
        raw_i_system=raw[SYSTEM], scoped_i_system=scoped[SYSTEM],
        new_RTL_signoff=False, unreachability_claim=False,
        input_pins=c['pins'], output_pins={str(p): life.digest(p) for p in out.rglob('*')
                                         if p.is_file() and p.name != 'result.json'})
    if (out / 'result.json').exists():
        require(json.loads((out / 'result.json').read_bytes()) == result, 'Saved result differs')
    else:
        life.save(out / 'result.json', result)
    print(json.dumps(dict(seal=life.digest(out / 'result.json'), raw=result['raw_i_system'], scoped=result['scoped_i_system'])))


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    require(c['targets'] == compiled_targets(Path((out / 'inputs.txt').read_text().splitlines()[0]) /
            'snps/coverage/db/design/verilog.design.xml') and c['output'] == str(out), 'Prepared target drift')
    life.check(c['pins'])
    tools.revalidate(c['tool_identity'])
    claim = out / 'execution.json'
    command = [shutil.which('xvfb-run'), '-a', '-e', str(out / 'xvfb.log'), '-s', '-screen 0 1280x1024x24',
               c['tool_identity']['roles']['launcher'], '-full64', '-cov', '-script', str(common.EXPORT)]
    life.save(claim, dict(command=command, cwd=str(out), timeout=900, automatic_retry=False))
    env = tools.controlled_environment(c['tool_identity'], os.environ)
    env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), DVE_REVIEWED_WAIVERS=str(HERE / 'observer_scope_741.tcl'))
    with (out / 'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(10)
        candidates = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                if (p / 'exe').resolve(strict=True) == Path(c['tool_identity']['executable']) and (p / 'cwd').resolve(strict=True) == out:
                    candidates.append(dict(pid=int(p.name), exe=str((p / 'exe').resolve()), cwd=str(out),
                                           command=(p / 'cmdline').read_bytes().replace(b'\0', b' ').decode()))
            except (OSError, ValueError):
                continue
        life.save(out / 'live-identity.json', candidates)
        print(json.dumps(dict(actual_dve=candidates)), flush=True)
        try:
            rc = process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise ValueError('Observer batch timed out; no retry')
    life.save(out / 'terminal.json', dict(returncode=rc, actual_dve_confirmed=bool(candidates)))
    require(rc == 0 and len(candidates) == 1, 'DVE failed or identity unconfirmed')
    verify(out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    a = p.parse_args()
    out = a.output.absolute()
    if a.mode == 'prepare':
        prepare(out)
    else:
        require(a.seal, 'Exact config seal required')
        (run if a.mode == 'run' else verify)(out, a.seal)
