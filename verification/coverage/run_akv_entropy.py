"""Prepare or explicitly run one sealed AKV entropy case; no automatic admission."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import run_gap95_simulation as life
import build_akv_descriptor_entropy_preflight as fixture
import collect_akv_entropy as collector

PRE = life.OUT/'akv-descriptor-entropy-preflight-owner-20261007-01'
PRE_SHA = '208726e271130145175a2150a6fa4de220dc497a5b34fc1f2d6ad82f920207ea'
BASE = life.OUT/'vmacc-offline-admitted775-parent-20261007-01'
BASE_SHA = '59d67f7d5088baefaa498eda1d8e0f607e0eaf87945cc79a5f83607f8d679a13'
PROBE = Path(__file__).with_name('akv_entropy_probe.tcl').resolve()
ELF = PRE/'input.elf'
NAME = 'akv_descriptor_entropy'
require = fixture.require


def command(output):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(ELF),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'),'+VECTOR_TRACE='+str(output/'vector_trace.csv'),
        '+AKV_PERF','+ARA_CONTRACT_TRACE_LIMIT=100000',
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),'-cm_name',NAME,
        '-ucli','-do',str(PROBE)]


def validate(pre):
    require(pre['status'] == 'AKV_DESCRIPTOR_ENTROPY_V1_SOFTWARE_PREFLIGHT_PASS_NOT_VCS' and
            pre['input_elf'] == str(ELF) and pre['dut_commands'] == 6 and pre['dut_checks'] == 3932 and
            pre['dut_traps'] == 1 and pre['dut_custom_write_bytes'] == 128 and pre['timeout_seconds'] == 600 and
            pre['software_reference_is_not_native_Spike'] is True and pre['coverage_admitted'] is False,
            'Exact adapter/native preflight differs')
    require(pre['oracle']['V1_opcodes'] == fixture.WORDS and pre['oracle']['rejected_VERSION_error'] == 3 and
            pre['oracle']['native_exception'] == dict(pc=pre['symbols']['entropy_site_1'],cause=2,tval=0),
            'Precise command/trap contract differs')
    require(pre['pins'][str(ELF)] == '2432ecf4e69be60fef9a994fa3d649a4431863a4440d9ae87b94dd0eaae32acc',
            'Fixed native ELF differs')


def check_baseline(base, ledger, prior):
    require(base['coverage_admitted'] is True and len(ledger) == len(set(ledger)) == 776 and
            ledger[:775] == prior, 'Exact formal775/774 prefix differs')


def dependency_pins():
    paths = {Path(__file__).resolve(),PROBE,Path(collector.__file__).resolve(),
             Path(__file__).with_name('test_akv_entropy_runtime.py').resolve()}
    for module in tuple(sys.modules.values()):
        file = getattr(module,'__file__',None)
        if file:
            p = Path(file).resolve()
            if p.suffix == '.py' and (p.parent == Path(__file__).resolve().parent or
                    p.is_relative_to(life.ROOT/'verification/ara_verify')):
                paths.add(p)
    return {str(p):fixture.sha(p) for p in paths}


def prepare(output, existing=False):
    output = Path(output).absolute()
    require(output.parent == life.OUT and output.resolve() == output and
            (output.is_dir() if existing else not output.exists()), 'Fresh/direct run output')
    pre = life.read_bound(PRE/'preflight-manifest.json',PRE_SHA); validate(pre)
    pins = life.merge_pins(pre['pins'],{str(PRE/'preflight-manifest.json'):PRE_SHA})
    base = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    ledger_path = BASE/'combined-inputs.txt'
    expected = base['output_pins'][str(ledger_path)]
    require(fixture.sha(ledger_path) == expected, 'Formal775 ledger drift')
    ledger = ledger_path.read_text().splitlines()
    old = life.read_bound(fixture.BASE/'admission-manifest.json',fixture.BASE_SHA)
    prior_path = fixture.BASE/'combined-inputs.txt'
    require(fixture.sha(prior_path) == old['output_pins'][str(prior_path)], 'Formal774 prefix drift')
    check_baseline(base,ledger,prior_path.read_text().splitlines())
    pins = life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(ledger_path):expected})
    bits_path = BASE/'combined-bits.json'
    bits = life.read_bound(bits_path,base['output_pins'][str(bits_path)])
    require(bits['tests'] == ledger[1:] and len(bits['tests']) == 775, 'Baseline bitmap membership differs')
    pins = life.merge_pins(pins,{str(bits_path):base['output_pins'][str(bits_path)]})
    plan = life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(plan['image']) == 66 and plan['simv'] == str(life.IMAGE), 'Exact66 old image required')
    pins = life.merge_pins(pins,plan['image'])
    pins = life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL})
    sources = life.read_bound(fixture.BUILD/'build-source-pins.json',
        pins[str(fixture.BUILD/'build-source-pins.json')])
    db = collector.isa.base.native.common.DESIGN/'snps/coverage/db'
    design_paths = [db/'design/verilog.design.xml',db/'auxiliary/verilog.sourceinfo.xml']
    design_paths += [db/('shape/'+metric+'.verilog.'+kind+'.xml')
                    for metric in ('line','branch','tgl') for kind in ('shape','info')]
    for p in design_paths:
        require(str(p) in base['input_pins'], 'Unbound compiled input: '+str(p))
        pins = life.merge_pins(pins,{str(p):base['input_pins'][str(p)]})
    life.check(pins)
    # Bind the established scalar reset/CSR/exception semantics, not just the new custom model.
    pins,source_proof = collector.isa.base.source_contract(sources,pins)
    dependencies = dependency_pins()
    audit_module = sys.modules[collector.isa.base.source_contract.__globals__['require'].__module__]
    dependencies[str(Path(audit_module.__file__).resolve())] = fixture.sha(audit_module.__file__)
    # Design imports its implementation from this frozen review directory.
    from inventory_operand_debug import Design
    design_module = sys.modules[Design.__module__]
    dependencies[str(Path(design_module.__file__).resolve())] = fixture.sha(design_module.__file__)
    for p,h in dependencies.items():
        if p in base['input_pins']:
            require(h == base['input_pins'][p], 'Historical helper drift: '+p)
    pins = life.merge_pins(pins,dependencies)
    require(fixture.sha(collector.CONVERTER) == collector.CONVERTER_SHA, 'Fixed converter drift')
    pins = life.merge_pins(pins,{str(collector.CONVERTER):collector.CONVERTER_SHA})
    life.check(pins)
    model,dry = collector.replay(ELF.read_bytes(),pre['symbols'])
    life.check(pins)
    return output,dict(case=NAME,preflight=pre,pins=pins,command=command(output),timeout_s=600,
        wave_limit_bytes=64*1024*1024,baseline_tests=775,baseline=str(BASE),baseline_sha256=BASE_SHA,
        dry_model=dry,source_proof=source_proof,expected_requests=len(model.requests),
        full_native_scalar_qualified=False,native_Spike_comparison=False,coverage_admitted=False,
        automatic_retry=False,EDA_launched=False,qualification_requires_ranges_VCD=True)


def live_identity(process,output,manifest):
    import time
    deadline = time.monotonic()+5
    while time.monotonic() < deadline and process.poll() is None:
        proc = Path('/proc')/str(process.pid)
        try:
            exe = (proc/'exe').resolve(strict=True)
            if exe == life.IMAGE:
                text = (proc/'stat').read_text()
                start = int(text[text.rfind(')')+2:].split()[19])
                require((proc/'cwd').resolve(strict=True) == output and
                        fixture.sha(proc/'exe') == manifest['pins'][str(life.IMAGE)] and
                        (proc/'cmdline').read_bytes().rstrip(b'\0').decode().split('\0') == manifest['command'],
                        'Actual simv identity differs')
                return dict(pid=process.pid,starttime=start,exe=str(exe),cwd=str(output),
                    executable_sha256=manifest['pins'][str(life.IMAGE)],command=manifest['command'],
                    input_elf=str(ELF),elf_sha256=manifest['pins'][str(ELF)],budget_s=600,
                    live_identity_verified=True,coverage_admitted=False)
        except FileNotFoundError:
            pass
        time.sleep(.05)
    raise ValueError('Actual simv live identity not established')


def run(output,manifest):
    require(manifest['command'] == command(output) and manifest['timeout_s'] == 600, 'Bounded command differs')
    life.check(manifest['pins']); output.mkdir(); life.save(output/'manifest.json',manifest)
    process = None
    try:
        with (output/'console.log').open('x') as log:
            process = subprocess.Popen(manifest['command'],cwd=output,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            life.save(output/'started.json',live_identity(process,output,manifest))
            # Wall-clock and wave bounds are enforced while the single process runs.
            import time
            deadline = time.monotonic()+600
            while process.poll() is None:
                require(time.monotonic() < deadline, 'Hard600 timeout')
                wave = output/'entropy-ranges.vpd'
                require(not wave.exists() or wave.stat().st_size <= manifest['wave_limit_bytes'], 'Wave limit exceeded')
                time.sleep(1)
            require(process.returncode == 0, 'Nonzero simulator exit')
            require((output/'entropy-ranges.vpd').is_file() and
                    (output/'entropy-ranges.vpd').stat().st_size <= manifest['wave_limit_bytes'], 'Final wave missing/oversize')
        life.check(manifest['pins'])
        life.save(output/'simulation-status.json',dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,
            timeout=False,pid=process.pid,coverage_admitted=False))
    except BaseException as error:
        if process is not None and process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL); process.wait()
        life.save(output/'simulation-status.json',dict(status='SIMULATION_FAILED_NOT_ADMITTED',reason=str(error),coverage_admitted=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','run')); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepared-seal')
    args = parser.parse_args()
    require((args.mode == 'run') == bool(args.prepared_seal), 'Explicit run seal required only for run')
    output,manifest = prepare(args.output)
    record = output.with_name(output.name+'.prepared.json')
    if args.mode == 'prepare':
        life.save(record,manifest)
        print(json.dumps(dict(status='AKV_ENTROPY_PREPARED_NO_EDA',prepared=str(record),seal=fixture.sha(record),pins=len(manifest['pins']))))
    else:
        require(life.read_bound(record,args.prepared_seal) == manifest, 'Reviewed prepared contract differs')
        run(output,manifest)
