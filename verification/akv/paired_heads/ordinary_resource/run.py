#!/usr/bin/env python3
"""One direct-owned unified-image run; reuse the accepted historical baseline."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
from contract import (s, ROOT, Execution, checked_baseline, unified_image, own_pins,
                      raw, protocol, compare, HistoricalSources, DEFAULT_BUILD, DEFAULT_BASELINE, DEFAULT_SOC)


def simulation_command(simv, elf, work):
    return [simv, '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD=' + str(elf),
            '+TESTCASE=akv_paired_heads_threeway', '+NO_FSDB', '+NO_INSTR_TRACE',
            '+AKV_PERF', '+AKV_SUMMARY', '+VECTOR_TRACE=' + str(work / 'vector_trace.csv'),
            '+COMMIT_TRACE=' + str(work / 'commit_trace.csv'),
            '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']


def validate_timeout(timeout):
    s.require(type(timeout) is int and 1 <= timeout <= 10800, 'Timeout must be 1..10800 seconds')


def run(args):
    validate_timeout(args.timeout)
    build, baseline, soc_build = (p.resolve(strict=True) for p in (args.build, args.baseline, args.soc_build))
    out = args.output.resolve()
    s.require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (build, baseline, soc_build)),
              'Use a fresh independent output')
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(build=str(build), baseline=str(baseline), soc_build=str(soc_build), timeout_seconds=args.timeout)
    owner.save()
    result = {}
    try:
        historical = HistoricalSources(ROOT, out / 'historical-source', s)
        historical.materialize()
        report, old, old_records, pins = checked_baseline(baseline, build, historical)
        soc, extra, image = unified_image(soc_build)
        s.merge_pins(pins, extra)
        s.merge_pins(pins, own_pins())
        elf, simv = Path(report['elf']), Path(soc['simv'])
        owner.state.update(elf=str(elf), simv=str(simv))
        owner.save()
        s.atomic_json(out / 'source-pins.json', pins)
        receipt = s.digest(out / 'source-pins.json')

        def identity():
            s.require(s.digest(out / 'source-pins.json') == receipt, 'Worker receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Image inventory drift')

        def manifest(stage):
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                           simv.parent / 'vcs_source_manifest.json', '--check'],
                          out / (stage + '.log'), 300, stage.upper())

        identity()
        manifest('manifest-before')
        owner.execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                       simv.parent, elf, 'akv_v2'], out / 'image-contract.log', 180, 'IMAGE_CONTRACT')
        identity()
        if args.preflight_only:
            manifest('manifest-after')
            identity()
            result = dict(state='PREFLIGHT_PASS_NOT_RUN', source_pins_sha256=receipt,
                          elf_sha256=report['elf_sha256'], post_pins_match=True)
        else:
            owner.execute(simulation_command(simv, elf, work), work / 'console.log', args.timeout, 'RUNNING')
            new, new_records = raw(out)
            result['raw_replay'] = new
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                           '--require-axi', '--require-axi-write', '--vector-trace', work / 'vector_trace.csv',
                           '--log', work / 'run.vcs.log', '--simv', simv, '--elf', elf,
                           '--output', work / 'uvm_result.json'], work / 'checker.log', 600, 'CHECKING')
            protocol(out, report['elf_sha256'], image)
            manifest('manifest-after')
            identity()
            result.update(simulator_exit_code=0, post_pins_match=True, independent_protocol_checked=True,
                          source_pins_sha256=receipt, elf_sha256=report['elf_sha256'],
                          snapshot_sha256=soc['snapshot_sha256'], baseline=str(baseline), build=str(build),
                          soc_build=str(soc_build), evidence_sha256=s.hashes([
                              work / name for name in ('run.vcs.log', 'vector_trace.csv', 'commit_trace.csv',
                                  'uvm_result.json', 'console.log', 'console.command.json', 'checker.command.json')
                          ] + [out / name for name in ('source-pins.json', 'manifest-before.log',
                                                       'manifest-after.log', 'image-contract.log')]))
            comparison = compare(old, new, old_records, new_records)
            result.update(state=comparison['state'], comparison=comparison)
        s.atomic_json(out / 'result.json', result)
        owner.state['state'] = result['state']
        return result
    except BaseException as exc:
        state = ('TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else
                 'INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL')
        owner.state.update(state=state, error=repr(exc))
        result.update(state=state, error=repr(exc))
        s.atomic_json(out / 'result.json', result)
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=DEFAULT_BUILD)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    parser.add_argument('--soc-build', type=Path, default=DEFAULT_SOC)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--preflight-only', action='store_true')

    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    sys.exit(0 if run(parser.parse_args())['state'] in ('PASS', 'PREFLIGHT_PASS_NOT_RUN') else 1)
