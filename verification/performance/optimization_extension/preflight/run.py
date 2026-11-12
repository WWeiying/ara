#!/usr/bin/env python3
"""Frozen dual-entry M4 benchmark; gate one bounded existing-image VCS run on Spike."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
SNAPSHOT = OUT/'enablement_unified_build_20261111_01'
COMMON = OUT/'stage2_qwen3_attn_m4_build_20261109_04'
IMAGE = OUT/'enablement_soc_build_20261111_02'
PROTOCOL = OUT/'stage3_attention_sdk_vcs_20261110_01'
PROTOCOL_SHA = '70ccad29ade83850f3c6a94276b8f60d7258513c4091939267641f550bbd3fb1'
PROTOCOL_PINS = 'd532da52c58a5742c294cab8a7148397a08e4e2ec13cb1a568e3f7c0582da3c2'
HELPER_SHA = '71b07f59aa44bea1102674d68fbe9fbaa36fa055f078804b4ff5dd0353fe0291'
DATA = OUT/'stage2_qwen3_rows8_20261109_02/attn_q/activation_f32.bin'
DATA_SHA = '4ba6296b70be49960bcce50b09efa38afb938993e38cd710ec6cf5ca951a441c'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
CXX = CC.with_name('riscv64-unknown-elf-g++')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
OWN = ('run.py', 'check.py', 'test_check.py', 'main.cpp', 'soc_io.c')
ENV = dict(PATH='/usr/bin:/bin', HOME='/home/wangwy', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True); f.write('\n')


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Pin drift: '+str(path))


def output(path):
    path = Path(path).resolve()
    require(path.parent == OUT and re.fullmatch(r'optimization_extension_preflight_[A-Za-z0-9_]+', path.name),
            'Direct sole signoff optimization_extension_preflight_* output required')
    return path


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def image_inventory():
    sim = IMAGE/'sim'
    return {str(p): sha(p) for p in sorted(sim.rglob('*')) if p.is_file() and
            (p.name == 'simv' or p.is_relative_to(sim/'simv.daidir'))}


def prepare(out):
    require(not out.exists(), 'Fresh output required; preserve original failures')
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()
    pins = {}; commands = []
    report = dict(state='FAIL', automatic_retry=False, simulator_launched=False, performance_measured=False)

    def pin(path):
        path = Path(path).resolve(strict=True); digest = sha(path)
        require(str(path) not in pins or pins[str(path)] == digest, 'Pin drift: '+str(path))
        pins[str(path)] = digest

    def copy(src, dst, inventory=None):
        if inventory is not None:
            require(inventory.get(str(src)) == sha(src), 'Unsealed snapshot: '+str(src))
        pin(src); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst); pin(dst)

    def run(label, argv, seconds=120):
        argv = list(map(str, argv)); pin(argv[0])
        command = dict(label=label, argv=argv, cwd=str(out), environment=ENV, timeout_seconds=seconds)
        commands.append(command)
        with (out/(label+'.log')).open('x') as log:
            proc = subprocess.run(argv, cwd=out, env=ENV, stdin=subprocess.DEVNULL,
                                  stdout=log, stderr=subprocess.STDOUT, timeout=seconds)
        command['returncode'] = proc.returncode
        require(proc.returncode == 0, 'Failed '+label+'; preserve original log')
        return (out/(label+'.log')).read_text().strip()

    try:
        for name in OWN:
            copy(HERE/name, inputs/name)
        checker = load(inputs/'check.py', 'extension_preflight_check')
        for directory, rel, dest in ((SNAPSHOT, 'inputs/llama/ggml', 'ggml'),
                                     (SNAPSHOT, 'inputs/sdk/software/qbs', 'sdk/software/qbs'),
                                     (COMMON, 'inputs/sdk/apps/common', 'common')):
            inventory = read(directory/'source-pins.json'); pin(directory/'source-pins.json')
            for src in sorted((directory/rel).rglob('*')):
                if src.is_file() and src.suffix in ('.h', '.hpp', '.c', '.cpp', '.S', '.inc', '.ld'):
                    copy(src, inputs/dest/src.relative_to(directory/rel), inventory)
        old = ROOT/'verification/performance/next_mechanism/stage4/m4_preflight'
        for name in ('start.S', 'runtime.cpp', 'link.ld'):
            copy(old/name, inputs/'spike'/name)
        helper = inputs/'sdk/software/qbs/experimental/m4_preflight/m4_preflight.h'
        require(sha(helper) == HELPER_SHA and 'max_k = 6144;' in helper.read_text(), 'SDK helper identity/bounds')
        require(sha(DATA) == DATA_SHA and DATA.stat().st_size == 8*2048*4, 'Real activation identity/extent')
        copy(DATA, inputs/'activation_f32.bin')
        data = inputs/'data.S'
        data.write_text('.section .rodata\n.balign 64\n.global extension_input\nextension_input:\n.incbin '+
                        json.dumps(str(inputs/'activation_f32.bin'))+'\n.section .note.GNU-stack,"",@progbits\n')
        pin(data)
        link = (inputs/'common/arch.link.ld').read_text()
        require(link.count('LENGTH = 0x00100000') == 1, 'Common linker template drift')
        (inputs/'soc-link.ld').write_text(link.replace('ALIGNMENT', '16').replace(
            'LENGTH = 0x00100000', 'LENGTH = 0x01000000'))
        pin(inputs/'soc-link.ld')
        # Only the already-accepted protocol implementation, never its live counterpart.
        verify({str(PROTOCOL/'result.json'): PROTOCOL_SHA, str(PROTOCOL/'source-pins.json'): PROTOCOL_PINS})
        require(read(PROTOCOL/'result.json')['state'] == 'PASS', 'Protocol predecessor not accepted')
        pin(PROTOCOL/'result.json'); pin(PROTOCOL/'source-pins.json')
        pp = read(PROTOCOL/'source-pins.json'); base = PROTOCOL/'inputs/verification/ara_verify'
        for src in sorted(base.rglob('*.py')):
            copy(src, inputs/'verification/ara_verify'/src.relative_to(base), pp)
        image = read(IMAGE/'image-pins.json')
        hw = read(IMAGE/'build.json')
        require(hw['state'] == 'ENABLEMENT_SOC_BUILT_NOT_EXECUTED' and hw['post_pins_match'] is True and
                hw['post_image_match'] is True and hw['image_pins'] == image == image_inventory(),
                'Accepted image content/membership mismatch')
        require(hw['configuration']['shared_fma'] == 1, 'Wrong all-on image')
        require(image[str(IMAGE/'sim/simv')] == '9a193e4045467b0e90f251ab62469eaa95609515e46718f1c18741e61d0fe4fb',
                'Wrong original accepted image')
        for name in ('build.json', 'image-pins.json', 'source-pins.json', 'plan.json'):
            pin(IMAGE/name)
        pins.update(image)
        run('checker-tests', [sys.executable, '-B', inputs/'test_check.py', '-v'])
        ggml = inputs/'ggml'; arch = ggml/'src/ggml-cpu/arch/riscv'
        includes = []
        for p in (inputs, helper.parent, inputs/'sdk/software/qbs/include', inputs/'common',
                  ggml/'include', ggml/'src', ggml/'src/ggml-cpu', arch):
            includes += ['-isystem', str(p)]
        flags = ['-O2', '-DNDEBUG', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany',
                 '-mno-relax', '-msmall-data-limit=0', '-fno-fast-math', '-ffp-contract=off',
                 '-ffunction-sections', '-fno-data-sections', '-fno-stack-protector', '-fno-tree-vectorize',
                 '-fno-tree-slp-vectorize', '-DNR_LANES=4', '-DVLEN=1024', *includes]
        for driver, names in ((CC, ('cc1', 'as', 'ld')), (CXX, ('cc1plus', 'collect2'))):
            for name in names:
                path = run(driver.name+'-locate-'+name, [driver, '-print-prog-name='+name])
                pin(shutil.which(path, path=ENV['PATH']) or path)
        libgcc = Path(run('locate-libgcc', [CXX, *flags[2:4], '-print-libgcc-file-name']))
        pin(libgcc)

        def compile_one(name, src, extra=()):
            cpp = src.suffix == '.cpp'; driver = CXX if cpp else CC
            mode = ['-std=c++17', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics'] if cpp else []
            if src.name in ('runtime.cpp', 'string.c'):
                mode += ['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns']
            obj = out/(name+'.o')
            run(name+'-compile', [driver, *flags, *mode, *extra, '-MD', '-MF', out/(name+'.d'), '-c', src, '-o', obj])
            pin(obj)
            return obj

        shared = [compile_one('main', inputs/'main.cpp'), compile_one('data', data),
                  compile_one('generic', ggml/'src/ggml-cpu/repack.cpp',
                              ['-Dggml_quantize_mat_q8_K_4x1_ara_generic=frozen_generic'])]
        spike_objects = [compile_one('spike-start', inputs/'spike/start.S'),
                         compile_one('spike-runtime', inputs/'spike/runtime.cpp')]
        soc_objects = [compile_one('soc-io', inputs/'soc_io.c')]
        soc_objects += [compile_one('soc-'+Path(name).stem, inputs/'common'/name) for name in
                        ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
        elf_info = {}
        for name, objects, script in (('spike', spike_objects, inputs/'spike/link.ld'),
                                      ('soc', soc_objects, inputs/'soc-link.ld')):
            elf = out/(name+'.elf')
            run(name+'-link', [CXX, *flags, '-nostdlib', '-static', *shared, *objects,
                              '-Wl,--gc-sections', '-Wl,--build-id=none', '-Wl,-Map='+str(out/(name+'.map')),
                              '-T', script, libgcc, '-o', elf]); pin(elf)
            names = run(name+'-symbols', [CC.with_name('riscv64-unknown-elf-nm'), '-n', elf])
            symbols = {}
            for symbol in ('_start', 'main', 'extension_baseline', 'extension_candidate',
                           *(('test_exit', 'test_log', 'tohost') if name == 'spike' else ('_eoc', '_putchar', 'printf_'))):
                rows = re.findall(r'^([0-9a-f]+) \w '+symbol+'$', names, re.M)
                require(len(rows) == 1, 'Missing entry: '+symbol)
                symbols[symbol] = rows[0]
            run(name+'-readelf', [CC.with_name('riscv64-unknown-elf-readelf'), '-a', elf])
            run(name+'-disassembly', [CC.with_name('riscv64-unknown-elf-objdump'), '-d', elf])
            elf_info[name] = dict(path=str(elf), sha256=sha(elf), symbols=symbols)
        for dep in out.glob('*.d'):
            for name in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]):
                p = Path(name).resolve(strict=True)
                require(not p.is_relative_to(ROOT/'software') and
                        not p.is_relative_to(Path('/home/wangwy/llama/llama.cpp')), 'Live library dependency')
                pin(p)
        cmd = inputs/'spike.cmd'
        cmd.write_text('until pc 0 '+elf_info['spike']['symbols']['test_exit']+'\nreg 0 a0\nstr '+
                       elf_info['spike']['symbols']['test_log']+'\nrs\n'); pin(cmd); pin(SPIKE)
        verify(pins)
        text = run('spike', [SPIKE, '-d', '--debug-cmd='+str(cmd),
                            '--isa=rv64gcv_zfh_zvfh_zicntr_zvl1024b', '-m2', out/'spike.elf'], 90)
        require(len(re.findall(r'^0x0000000000000000$', text, re.M)) == 1, 'Spike return status')
        reference = checker.numerical(text)
        save(out/'spike-check.json', reference); pin(out/'spike-check.json'); pin(out/'spike.log')
        environment = read(IMAGE/'plan.json')['environment'].copy()
        environment['LD_LIBRARY_PATH'] = str(Path(environment['VCS_HOME'])/'linux64/lib')+':'+environment.get('LD_LIBRARY_PATH', '')
        environment.update(PYTHONPATH=str(inputs/'verification'), PYTHONDONTWRITEBYTECODE='1', READELF='/usr/bin/readelf')
        pin('/usr/bin/readelf')
        # Pin dynamically loaded VCS libraries in addition to the complete generated design.
        linked = run('simv-ldd', ['/usr/bin/ldd', IMAGE/'sim/simv'])
        require('not found' not in linked, 'Missing simulator runtime library')
        for path in re.findall(r'(?:=>\s+|^\s*)(/[^\s()]+)', linked, re.M):
            pin(path)
        unit = 'optimization-extension-preflight-'+out.name.removeprefix('optimization_extension_preflight_')
        plan = dict(schema='m4-extension-preflight-v1', state='SPIKE_CHECKED_READY_FOR_ONE_VCS',
                    elves=elf_info, simv=str(IMAGE/'sim/simv'), image_pins=image,
                    data_sha256=DATA_SHA, helper_sha256=HELPER_SHA, environment=environment,
                    unit=unit, simulation_seconds=3600, protocol_seconds=1200, automatic_retry=False,
                    trials=8, order=['A', 'B', 'B', 'A'], trials_per_shape=4, calls_per_trial=3,
                    shapes=[dict(k=2048, real_operator=True, description='First 4 rows of Qwen3 attn_norm 8x2048'),
                            dict(k=4096, real_operator=False, description='Same 8x2048 activation bytes reshaped 4x4096')],
                    roi_included=['cache cold query', 'one producer', 'cache store', 'two hit lookups/copies',
                                  'caller CSR merge and loop/accounting'],
                    roi_excluded=['cache construction', 'initial poisoning', 'warmup', 'full memcmp', 'guards',
                                  'hashing', 'logging', 'cache destruction'],
                    baseline='Existing packed-parallel quantize<true>, producer tag3',
                    candidate='Same SDK m4_preflight.h, producer tag4; no live adapter enablement change',
                    spike_performance_claim=False, full_model_claim=False)
        save(out/'plan.json', plan); pin(out/'plan.json')
        verify(pins); save(out/'source-pins.json', pins)
        report.update(state='SPIKE_CHECKED_READY_FOR_ONE_VCS', elves=elf_info, post_pins_match=True,
                      source_pins_sha256=sha(out/'source-pins.json'), helper_sha256=HELPER_SHA,
                      data_sha256=DATA_SHA, service=unit+'.service')
    except BaseException as exc:
        report['error'] = repr(exc)
        if not (out/'source-pins.json').exists():
            save(out/'source-pins.json', pins)
    save(out/'commands.json', commands); save(out/'build.json', report)
    return report


def execute(out, review):
    require(Path(__file__).resolve() == out/'inputs/run.py', 'Frozen direct-owner worker required')
    require(sha(out/'source-pins.json') == review, 'Reviewed source pin identity')
    pins = read(out/'source-pins.json'); verify(pins)
    plan = read(out/'plan.json'); build = read(out/'build.json')
    require(build['state'] == 'SPIKE_CHECKED_READY_FOR_ONE_VCS' and build['source_pins_sha256'] == review,
            'Spike/checker gate not accepted')
    require(not (out/'attempt.json').exists() and not (out/'result.json').exists(), 'One VCS attempt only')
    unit = os.environ.get('SYSTEMD_UNIT', plan['unit']+'.service')
    owner = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True)
    require(int(owner.strip()) == os.getpid(), 'systemd must directly own this worker')
    save(out/'attempt.json', dict(started=stamp(), worker_pid=os.getpid(), service=unit,
                                  source_pins_sha256=review, build_sha256=sha(out/'build.json'),
                                  cgroup=Path('/proc/self/cgroup').read_text()))
    work = out/'vcs'; work.mkdir()
    report = dict(state='FAIL', automatic_retry=False, performance_measured=False, service=unit,
                  source_pins_sha256=review, started=stamp())
    checker = load(out/'inputs/check.py', 'frozen_extension_checker')
    env = plan['environment']; simv = plan['simv']; elf = plan['elves']['soc']['path']

    def run(label, argv, seconds):
        argv = list(map(str, argv))
        save(work/(label+'.command.json'), dict(argv=argv, cwd=str(work), environment=env, timeout_seconds=seconds))
        with (work/(label+'.log')).open('x') as log:
            child = subprocess.Popen(argv, cwd=work, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            save(work/(label+'.process.json'), dict(pid=child.pid, worker_pid=os.getpid(), started=stamp()))
            try:
                rc = child.wait(timeout=seconds)
            except BaseException:
                try:
                    os.killpg(child.pid, signal.SIGTERM); child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL); child.wait()
                raise
        save(work/(label+'.exit.json'), dict(returncode=rc, finished=stamp()))
        require(rc == 0, 'Failed '+label+'; no retry')

    try:
        verify(pins)
        require(image_inventory() == plan['image_pins'], 'Image membership drift')
        run('console', [simv, '-no_save', '-l', work/'run.vcs.log', '+PRELOAD='+elf,
                        '+TESTCASE=optimization_extension_preflight', '+NO_FSDB', '+NO_INSTR_TRACE',
                        '+COMMIT_TRACE='+str(work/'commit.csv'), '+VECTOR_TRACE='+str(work/'vector.csv'),
                        '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
            plan['simulation_seconds'])
        numerical = checker.numerical((work/'run.vcs.log').read_text(), vcs=True, reference=read(out/'spike-check.json'))
        save(work/'numerical.json', numerical)
        io = {str(work/name): sha(work/name) for name in ('run.vcs.log', 'commit.csv', 'vector.csv')}
        run('protocol', [sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                         '--require-axi', '--require-axi-write', '--vector-trace', work/'vector.csv',
                         '--log', work/'run.vcs.log', '--simv', simv, '--elf', elf, '--output', work/'protocol.json'],
            plan['protocol_seconds'])
        proof = read(work/'protocol.json')
        checker.protocol(proof, dict(elf_sha256=plan['elves']['soc']['sha256'], simv_sha256=sha(simv),
                                    log_sha256=io[str(work/'run.vcs.log')], vector_trace_sha256=io[str(work/'vector.csv')]))
        verify(io); verify(pins)
        require(image_inventory() == plan['image_pins'], 'Post image membership drift')
        report.update(state='M4_EXTENSION_PREFLIGHT_VCS_CHECKED', post_pins_match=True, post_image_match=True,
                      performance_measured=True, cycle_metrics=numerical['cycle_metrics'],
                      elf_sha256=sha(elf), simv_sha256=sha(simv), protocol_sha256=sha(work/'protocol.json'),
                      protocol_counts=proof['contract_counts'], full_model_claim=False)
    except BaseException as exc:
        report['error'] = repr(exc)
    report['finished'] = stamp()
    report['artifacts'] = {str(p): sha(p) for p in sorted(work.rglob('*')) if p.is_file()}
    save(out/'result.json', report)
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'M4_EXTENSION_PREFLIGHT_VCS_CHECKED')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'execute'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--review-sha256')
    args = parser.parse_args(); out = output(args.output)
    if args.action == 'prepare':
        report = prepare(out); print(json.dumps(report), flush=True)
        return int(report['state'] == 'FAIL')
    return execute(out, args.review_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
