#!/usr/bin/env python3
"""One frozen host check and fixed-flags dualcompile; no reference execution."""
import difflib
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / 'source_model02/software'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
DEFS = ['-DSEW=16', '-DUNMASKED_COMPARISONS=1', '-DUNBOXED_COMPARISONS=1', '-DRESTART_COMPARISONS=0', '-DDESTINATION_KIND=0']
FLAGS = ['-Os', '-march=rv64gcv_zfh_zvfh_zvl1024b', '-mabi=lp64d', '-nostdlib', '-static',
         '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize',
         '-fno-tree-slp-vectorize', '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wall', '-Wextra',
         '-Werror', '-Wno-unused-const-variable', '-mcmodel=medany', '-ffunction-sections',
         '-fdata-sections', '-Wl,--gc-sections']

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')

def require(ok, message):
    if not ok: raise ValueError(message)

def limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

def command(argv, prefix, timeout=60, expected=0):
    argv = [str(x) for x in argv]
    save(prefix.with_suffix('.command.json'), argv)
    started = time.monotonic(); timed_out = False
    with prefix.with_suffix('.log').open('wb') as log:
        p = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, preexec_fn=limits)
        try: rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True; p.kill(); rc = p.wait()
    receipt = dict(actual_wait_exit=rc, timed_out=timed_out, elapsed_seconds=time.monotonic()-started,
                   command_sha256=sha(prefix.with_suffix('.command.json')), log_sha256=sha(prefix.with_suffix('.log')))
    save(prefix.with_suffix('.exit.json'), receipt)
    require(not timed_out and (rc == expected if expected is not None else rc != 0), 'Command outcome: '+str(prefix))
    return receipt

def main():
    out = HERE / 'run01'
    require(not out.exists(), 'Fresh one-attempt output required')
    review = ROOT.parent/'fp_compare_unboxed_full17920_source_review01/SOURCE_MODEL02_REVIEW.json'
    require(sha(review) == 'fb166f6bb61013e2ee25e426868d0125227a8c98b39a733ed4b2904d096fab2e', 'Actual independent review')
    pins = json.loads((ROOT/'source_model02/artifact_pins.json').read_text())
    pins.update(json.loads((ROOT/'source_model02/inputs_after.json').read_text()))
    for p, h in pins.items(): require(sha(Path(p)) == h, 'Reviewed source drift: '+p)
    for p in (review, Path(__file__), HERE/'host.c', CC.resolve(), Path('/usr/bin/gcc').resolve()):
        pins[str(p)] = sha(p)
    for name in ('as', 'ld', 'cc1'):
        tool = Path(subprocess.check_output([str(CC), '-print-prog-name='+name], text=True).strip()).resolve()
        require(tool.is_file(), 'Compiler tool location '+name)
        pins[str(tool)] = sha(tool)
    out.mkdir(); save(out/'inputs_before.json', pins)
    save(out/'FIXED_CONFIGURATION.json', dict(compiler=str(CC), flags=FLAGS, defines=DEFS,
         backends=['soc','spike'], source=str(SOURCE), retries=0,
         warning_note='Unused original const fixtures remain copied for provenance; suppress only unused-const-variable before either compile.',
         authorization='Parent next single compile stage; no reference/VCS authorized.'))
    host = out/'host'; host.mkdir()
    for name in ('case.c','generated_tables.h'):
        shutil.copyfile(SOURCE/name, host/name)
    core = (SOURCE/'packed_core.h').read_text()
    start, end = core.index('#define SD_AT('), core.index('#define ALL_16_SD(')
    hostcore = core[:start] + '#define SD_AT(base, offset, value) host_store(base,offset,(uint64_t)(value),8)\n#define SH_AT(base, offset, value) host_store(base,offset,(uint64_t)(value),2)\n' + core[end:]
    start, end = hostcore.index('static inline uint32_t result_and_guards'), hostcore.index('static inline unsigned packed_errors')
    hostcore = hostcore[:start] + 'static inline uint32_t result_and_guards(const void *p) {return host_lwu(p);}\n\n' + hostcore[end:]
    require(core[core.index('static inline unsigned packed_errors'):] == hostcore[hostcore.index('static inline unsigned packed_errors'):], 'Error core unchanged')
    (host/'packed_core.h').write_text(hostcore)
    (host/'core_adapter.diff').write_text(''.join(difflib.unified_diff(core.splitlines(True), hostcore.splitlines(True), fromfile='RV64', tofile='Host instrumented memory')))
    command(['/usr/bin/gcc','-O2','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-const-variable',*DEFS,
             '-I'+str(host),'-I'+str(SOURCE/'original'),HERE/'host.c','-o',host/'host'],host/'compile')
    tests = {}
    for name in ('positive','details','missing_input_store','missing_mask_store','missing_output_tail','wrong_raw_seed'):
        tests[name] = command([host/'host',name],host/name,timeout=30,expected=0 if name in ('positive','details') else -6)
        if name not in ('positive','details'):
            wanted = 'b[i] == inputs' if name == 'wrong_raw_seed' else 'event_count == 41'
            require(wanted in (host/(name+'.log')).read_text(), 'Exact Host negative cause')
    save(host/'RESULT.json',dict(status='PASS_SHORT_C_HOST_ONLY',tests=tests, helper_execution='C fixture stub, not RVV hardware', full_calls_per_positive=17920))
    binaries = {}
    for backend in ('soc','spike'):
        dest = out/backend; dest.mkdir(); elf=dest/'program.elf'
        extra = ['-DSPIKE_REFERENCE=1'] if backend=='spike' else []
        argv = [CC,*FLAGS,*DEFS,*extra,'-T',SOURCE/'replay.ld','-Wl,-Map='+str(dest/'program.map'),
                '-I'+str(SOURCE/'original'), SOURCE/'case.c',SOURCE/'original/scenario.S',SOURCE/'main.c',
                SOURCE/'startup.S',SOURCE/'runtime.c','-lgcc','-o',elf]
        command(argv,dest/'compile',timeout=120)
        command([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],dest/'disassemble')
        command([CC.with_name('riscv64-unknown-elf-nm'),'-S','-n',elf],dest/'symbols')
        command([CC.with_name('riscv64-unknown-elf-readelf'),'-l','-A',elf],dest/'layout')
        binaries[backend]=dict(path=str(elf),sha256=sha(elf))
    after={p:sha(Path(p)) for p in pins}
    require(after==pins,'Input/tool drift')
    save(out/'inputs_after.json',after)
    save(out/'RESULT.json',dict(status='DUAL_COMPILED_COST_AND_LOWERING_PENDING_NOT_REFERENCE',host='PASS',binaries=binaries,
         source_pins_unchanged=True, reference_executed=False, DUT_executed=False))
    print(json.dumps(binaries))

if __name__ == '__main__': main()
