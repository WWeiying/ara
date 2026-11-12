#!/usr/bin/env python3
"""Frozen minimal QBINFO admission; two package builds and two small SoC runs."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
OLD = OUT / 'enablement_soc_build_20261111_02'
NEW = OUT / 'enablement_soc_extension_20261111_01'
COMMON = OUT / 'stage2_qwen3_attn_m4_build_20261109_04/inputs/sdk/apps/common'
PROTOCOL = OUT / 'stage3_attention_sdk_vcs_20261110_01'
REUSE = OUT / 'optimization_extension_sdk_20261111_01'
GNU = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')
CC = GNU / 'riscv64-unknown-elf-gcc'
HOSTS = ('qbs_runtime_test', 'qbs_runtime_adapter_example', 'qbs_format_test',
         'qbs_segmented_test', 'qbs_planner_traffic', 'qbs_context_admission_test',
         'qbs_context_cost_test', 'qbs_cooperative_test')
OVERLAYS = ('include/qbs/qbs.h', 'include/qbs/qbs_abi.h', 'src/qbs_runtime.c')
DONE = re.compile(r'^EXT_NATIVE_CAPABILITY_DONE expected=(\d+) actual=(\d+) decoded=(\d+) legacy=(\d+) errors=(\d+)$', re.M)
WORDS = re.compile(r'^EXT_NATIVE_WORDS info0=([0-9a-f]{16}) info1=([0-9a-f]{16}) old_words=(\d+) hash=([0-9a-f]{16}) errors=(\d+)$', re.M)

NATIVE_HARNESS = r'''#include "qbs/qbs.h"
#include "printf.h"
int capability_original_main(void);
int main(void) {
  unsigned errors = capability_original_main() != 0;
  uint64_t hash = UINT64_C(14695981039346656037);
  unsigned checked = 0;
  for (unsigned i = 0; i < 256; ++i) {
    if (i == 5) continue;
    const uint64_t word = qbs_native_info(NULL, i);
    errors += word != qbs_capability_word(i, 1024);
    for (unsigned b = 0; b < 8; ++b) {
      hash ^= (word >> (8 * b)) & 255u;
      hash *= UINT64_C(1099511628211);
    }
    ++checked;
  }
  printf("EXT_NATIVE_WORDS info0=%016lx info1=%016lx old_words=%u hash=%016lx errors=%u\n",
         (unsigned long)qbs_native_info(NULL, 0), (unsigned long)qbs_native_info(NULL, 1),
         checked, (unsigned long)hash, errors);
  return errors != 0;
}
'''

PACKAGE_EXTRA = '''    if (QbsCooperativeCapabilityIndex != 5 || QbsCooperativeQ4KBit != 0)
      $fatal(1, "Cooperative ABI literal changed");
    for (int v = 32; v <= 2048; v += 32)
      for (int policy = 0; policy < 2; policy++)
        for (int index = 0; index < 256; index++)
          if (index != 5 && qbs_capability_word(64'(index), v, 1'(policy)) !==
              legacy_qbs_pkg::qbs_capability_word(64'(index), v))
            $fatal(1, "Legacy package mismatch vlen=%0d index=%0d", v, index);
    if (qbs_capability_word(64'hffff, 1024, 1'b1) !== 0)
      $fatal(1, "Unknown query must return zero");
    $display("EXT_LEGACY_PACKAGE_PASS old_words=255 widths=64 policies=2");
'''


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def verify(pins):
    for name, digest in pins.items():
        require(sha(name) == digest, 'Identity drift: ' + str(name))


def pin(pins, path):
    key, digest = str(path), sha(path)
    require(key not in pins or pins[key] == digest, 'Pin conflict: ' + key)
    pins[key] = digest


def copy(pins, source, dest):
    pin(pins, source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    pin(pins, dest)


def output(path):
    path = Path(path).absolute()
    require(path == path.resolve() and path.parent == OUT and
            re.fullmatch(r'optimization_extension_capability_20261111_[A-Za-z0-9_]+', path.name),
            'Fresh direct signoff capability output required')
    return path


def wait_builder(pid):
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        return 'ALREADY_EXITED'
    try:
        command = Path('/proc', str(pid), 'cmdline').read_bytes()
        require(b'enablement_soc_extension_20261111_01' in command, 'Builder PID incarnation differs')
        select.select([fd], [], [])
    finally:
        os.close(fd)
    return 'PIDFD_EXIT'


def checked_image(directory):
    report = read(directory / 'build.json')
    require(report['state'] == 'ENABLEMENT_SOC_BUILT_NOT_EXECUTED' and
            report['post_pins_match'] is True and report['post_image_match'] is True and
            report['source_pins_sha256'] == sha(directory / 'source-pins.json') and
            report['configuration'] == read(directory / 'plan.json')['configuration'],
            'Unaccepted terminal image build')
    pins = read(directory / 'source-pins.json')
    image = {str(p): sha(p) for p in (directory / 'sim/simv.daidir').rglob('*') if p.is_file()}
    pin(image, directory / 'sim/simv')
    require(image == report['image_pins'] == read(directory / 'image-pins.json'), 'Image membership drift')
    pins.update(image)
    for name in ('build.json', 'source-pins.json', 'plan.json', 'inventory.json', 'sources.f', 'image-pins.json'):
        pin(pins, directory / name)
    verify(pins)
    return report, pins


def package_bench(text):
    marker = '    $display("EXT_CAPABILITY_PASS'
    require(text.count(marker) == 1, 'Unrecognized parent package probe')
    return text.replace(marker, PACKAGE_EXTRA + marker)


def static_admission(inputs):
    ara = (inputs / 'rtl/ara.sv').read_text()
    dispatcher = (inputs / 'rtl/ara_dispatcher.sv').read_text()
    pkg = (inputs / 'rtl/ara_pkg.sv').read_text()
    gate = re.search(r'localparam bit QbsLaneMulSupported\s*=\s*(.*?);', ara, re.S)
    require(gate and ' '.join(gate[1].split()) ==
            'EnableQbsLaneMul && qbs_pkg::QbsEnable && NrLanes == 4 && VLEN == 1024 && QbsLaneMulLatencySupported',
            'Top-level cooperative enable/geometry/latency gate differs')
    require('.QbsCooperativeMul (QbsLaneMulSupported)' in ara and
            re.search(r'parameter bit\s+QbsCooperativeMul\s*=\s*1\'b0', dispatcher),
            'Actual dispatcher parameter binding is missing')
    branch = dispatcher.split('if (is_qbinfo) begin', 1)[1].split('end else if (is_qbexec)', 1)[0]
    require('qbs_capability_word(64\'(acc_req_i.rs1), VLEN, QbsCooperativeMul)' in branch and
            "acc_resp_o.resp_valid = 1'b1;" in branch and 'if (!QbsEnable)' in branch and
            'QbsLaneMulLatencySupported = LatMultiplierEW8 == 0;' in pkg,
            'QBINFO combinational response/latency admission differs')
    return dict(top_gate=' '.join(gate[1].split()), dispatcher_parameter='QbsCooperativeMul',
                capability_is_constant=True, arithmetic_changed=False,
                note='Static source inspection plus real query run, not a new arithmetic/performance acceptance')


def prepare(out):
    require(not out.exists(), 'Preserve every prior attempt')
    waited = wait_builder(1051629)
    old, oldpins = checked_image(OLD)
    new, newpins = checked_image(NEW)
    require(old['configuration'] == new['configuration'] and
            new['configuration']['qbs_lane_multiplier'] == 1 and new['configuration']['vlen'] == 1024 and
            new['configuration']['nr_lanes'] == 4, 'Image configuration mismatch')
    branch = subprocess.check_output(['/usr/bin/git', '-C', str(OUT.parents[1]),
                                     'branch', '--show-current'], text=True).strip()
    require(branch == 'ara_dsa_signoff_integration', 'Wrong evidence branch')
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    pins = oldpins | newpins
    # Retain the inventories inspected before creating our two unsealed helpers.
    inventories = []
    for path in sorted(OUT.glob('*20261111*/source-pins.json')):
        entries = read(path)
        inventories.append(dict(path=str(path), sha256=sha(path), entries=len(entries),
            owned_matches=[p for p in entries if p in [str(HERE/n) for n in ('capability_run.py', 'capability_test.py')]],
            documentation_pins={p: h for p, h in entries.items() if p.endswith('.md')}))
    save(out / 'inspected-worker-inventories.json', inventories)
    require(not any(r['owned_matches'] for r in inventories), 'New owned helper is already sealed')
    for name in ('capability_run.py', 'capability_test.py', 'capability.c', 'capability.sv'):
        copy(pins, HERE / name, inputs / name)
    for name in ('ara.sv', 'ara_dispatcher.sv'):
        copy(pins, NEW / 'source/hardware/src' / name, inputs / 'rtl' / name)
    for name in ('ara_pkg.sv', 'qbs_pkg.sv'):
        copy(pins, NEW / 'source/hardware/include' / name, inputs / 'rtl' / name)
    copy(pins, OLD / 'source/hardware/include/qbs_pkg.sv', inputs / 'legacy_qbs_pkg.source.sv')
    legacy = (inputs / 'legacy_qbs_pkg.source.sv').read_text()
    require(legacy.count('package qbs_pkg;') == 1, 'Unrecognized legacy package declaration')
    (inputs / 'legacy_qbs_pkg.sv').write_text(legacy.replace('package qbs_pkg;', 'package legacy_qbs_pkg;'))
    (inputs / 'package_tb.sv').write_text(package_bench((inputs / 'capability.sv').read_text()))
    (inputs / 'native_harness.c').write_text(NATIVE_HARNESS)
    head = subprocess.check_output(['/usr/bin/git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    archive = subprocess.check_output(['/usr/bin/git', '-C', str(ROOT), 'archive', head, 'software/qbs'])
    (inputs / 'sdk-head.tar').write_bytes(archive)
    sdk = inputs / 'sdk'
    sdk.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        require(all(not Path(m.name).is_absolute() and '..' not in Path(m.name).parts and
                    (m.isfile() or m.isdir()) for m in tar.getmembers()), 'Unsafe SDK archive member')
        tar.extractall(sdk)
    overlays = {}
    for name in OVERLAYS:
        source = ROOT / 'software/qbs' / name
        dest = sdk / 'software/qbs' / name
        overlays[name] = dict(before=sha(dest), overlay=sha(source))
        copy(pins, source, dest)
    copy(pins, ROOT / 'software/qbs/tests/qbs_cooperative_test.c', inputs / 'qbs_cooperative_test.c')
    commonpins = read(OUT / 'stage2_qwen3_attn_m4_build_20261109_04/source-pins.json')
    for source in COMMON.rglob('*'):
        if source.is_file():
            require(commonpins.get(str(source)) == sha(source), 'Unpinned common source')
            copy(pins, source, inputs / 'common' / source.relative_to(COMMON))
    link = (inputs / 'common/arch.link.ld').read_text()
    require(link.count('LENGTH = 0x00100000') == 1, 'Common linker geometry differs')
    (inputs / 'link.ld').write_text(link.replace('ALIGNMENT', '16').replace('LENGTH = 0x00100000', 'LENGTH = 0x01000000'))
    protocolpins = read(PROTOCOL / 'source-pins.json')
    require(read(PROTOCOL / 'result.json')['state'] == 'PASS', 'Protocol predecessor is not PASS')
    for source in (PROTOCOL / 'inputs/verification/ara_verify').rglob('*.py'):
        require(protocolpins.get(str(source)) == sha(source), 'Unpinned independent protocol helper')
        copy(pins, source, inputs / 'verification/ara_verify' / source.relative_to(PROTOCOL / 'inputs/verification/ara_verify'))
    for name in ('source-pins.json', 'result.json'):
        pin(pins, PROTOCOL / name)
    for name in HOSTS:
        copy(pins, REUSE / name, inputs / 'host-reuse' / name)
        (inputs / 'host-reuse' / name).chmod(0o755)
    reused_sources = {}
    for source in (ROOT / 'software/qbs').rglob('*'):
        if source.is_file() and source.suffix in ('.c', '.h') and 'build' not in source.relative_to(ROOT / 'software/qbs').parts:
            pin(reused_sources, source)
    pin(reused_sources, ROOT / 'software/qbs/Makefile')
    pins.update(reused_sources)
    save(out / 'host-reuse-source-pins.json', reused_sources)
    config = dict(sdk_commit=head, sdk_archive_scope=['software/qbs'], sdk_overlays=overlays,
        common=str(COMMON), builder_wait=waited, old_image=str(OLD), new_image=str(NEW),
        vcs=str(Path(shutil.which('vcs')).resolve()), python='/usr/bin/python3',
        automatic_retry=False, static_admission=static_admission(inputs),
        reused_host_original_build_receipt_available=False,
        reused_host_scope='Re-execution of parent-provided binaries with binary and contemporaneous source SHAs; no inferred original build receipt',
        environment={k: os.environ[k] for k in ('HOME', 'VCS_HOME', 'VCS_ARCH_OVERRIDE', 'SNPSLMD_LICENSE_FILE', 'LM_LICENSE_FILE', 'LD_LIBRARY_PATH') if k in os.environ})
    config['environment'].update(PATH=str(GNU) + ':/usr/bin:/bin', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1',
                                 PYTHONPATH=str(inputs / 'verification'))
    for tool in (CC, GNU / 'riscv64-unknown-elf-objdump', Path('/usr/bin/gcc'), Path('/usr/bin/python3'), Path(config['vcs'])):
        pin(pins, tool.resolve())
    for driver in (CC, Path('/usr/bin/gcc')):
        for tool in ('cc1', 'as', 'ld', 'collect2'):
            name = subprocess.check_output([str(driver), '-print-prog-name=' + tool], text=True).strip()
            path = Path(name) if '/' in name else Path(shutil.which(name))
            pin(pins, path.resolve())
    for name in ('libm.a', 'libc.a', 'libgcc.a', 'libnosys.a'):
        path = subprocess.check_output([str(CC), '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
                                        '-print-file-name=' + name], text=True).strip()
        pin(pins, Path(path).resolve(strict=True))
    for path in inputs.rglob('*'):
        if path.is_file():
            pin(pins, path)
    save(out / 'plan.json', config)
    pin(pins, out / 'plan.json')
    pin(pins, out / 'host-reuse-source-pins.json')
    verify(pins)
    save(out / 'source-pins.json', pins)
    save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=sha(out / 'source-pins.json')))
    return dict(output=str(out), review_sha256=sha(out / 'source-pins.json'))


def native_check(text, expected):
    done, words = DONE.findall(text), WORDS.findall(text)
    require(len(done) == len(words) == 1 and tuple(map(int, done[0])) == (expected, expected, expected, 0, 0),
            'Native feature/decode/legacy probe failed or duplicated')
    a, b, count, digest, errors = words[0]
    require(int(count) == 255 and int(errors) == 0 and int(a, 16) != 0 and int(b, 16) != 0,
            'Native old-word inventory failed')
    return dict(expected=expected, actual=expected, decoded=expected, legacy=0, errors=0,
                info0=a, info1=b, old_words=255, old_words_hash=digest)


def protocol_check(proof, image, elf, log):
    require(proof['status'] == 'PASS' and proof['issues'] == [] and
            proof['elf_sha256'] == sha(elf) and proof['simv_sha256'] == sha(image['simv']) and
            proof['log_sha256'] == sha(log) and proof['sim_image_sha256'] ==
            {p: h for p, h in image['image_pins'].items() if p == image['simv'] or p.endswith('.so')},
            'Independent CVXIF proof/image/log identity failed')
    counts = proof['contract_counts']
    require(counts['requests'] == counts['responses'] and counts['requests'] >= 255 and
            all(counts[k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding', 'mmu_request_cycles')),
            'CVXIF exception/drain/VLSU failure')
    require(proof['backend_counts'] is not None and all(v == 0 for v in proof['backend_counts'].values()) and
            proof['uvm_backend_event_count'] == 0 and
            proof['axi_read_counts'] is not None and proof['axi_write_counts'] is not None and
            all(v == 0 for v in proof['axi_read_counts'].values()) and
            all(v == 0 for v in proof['axi_write_counts'].values()), 'QBINFO entered backend or VLSU AXI')


def unit(out):
    return 'optimization-extension-capability-' + out.name + '.service'


def service(out, review):
    require(sha(out / 'source-pins.json') == review and not (out / 'attempt.json').exists(), 'Sealed one-attempt service required')
    return ['/usr/bin/systemd-run', '--user', '--unit=' + unit(out), '--property=Type=exec',
            '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
            '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
            '--property=StandardError=append:' + str(out / 'service.stderr.log'),
            '/usr/bin/python3', '-B', '-u', str(out / 'inputs/capability_run.py'), 'execute',
            '--output', str(out), '--review-sha256', review]


def execute(out, review):
    require(Path(__file__).resolve() == out / 'inputs/capability_run.py', 'Use frozen worker only')
    require(sha(out / 'source-pins.json') == review and
            read(out / 'prepared.json') == dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=review), 'Unreviewed input closure')
    require(not (out / 'attempt.json').exists(), 'Never restart an attempt')
    cgroup = Path('/proc/self/cgroup').read_text()
    owner = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit(out), '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + unit(out) in cgroup and owner == str(os.getpid()), 'Worker must directly own service MainPID')
    save(out / 'attempt.json', dict(main_pid=os.getpid(), unit=unit(out), cgroup=cgroup, review_sha256=review))
    pins, config = read(out / 'source-pins.json'), read(out / 'plan.json')
    inputs, env = out / 'inputs', config['environment']
    artifacts, commands, compiled_inputs = {}, [], {}
    report = dict(state='FAIL', source_pins_sha256=review, automatic_retry=False,
                  scope='Minimal capability admission only; no model, projection, performance or FPGA acceptance',
                  host_reuse=[], package=[], native=[])
    started = time.monotonic()

    def run(label, command, work=out, timeout=None):
        verify(pins)
        log = work / (label + '.log')
        command = list(map(str, command))
        commands.append(dict(label=label, argv=command, cwd=str(work), environment=env, timeout=timeout))
        save(out / 'commands.json', commands)
        print('CAPABILITY ' + label, flush=True)
        with log.open('x') as stream:
            proc = subprocess.Popen(command, cwd=work, env=env, stdout=stream, stderr=subprocess.STDOUT)
            save(out / 'status.json', dict(state=label, worker_pid=os.getpid(), child_pid=proc.pid, command=command))
            try:
                code = proc.wait(timeout=timeout)
            except BaseException:
                proc.terminate()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise
        commands[-1].update(returncode=code, log=str(log), log_sha256=sha(log))
        save(out / 'commands.json', commands)
        pin(artifacts, log)
        require(code == 0, label + ' returncode=' + str(code))
        verify(pins)
        return log.read_text()

    try:
        run('runner-unit-tests', ['/usr/bin/python3', '-B', inputs / 'capability_test.py'], timeout=120)
        for name in HOSTS:
            run('reuse-' + name, [inputs / 'host-reuse' / name], timeout=180)
            report['host_reuse'].append(dict(name=name, returncode=0, binary_sha256=sha(inputs / 'host-reuse' / name)))
        sdk, common = inputs / 'sdk/software/qbs', inputs / 'common'
        sources = [inputs / 'qbs_cooperative_test.c'] + [sdk / 'src' / n for n in ('qbs_runtime.c', 'qbs_native_riscv.c', 'qbs_format.c')]
        for mode in ('gcc', 'ubsan'):
            exe = out / ('cooperative-' + mode)
            flags = ['-fsanitize=undefined', '-fno-sanitize-recover=all'] if mode == 'ubsan' else []
            run(mode + '-compile', ['/usr/bin/gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-I' + str(sdk / 'include'), *flags, *sources, '-o', exe], timeout=180)
            pin(artifacts, exe)
            result = run(mode + '-32combo', [exe], timeout=120)
            require('QBS_COOPERATIVE_CAPABILITY_PASS combinations=32' in result, 'Incomplete host capability combinations')
        for enable in (0, 1):
            work = out / ('package_qbs' + str(enable))
            work.mkdir()
            defines = ['+define+ARA_QBS_ENABLE'] if enable else []
            run('compile', [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps',
                '-top', 'extension_capability_tb', '-o', work / 'simv', *defines,
                inputs / 'legacy_qbs_pkg.sv', inputs / 'rtl/qbs_pkg.sv', inputs / 'package_tb.sv'], work)
            imagepins = {str(p): sha(p) for p in (work / 'simv.daidir').rglob('*') if p.is_file()}
            pin(imagepins, work / 'simv')
            save(work / 'image-pins.json', imagepins)
            text = run('run', [work / 'simv', '-no_save'], work, timeout=120)
            require(text.count('EXT_CAPABILITY_PASS widths=64 policies=2 old_words_unchanged=1') == 1 and
                    text.count('EXT_LEGACY_PACKAGE_PASS old_words=255 widths=64 policies=2') == 1 and
                    not re.search(r'Fatal:|Error:|Error-\[', text), 'Package capability test failed')
            verify(imagepins)
            artifacts.update(imagepins)
            pin(artifacts, work / 'image-pins.json')
            report['package'].append(dict(qbs_enable=enable, widths=64, policies=2, old_words=255, state='PASS'))
        flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
                 '-O2', '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-ffunction-sections', '-fdata-sections',
                 '-DNR_LANES=4', '-DVLEN=1024', '-I' + str(sdk / 'include'), '-I' + str(common)]
        shared = [inputs / 'native_harness.c', *[common / n for n in
            ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')],
            sdk / 'src/qbs_runtime.c', sdk / 'src/qbs_native_riscv.c']
        objects = []
        for i, source in enumerate(shared):
            obj = out / ('common_%02d_%s.o' % (i, source.stem))
            extra = ['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns'] if source.name == 'string.c' else []
            run('compile-' + obj.stem, [CC, *flags, *extra, '-MD', '-MF', obj.with_suffix('.d'), '-c', source, '-o', obj], timeout=180)
            objects.append(obj)
        for expected in (0, 1):
            obj, elf = out / ('capability%d.o' % expected), out / ('capability%d.elf' % expected)
            run('compile-capability%d' % expected, [CC, *flags, '-DEXPECT_COOPERATIVE=' + str(expected),
                '-Dmain=capability_original_main', '-MD', '-MF', obj.with_suffix('.d'), '-c', inputs / 'capability.c', '-o', obj], timeout=180)
            run('link-capability%d' % expected, [CC, *flags[:4], '-static', '-nostartfiles', '-nostdlib',
                *objects, obj, '-Wl,--gc-sections', '-Wl,-Map=' + str(elf.with_suffix('.map')),
                '-T', inputs / 'link.ld', '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf], timeout=180)
            listing = run('disassembly%d' % expected, [GNU / 'riscv64-unknown-elf-objdump', '-d', elf], timeout=120)
            require('0005155b' in listing and '<capability_original_main>:' in listing,
                    'Missing actual native QBINFO or original parent probe')
            pin(artifacts, elf)
        for dep in out.glob('*.d'):
            for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
                path = Path(name).resolve(strict=True)
                require(not path.is_relative_to(ROOT / 'software'), 'Live dirty compiler input')
                pin(compiled_inputs, path)
        save(out / 'compiler-input-pins.json', compiled_inputs)
        pin(artifacts, out / 'compiler-input-pins.json')
        for expected, directory in ((0, OLD), (1, NEW)):
            image, imagepins = checked_image(directory)
            verify(imagepins)
            elf = out / ('capability%d.elf' % expected)
            work = out / ('native_expect%d' % expected)
            work.mkdir()
            command = [image['simv'], '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD=' + str(elf),
                       '+TESTCASE=optimization_extension_capability_' + str(expected), '+NO_FSDB', '+NO_INSTR_TRACE',
                       '+VECTOR_TRACE=' + str(work / 'vector.csv'), '+COMMIT_TRACE=' + str(work / 'commit.csv'),
                       '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
            run('console', command, work)
            raw = {str(p): sha(p) for p in work.iterdir() if p.is_file()}
            result = native_check((work / 'run.vcs.log').read_text(), expected)
            run('protocol', ['/usr/bin/python3', '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                '--log', work / 'run.vcs.log', '--simv', image['simv'], '--elf', elf,
                '--output', work / 'protocol.json'], work, timeout=120)
            protocol_check(read(work / 'protocol.json'), image, elf, work / 'run.vcs.log')
            with (work / 'vector.csv').open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            require(len(rows) == 1 and rows[0]['event'] == 'config' and rows[0]['nr_lanes'] == '4' and
                    rows[0]['vlen_bits'] == '1024', 'Independent trace contains backend activity')
            save(work / 'numerical.json', result)
            verify(raw)
            verify(imagepins)
            verify(pins)
            artifacts.update({str(p): sha(p) for p in work.iterdir() if p.is_file()})
            report['native'].append(dict(state='PASS', directory=str(work), elf_sha256=sha(elf),
                simv_sha256=sha(image['simv']), **result))
            save(out / 'progress.json', report)
        a, b = report['native']
        require(all(a[k] == b[k] for k in ('info0', 'info1', 'old_words', 'old_words_hash')),
                'Native cross-image old-word mismatch')
        verify(pins)
        verify(artifacts)
        verify(compiled_inputs)
        save(out / 'artifact-pins.json', artifacts)
        report.update(state='PASS', post_pins_match=True, post_image_match=True,
                      post_artifacts_match=True, artifact_pins_sha256=sha(out / 'artifact-pins.json'),
                      old_words_cross_image_equal=True, backend_allocations=0, vlsu_axi_transactions=0,
                      static_admission=config['static_admission'])
    except BaseException as exc:
        report['error'] = repr(exc)
    report['elapsed_seconds'] = time.monotonic() - started
    save(out / 'result.json', report)
    save(out / 'status.json', dict(state=report['state'], worker_pid=os.getpid(), child_pid=None))
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'service-command', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    out = output(args.output)
    if args.action == 'prepare':
        print(json.dumps(prepare(out)), flush=True)
    elif args.action == 'service-command':
        print(json.dumps(service(out, args.review_sha256)), flush=True)
    else:
        return execute(out, args.review_sha256)
    return 0


if __name__ == '__main__':
    def interrupted(sig, frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    raise SystemExit(main())
