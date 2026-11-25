#!/usr/bin/env python3
"""Build an isolated safety bundle and run ONLY the host status classifier."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
SIGNOFF = ROOT.parent/'ara_dsa_signoff_integration'
OUT = SIGNOFF/'verification/out'
REL = Path('verification/performance/resident_deployment/direct_cost')
DIRECT = Path('software/llama/platform/linux/direct')
GNU = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')
KERNEL = DIRECT/'kernel/v1'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def instructions(code):
    offset = 0
    while offset < len(code):
        require(offset+2 <= len(code), 'Truncated instruction')
        word = int.from_bytes(code[offset:offset+2], 'little')
        size = 2 if word & 3 != 3 else 4
        require(offset+size <= len(code) and (size == 2 or word & 0x1f != 0x1f),
                'Unsupported/truncated instruction')
        yield size, int.from_bytes(code[offset:offset+size], 'little')
        offset += size


def prepare(out):
    require(not out.exists(), 'Preserve every previous bundle')
    require(subprocess.check_output(['git', '-C', str(SIGNOFF), 'branch', '--show-current'],
                                    text=True).strip() == 'ara_dsa_signoff_integration', 'Wrong signoff branch')
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()
    names = [Path('AGENTS.md'), REL/'lease_smoke.c', REL/'test_lease_smoke.py', REL/'test_client.py',
             *[DIRECT/n for n in ('direct_client.c', 'direct_client.h', 'direct_uapi.h')],
             KERNEL/'README.md', KERNEL/'hooks.py',
             KERNEL/'overlay/arch/riscv/kernel/akv_direct.c']
    pins = {}
    for name in names:
        source, destination = ROOT/name, inputs/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        pins[str(source)] = sha(source)
        shutil.copyfile(source, destination)
        require(sha(destination) == pins[str(source)], 'Source snapshot race')
        pins[str(destination)] = sha(destination); destination.chmod(0o444)
    pins[str(SIGNOFF/'AGENTS.md')] = sha(SIGNOFF/'AGENTS.md')
    tools = {name: shutil.which(name, path='/usr/bin:/bin') for name in ('gcc', 'clang')}
    require(all(tools.values()), 'Host GCC and Clang required')
    tools.update(rvcc=str(GNU/'riscv64-linux-gcc'), objdump=str(GNU/'riscv64-linux-objdump'),
                 readelf=str(GNU/'riscv64-linux-readelf'), python=str(Path(sys.executable).resolve()))
    for path in tools.values():
        resolved = Path(path).resolve(strict=True); pins[str(resolved)] = sha(resolved)
    for library in ('libc.a', 'libgcc.a', 'libgcc_eh.a'):
        resolved = Path(subprocess.check_output([tools['rvcc'], '-mabi=lp64d',
            '-print-file-name='+library], text=True).strip()).resolve(strict=True)
        pins[str(resolved)] = sha(resolved)
    common = ['-std=gnu11', '-O2', '-mabi=lp64d', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
              '-fno-stack-protector', '-fno-builtin', '-ffunction-sections', '-fdata-sections',
              '-fno-pie', '-Wall', '-Wextra', '-Werror']
    plan = dict(schema='akv-direct-lease-safety-bundle-v1', tools=tools, common_cflags=common,
        smoke_arch='rv64gcv_zfh_zvfh', client_arch='rv64gc',
        link_flags=['-static', '-no-pie', '-Wl,--gc-sections'],
        run_argument='--new-gate-lease-smoke', supervised_cases=11,
        runtime_requires=['NEW strict gate signature 0x414b5601', 'matching TEST kernel hooks',
            'root/CAP_SYS_RAWIO', 'one online CPU/hart0', 'memlock and 128KiB private prefaulted stack',
            'ordinary RVV/F enabled and warmed before every lease'],
        runtime_bounds=dict(prepare_ms=30000, case_ms=8000, cleanup_ms=2000),
        scope='Bounded safety prerequisite only; not full OS isolation proof or Attention/performance evidence',
        board_executed=False, target_executed=False, modifies_perf_fixture=False, automatic_retry=False)
    save(out/'build_requirements.json', plan)
    pins[str(out/'build_requirements.json')] = sha(out/'build_requirements.json')
    save(out/'source-pins.json', pins)
    review = sha(out/'source-pins.json')
    print('FROZEN '+str(out)+' source-pins-sha256='+review, flush=True)
    return subprocess.run([tools['python'], '-B', str(inputs/REL/'test_lease_smoke.py'),
        '--output', str(out), '--run', '--review-sha256', review],
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CCACHE_DISABLE='1')).returncode


def frozen(out, review):
    require(Path(__file__).resolve() == out/'inputs'/REL/'test_lease_smoke.py' and
            sha(out/'source-pins.json') == review, 'Frozen reviewed driver required')
    require(not (out/'attempt.json').exists(), 'One attempt per output')
    save(out/'attempt.json', dict(pid=os.getpid(), source_pins_sha256=review))
    pins = json.loads((out/'source-pins.json').read_text())
    plan = json.loads((out/'build_requirements.json').read_text()); tools = plan['tools']
    inputs, work = out/'inputs', out/'work'; work.mkdir()
    commands = []
    report = dict(state='FAIL', board_executed=False, target_executed=False,
                  production_changed=False, scope=plan['scope'], source_pins_sha256=review)

    def verify():
        for path, digest in pins.items():
            require(sha(path) == digest, 'Source identity drift: '+path)

    def run(label, argv):
        verify()
        require(not str(argv[0]).endswith('.elf'), 'Executing the board ELF is forbidden')
        commands.append(dict(label=label, argv=list(map(str, argv))))
        save(out/'commands.json', commands)
        with (out/(label+'.log')).open('x') as stream:
            subprocess.run(list(map(str, argv)), cwd=work, stdout=stream, stderr=subprocess.STDOUT,
                timeout=120, check=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CCACHE_DISABLE='1'))
        verify()
        return (out/(label+'.log')).read_text()

    try:
        verify()
        source = inputs/REL/'lease_smoke.c'; direct = inputs/DIRECT
        text = source.read_text()
        require(not re.search(r'\b(?:execve|execveat|execl|execvp|system|popen)\s*\(', text),
                'No process replacement/shell execution belongs in this smoke')
        require('mlockall(MCL_CURRENT | MCL_FUTURE)' in text and 'prefault_stack();' in text and
                'volatile unsigned char stack[128 * 1024]' in text and 'warm_f();' in text and
                'PROT_NONE' in text, 'Missing memory/state preparation')
        require(text.index('warm_f();') < text.index('emit(reply_fd, READY, 0)') and
                text.index('prefault_stack();') < text.index('emit(reply_fd, READY, 0)'),
                'Preparation must finish before READY/admission')
        require('while ((rc = receive(child, deadline)) > 0)' in text and
                'UNEXPECTED_CHILD' in text and 'child->forced' in text,
                'Missing bounded lifecycle/status safeguards')
        host = []
        for compiler in ('gcc', 'clang'):
            binary = work/('host-status-'+compiler)
            run(compiler+'-compile', [tools[compiler], '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-DLEASE_SMOKE_HOST_TEST', '-I'+str(direct), source, '-o', binary])
            log = run(compiler+'-host-status', [binary])
            require(log.strip() == 'LEASE_SMOKE_HOST_PASS cases=11 wait_checks=720896',
                    'Incomplete exact wait-status/phase classifier checks')
            host.append(dict(compiler=compiler, state='PASS', wait_checks=720896, cases=11))
        spec = importlib.util.spec_from_file_location('sealed_scalar_auditor', inputs/REL/'test_client.py')
        auditor = importlib.util.module_from_spec(spec); spec.loader.exec_module(auditor)
        client_obj, smoke_obj = work/'direct_client.o', work/'lease_smoke.o'
        for label, src, obj, arch in (('client', direct/'direct_client.c', client_obj, plan['client_arch']),
                                      ('smoke', source, smoke_obj, plan['smoke_arch'])):
            run(label+'-compile', [tools['rvcc'], *plan['common_cflags'], '-march='+arch,
                '-I'+str(direct), '-MD', '-MF', obj.with_suffix('.d'), '-c', src, '-o', obj])
        client_audit = {name: auditor.audit_instructions(code)
                        for name, code in auditor.executable_sections(client_obj.read_bytes()).items()}
        custom = 0; setup_sections = []; scalar_sections = []
        for name, code in auditor.executable_sections(smoke_obj.read_bytes()).items():
            if name.startswith('.text.warm_'):
                require(not any(size == 4 and word & 0x7f in (0x0b, 0x2b, 0x5b, 0x7b)
                                for size, word in instructions(code)), 'Custom instruction in warmup')
                setup_sections.append(name); continue
            if name == '.text.gate_info':
                for size, word in instructions(code):
                    if size == 4 and word & 0x7f in (0x0b, 0x2b, 0x5b, 0x7b):
                        require(word & 0xfff0707f == 0x405b, 'Only INFO, never compute, is permitted')
                        custom += 1
                    else:
                        auditor.audit_instructions(word.to_bytes(size, 'little'))
                continue
            auditor.audit_instructions(code); scalar_sections.append(name)
        require(custom == 1 and any('warm_f' in name for name in setup_sections) and
                any('warm_rvv' in name for name in setup_sections), 'Missing explicit INFO/RVV/F probes')
        run('client-disassembly', [tools['objdump'], '-dr', client_obj])
        run('smoke-disassembly', [tools['objdump'], '-dr', smoke_obj])
        elf = out/'lease_smoke.elf'
        run('static-link', [tools['rvcc'], '-march='+plan['smoke_arch'], '-mabi=lp64d',
            *plan['link_flags'], '-Wl,-Map='+str(out/'lease_smoke.map'), client_obj, smoke_obj, '-o', elf])
        headers = run('elf-headers', [tools['readelf'], '-hlA', elf])
        dynamic = run('elf-dynamic', [tools['readelf'], '-d', elf])
        require('RISC-V' in headers and 'ELF64' in headers and 'INTERP' not in headers and
                'NEEDED' not in dynamic and 'There is no dynamic section' in dynamic,
                'Must be an actual static RV64 ELF')
        compiled = {}
        for dep in work.glob('*.d'):
            for path in dep.read_text().replace('\\\n', ' ').split(':', 1)[1].split():
                resolved = Path(path).resolve(strict=True)
                require(not resolved.is_relative_to(ROOT/'software'), 'Live production compiler input')
                compiled[str(resolved)] = sha(resolved)
        save(out/'compiler-input-pins.json', compiled)
        verify()
        bundle = out/'bundle'; bundle.mkdir()
        for item in (elf, out/'build_requirements.json'):
            destination = bundle/item.name
            shutil.copyfile(item, destination)
            require(sha(destination) == sha(item), 'Safety bundle copy differs')
        with (bundle/'SHA256SUMS').open('x') as stream:
            for item in sorted(bundle.iterdir()):
                if item.name != 'SHA256SUMS':
                    stream.write(sha(item)+'  '+item.name+'\n')
        report.update(state='PASS', host=host, elf=str(elf), elf_sha256=sha(elf),
            client_scalar_audit=client_audit, explicit_setup_sections=setup_sections,
            scalar_smoke_sections=len(scalar_sections), custom_instruction_sites=custom,
            link_static=True, post_pins_match=True, safety_runtime_status='NOT_RUN',
            bundle=str(bundle), bundle_checksums_sha256=sha(bundle/'SHA256SUMS'),
            required_board_argument=plan['run_argument'])
    except Exception as error:
        report['error'] = repr(error)
    save(out/'result.json', report)
    artifacts = {str(path.relative_to(out)): sha(path) for path in out.rglob('*') if path.is_file()}
    save(out/'artifact-pins.json', artifacts)
    with (out/'SHA256SUMS').open('x') as stream:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path != out/'SHA256SUMS':
                stream.write(sha(path)+'  '+str(path.relative_to(out))+'\n')
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--review-sha256', help=argparse.SUPPRESS)
    args = parser.parse_args(); out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT and
            re.fullmatch(r'resident_direct_lease_smoke_[A-Za-z0-9_-]+', out.name), 'Fresh signoff smoke output required')
    return frozen(out, args.review_sha256) if args.run else prepare(out)


if __name__ == '__main__':
    raise SystemExit(main())
