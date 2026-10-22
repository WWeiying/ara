"""One authorized Linux identity compile; never executes the resulting ELF."""
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import time

HERE = Path(__file__).resolve().parent
G = HERE.parents[1]
ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
SOURCE = G / 'fp_compare_unboxed_full17920_prepare01/source_model02/software/original/parent.c'
FAMILY = ARCHIVE / 'rvv_fp_comparisons_unmasked01'
ASM = FAMILY / 'rvv_fp_compare_unmasked_e16_mf4.S'
ORIGINAL = ARCHIVE / 'rvv_additions30/binaries/rvv_fp_compare_unmasked_e16_mf4'
RECIPE = HERE.parent / 'provenance01/original_rebuild.command.json'
EXPECTED_C = '03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad'
EXPECTED_ELF = 'bef54674b16fdeefdb37295d035b1b9a58cd446cd54662078aa24e83cced7b2d'
HISTORICAL_C = '9060f2931a5a2b6b51e3ff7be14ce420efaeb5c34800e496dad95dd78fc89dcf'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(HERE, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sections(data):
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    require(h[0][:6] == b'\x7fELF\x02\x01' and h[2] == 243,
            'Expected ELF64 little-endian RISC-V')
    rows = [struct.unpack_from('<IIQQQQIIQQ', data, h[6] + i * h[11])
            for i in range(h[12])]
    names = rows[h[13]]
    strings = data[names[4]:names[4] + names[5]]
    result = {}
    for row in rows:
        name = strings[row[0]:].split(b'\0', 1)[0].decode('ascii')
        if not name:
            continue
        payload = None if row[1] == 8 else data[row[4]:row[4] + row[5]]
        result[name] = dict(type=row[1], flags=row[2], address=row[3],
                            offset=row[4], size=row[5], alignment=row[8],
                            payload_sha256=None if payload is None else
                            hashlib.sha256(payload).hexdigest())
    return result


def main():
    require(not (HERE / 'command.json').exists(), 'Sole attempt already prepared; no retry')
    require(sha(SOURCE) == sha(HERE / 'parent.c') == EXPECTED_C,
            'Unchanged authorized later C only')
    require(SOURCE.read_bytes() == (HERE / 'parent.c').read_bytes(), 'Exact source copy')
    require(sha(ORIGINAL) == EXPECTED_ELF, 'Exact original ELF identity')
    require(sha(ASM) == '156cb4e726a4eb5c2c7fb267f478f0e11beb2d68aadbdbe3c0f0ef43c002988a',
            'Exact original assembly')
    require(sha(FAMILY / 'e16/fixtures.h') ==
            '5664c1a4546bb402fe64ef190ca8e4910efa21fc35daea5229a187377eba7cb1',
            'Original fixtures')
    require(sha(FAMILY / 'e16/operations.h') ==
            'cd0e50739a57ccd54ead1092113528d6535ec62468e8fe4863dbb64fbf2fee64',
            'Original operation declarations')
    old = json.loads(RECIPE.read_text())
    command = list(old)
    command[command.index('-DDESTINATION_KIND=1')] = '-DDESTINATION_KIND=0'
    includes = [i for i, argument in enumerate(command) if argument.startswith('-I')]
    require(len(includes) == 1, 'One original header include path')
    command[includes[0]] = '-I' + str(FAMILY / 'e16')
    c = [i for i, argument in enumerate(command) if argument.endswith('.c')]
    assembly = [i for i, argument in enumerate(command) if argument.endswith('.S')]
    require(len(c) == len(assembly) == 1, 'One C and one assembly input')
    command[c[0]] = str(HERE / 'parent.c')
    command[assembly[0]] = str(ASM)
    command[command.index('-o') + 1] = str(HERE / 'rebuilt.elf')
    require(set(x for x in command if x.startswith('-D')) == {
        '-DSEW=16', '-DUNBOXED_COMPARISONS=0', '-DUNMASKED_COMPARISONS=1',
        '-DRESTART_COMPARISONS=0', '-DDESTINATION_KIND=0'}, 'Exact original definitions')
    compiler = Path(command[0])
    real = Path(str(compiler) + '.br_real')
    files = [Path(__file__).resolve(), SOURCE, HERE / 'parent.c', ORIGINAL, ASM,
             FAMILY / 'e16/fixtures.h', FAMILY / 'e16/operations.h',
             FAMILY / 'manifest.json', RECIPE, compiler, compiler.resolve(), real]
    pins = {str(path): sha(path) for path in files}
    save('input_pins.json', pins)
    save('compiler.json', dict(invoked=str(compiler), resolved=str(compiler.resolve()),
                              wrapper_sha256=sha(compiler), real_driver=str(real),
                              real_driver_sha256=sha(real), version_command_executed=False))
    save('command.json', dict(command=command, cwd=str(HERE), timeout_s=120,
                             attempts=1, no_retry=True, baseline_recipe=str(RECIPE),
                             baseline_recipe_sha256=sha(RECIPE),
                             hypothesis='Later disabled branches fold to the original complete ELF',
                             acceptance='Whole ELF byte identity only',
                             relevant_environment={name: os.environ.get(name) for name in
                                 ('CPATH', 'C_INCLUDE_PATH', 'LIBRARY_PATH',
                                  'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'STAGING_DIR')}))
    start = time.monotonic()
    timed_out = False
    with (HERE / 'compile.log').open('x') as stream:
        child = subprocess.Popen(command, cwd=HERE, stdout=stream,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            rc = child.wait()
    receipt = dict(actual_wait_returncode=rc, pid=child.pid,
                   elapsed_s=time.monotonic() - start, finished_epoch=time.time(),
                   timed_out=timed_out, retries=0, attempts=1, validated=False)
    save('compile_execution.json', receipt)
    post = {path: sha(path) for path in pins}
    save('post_pins.json', post)
    if rc != 0 or timed_out or post != pins:
        save('result.json', dict(status='COMPILE_OR_PIN_FAILURE_NOT_ACCEPTED',
                                 actual_compile=receipt, pins_unchanged=post == pins,
                                 historical_C_recovered=False, no_retry=True))
        raise SystemExit(1)
    original = ORIGINAL.read_bytes()
    rebuilt = (HERE / 'rebuilt.elf').read_bytes()
    identical = original == rebuilt
    differences = [i for i, (a, b) in enumerate(zip(original, rebuilt)) if a != b]
    first = differences[0] if differences else min(len(original), len(rebuilt)) if not identical else None
    left, right = sections(original), sections(rebuilt)
    section_report = {name: dict(original=left.get(name), rebuilt=right.get(name))
                      for name in sorted(set(left) | set(right))}
    save('section_comparison.json', section_report)
    save('byte_difference.json', dict(original_bytes=len(original), rebuilt_bytes=len(rebuilt),
                                      different_bytes_in_common_span=len(differences),
                                      length_delta=len(rebuilt) - len(original),
                                      first_difference_offset=first,
                                      first_32_differences=[dict(offset=i, original=original[i], rebuilt=rebuilt[i])
                                                            for i in differences[:32]]))
    result = dict(status='ELF_IDENTICAL_REBUILD_FROM_LATER_TEMPLATE' if identical else
                  'ELF_MISMATCH_FROM_LATER_TEMPLATE_STOP_NO_RETRY',
                  identical_full_ELF=identical, original_ELF_sha256=sha(ORIGINAL),
                  rebuilt_ELF_sha256=sha(HERE / 'rebuilt.elf'),
                  later_C_sha256=EXPECTED_C, expected_historical_C_sha256=HISTORICAL_C,
                  historical_C_status='NOT_RECOVERED', historical_C_recovered=False,
                  command_sha256=sha(HERE / 'command.json'),
                  compiler_identity_sha256=sha(HERE / 'compiler.json'),
                  input_pins_sha256=sha(HERE / 'input_pins.json'),
                  actual_execution_sha256=sha(HERE / 'compile_execution.json'),
                  actual_compile=receipt, pins_unchanged=True,
                  numeric_wait_saved_before_comparison=True, comparison_epoch=time.time(),
                  section_comparison_sha256=sha(HERE / 'section_comparison.json'),
                  byte_difference_sha256=sha(HERE / 'byte_difference.json'),
                  compile_attempts=1, retries=0, Host_Spike_DUT_executed=False,
                  original_provenance_modified=False, original_scene_closed=False)
    save('result.json', result)
    print(result['status'], result['rebuilt_ELF_sha256'], flush=True)


if __name__ == '__main__':
    main()
