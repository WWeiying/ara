#!/usr/bin/env python3
"""Fresh preparation after an adapter-aware static-check correction; no retries."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'vi0_missing2_prefix112_prepare01'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, why):
    if not ok:
        raise ValueError(why)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2);stream.write('\n')


def main(kind):
    old_pins = json.loads((OLD/'e8_m4/input_pins.json').read_text())
    require(sha(OLD/'prepare.py') == old_pins[str(OLD/'prepare.py')], 'Failed producer code must stay unchanged')
    old_failure = json.loads((OLD/'e8_m4/STOPPED.json').read_text())
    require(old_failure['error'] == "ValueError('Original RNG/loops/setup/fulloracle changed')", 'Exact static admission failure')
    require(not (OLD/'e8_m4/host').exists() and not (OLD/'e8_m4/soc01').exists()
        and not (OLD/'e8_m4/reference').exists(), 'Prior failure happened before Host/SoC/reference')
    text = (OLD/'prepare.py').read_text()
    old = "require(source[a:source.index(anchor)+len(anchor)] == port[port.index('    for(unsigned seed='):port.index(anchor)+len(anchor)],"
    new = "require(adapted[adapted.index('    for(unsigned seed='):adapted.index(anchor)+len(anchor)] == port[port.index('    for(unsigned seed='):port.index(anchor)+len(anchor)],"
    require(text.count(old) == 1, 'Unique adapter-aware static check')
    corrected = text.replace(old, new)
    generated = HERE/'frozen_prepare.py'
    if generated.exists():
        require(generated.read_text() == corrected, 'Successor code drift')
    else:
        generated.write_text(corrected)
        import difflib
        (HERE/'correction.diff').write_text(''.join(difflib.unified_diff(text.splitlines(True), corrected.splitlines(True))))
        save(HERE/'PRIOR_FAILURE.json', dict(status='PRESERVED_PRE_REFERENCE_STATIC_CHECK_FAILURE',
            actual_prepare_tool_exit=1, execution_evidence='exec_command session60693 final chunk56cff3 actualexit1',
            error=old_failure['error'], prior_Host_SoC_Spike_invocations=0,
            only_change='Compare accepted adapter segment against prefix; original ioctl adapter diff remains explicit',
            old_artifacts={str(p): sha(p) for p in (OLD/'e8_m4').rglob('*') if p.is_file()},
            failed_producer_sha256=sha(OLD/'prepare.py')))
    namespace = {'__file__': str(generated), '__name__': 'owned_vi0_successor_prepare'}
    exec(compile(corrected, str(generated), 'exec'), namespace)
    real_run = namespace['run']

    def original_receipt_reuse(command, log, seconds=30):
        if kind != 'e8_m4' or log.name != 'linux_rebuild.log':
            return real_run(command, log, seconds)
        proof_path = OLD/'e8_m4/original_binary_proof.json'
        proof = json.loads(proof_path.read_text())
        require(proof['status'] == 'PASS_FULL_ORIGINAL_LINUX_ELF_BYTE_IDENTICAL'
                and type(proof['execution']['returncode']) is int and proof['execution']['returncode'] == 0,
                'Actual prior successful original binary proof required')
        for name in ('scenario.c', 'operations.S', 'operations.h', 'original_linux.elf'):
            a = OLD/'e8_m4/prepared/gather_vi0_e8_m4_prefix112/original'/name
            b = HERE/'e8_m4/prepared/gather_vi0_e8_m4_prefix112/original'/name
            require(a.read_bytes() == b.read_bytes(), 'Reused proof source identity '+name)
        binary = Path(command[-1])
        shutil.copyfile(OLD/'e8_m4/original_rebuilt.elf', binary)
        require(sha(binary) == proof['original_elf_sha256'], 'Reused actual byte-identical ELF')
        shutil.copyfile(OLD/'e8_m4/linux_rebuild.log', log)
        receipt = dict(proof['execution'], reused=True, new_compile_invocations=0,
            actual_origin=str(OLD/'e8_m4/linux_rebuild.execution.json'),
            actual_origin_sha256=sha(OLD/'e8_m4/linux_rebuild.execution.json'),
            requested_equivalent_command=list(map(str, command)))
        save(log.with_suffix('.execution.json'), receipt)
        return receipt

    namespace['run'] = original_receipt_reuse
    out = HERE/kind
    try:
        namespace['prepare'](kind)
        receipt = json.loads((out/'READY.json').read_text())
        save(out/'successor_binding.json', dict(ready_sha256=sha(out/'READY.json'),
            driver_path=str(Path(__file__)), driver_sha256=sha(Path(__file__)),
            generated_path=str(generated), generated_sha256=sha(generated),
            correction_sha256=sha(HERE/'correction.diff'), prior_failure_sha256=sha(HERE/'PRIOR_FAILURE.json'),
            reference_launches=1, actual_reference_returncode=receipt['actual_reference_returncode'],
            old_artifacts_unchanged=all(sha(p)==d for p,d in json.loads((HERE/'PRIOR_FAILURE.json').read_text())['old_artifacts'].items())))
    except BaseException as error:
        if out.exists() and not (out/'STOPPED.json').exists():
            save(out/'STOPPED.json', dict(status='PREPARATION_FAILED_NO_RETRY', error=repr(error), new_DUT_runs=0))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=['e8_m4', 'e16_m8'])
    main(parser.parse_args().case)
