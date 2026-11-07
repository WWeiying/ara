#!/usr/bin/env python3
"""Execute sealed prebuilt model guests without recompiling/relinking them."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from audit import digest, require, verify_pins
from run_supply_sdk import bind
from sdk_dispatch_model import RUNS, HERE, ROOT, PRIOR, MODEL, read, recipe
from run_rms_ggml_model import LATEST, BASE_ELF
from rms_ggml_model import check
from audit_sdk_guest_payload import validate_payload


def admit(record):
    required = dict(state='RMS_GGML_MODEL_PAIR_PREPARED_NOT_EXECUTED', performance_measured=False,
                    rtl_changed=False, production_library_promoted=False, compiled_translation_units=1,
                    common_model_object_reused=True, default_enabled=False,
                    baseline_link_reproduced_exactly=True, guest_cpio_parsed_and_bound=True,
                    baseline_elf_sha256=BASE_ELF, child_pid=None)
    require(all(k in record and record[k] == v for k, v in required.items()), 'Complete sealed model preflight required')


def execute(preflight, expected, output):
    preflight = preflight.resolve(strict=True); out = output.absolute()
    require(preflight.is_relative_to(RUNS) and out == out.resolve() and out.is_relative_to(RUNS),
            'Sole-verification fresh output required')
    out.mkdir(parents=True, exist_ok=False)
    pins = {}; commands = []
    result = dict(state='PREPARING', child_pid=None, compiled_translation_units=0,
                  rtl_changed=False, performance_measured=False, model_library_promoted=False)
    def pin(path, sha=None): bind(pins, path, sha)
    def save(): (out/'status.json').write_text(json.dumps(result, indent=2)+'\n')
    try:
        pin(preflight/'result.json', expected); prepared = read(preflight/'result.json'); admit(prepared)
        pin(preflight/'source-pins.json', prepared['source_pins_sha256'])
        for entries in (read(preflight/'source-pins.json'), prepared['artifacts']):
            for path, sha in entries.items(): pin(path, sha)
        require(not any(row['label'] == 'qemu' for row in read(preflight/'commands.json')),
                'Preflight must not already contain a target run')
        init = next(Path(words[2]) for words in (line.split() for line in (preflight/'initramfs.list').read_text().splitlines())
                    if len(words) == 6 and words[:2] == ['file', '/init'])
        guest = validate_payload((preflight/'initramfs.cpio').read_bytes(), {
            'init': init.read_bytes(), 'base': (LATEST/'candidate').read_bytes(),
            'candidate': (preflight/'candidate').read_bytes(), 'test': (preflight/'test').read_bytes()})
        require(guest == read(preflight/'guest-payload.json'), 'Actual prebuilt cpio audit differs')
        argv = recipe(read(LATEST/'commands.json'), 'qemu')
        require(argv[argv.index('-initrd')+1] == str(LATEST/'initramfs.cpio') and
                'xaraqbs=true' in argv[argv.index('-cpu')+1] and argv[argv.index('-smp')+1] == '1' and
                'readonly=on' in argv[argv.index('-drive')+1], 'Native single-hart readonly model required')
        argv[argv.index('-initrd')+1] = str(preflight/'initramfs.cpio')
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(HERE): pin(path)
        pin(HERE/'test_rms_ggml_model.py'); pin(HERE/'test_execute_rms_ggml_model.py'); pin(Path(sys.executable))
        verify_pins(pins); (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        env = dict(PATH='/usr/bin:/bin', LC_ALL='C', HOME=str(out), PYTHONDONTWRITEBYTECODE='1')
        commands.append(dict(label='qemu', argv=argv, cwd=str(out), timeout_seconds=7200, environment=env))
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        result.update(state='RUNNING', preflight=str(preflight), preflight_result_sha256=expected,
            baseline_elf_sha256=BASE_ELF, candidate_elf_sha256=prepared['candidate_elf_sha256'],
            candidate_library_sha256=prepared['candidate_library_sha256'],
            baseline_library_sha256=prepared['baseline_library_sha256'],
            common_model_object_sha256=prepared['common_model_object_sha256'],
            reused_prebuilt_guest_payload=True, source_pins_sha256=digest(out/'source-pins.json'))
        with (out/'qemu.log').open('xb') as log, (out/'qemu.stderr').open('xb') as errors:
            child = subprocess.Popen(argv, cwd=out, env=env, stdout=log, stderr=errors)
            result['child_pid'] = child.pid; save()
            try: code = child.wait(timeout=7200)
            except BaseException:
                child.kill(); child.wait(); raise
            finally: result['child_pid'] = None; save()
        commands[-1]['returncode'] = code; require(code == 0, 'Native model execution failed')
        verify_pins(pins)
        result['measured'] = check((out/'qemu.log').read_text(), (MODEL/'qemu.log').read_text(), read(PRIOR/'projection-schema.json'))
        require(result['measured']['native'] == read(LATEST/'result.json')['measured'],
                'Projection/Attention work differs from accepted production baseline')
        verify_pins(pins); result.update(state='RMS_GGML_PREBUILT_MODEL_PAIR_FUNCTIONAL_PASS', post_pins_match=True,
            log_sha256=digest(out/'qemu.log'), limits=[
                'Full logits/token/CSR and actual native work; no QEMU-derived hardware timing',
                'Norm row/node totals checked; fused distribution retained rather than assumed',
                'Opt-in isolated model library; not a production default or new RTL acceptance'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        save(); (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        result['source_pins_sha256'] = digest(out/'source-pins.json')
        result['artifacts'] = {str(p): digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('result.json','status.json')}
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preflight', type=Path, required=True); p.add_argument('--preflight-sha256', required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--execute-reviewed', action='store_true')
    def stop(sig, _frame): raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, stop)
    args = p.parse_args(); require(args.execute_reviewed, 'Explicit reviewed execution required')
    execute(args.preflight, args.preflight_sha256, args.output)
