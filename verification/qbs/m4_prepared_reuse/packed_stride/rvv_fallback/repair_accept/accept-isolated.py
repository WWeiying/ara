#!/usr/bin/env python3
"""One bounded fork-isolated replay using the frozen private repack object."""
import difflib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from accept import HERE, ROOT, BASE, ACTIVE, ACTIVE_SHA, digest, read, merge, verify, require
from check import check

PREPARED = ROOT/'verification/out/m4-stride-rvv-repair-20261027-02'
PRIOR = ROOT/'verification/out/m4-stride-rvv-repair-20261027-03'
OUT = ROOT/'verification/out/m4-stride-rvv-repair-20261027-04'
TRAIT = 'ggml::cpu::repack::tensor_traits<block_q4_K, 1l, 32l, (ggml_type)15>'


def isolate(source):
    before = '        if (run_case(matrix[case_id][0], matrix[case_id][1], matrix[case_id][2])) {'
    after = '''        const pid_t child = fork();
        need(child >= 0, "fork_failed");
        if (child == 0) {
            std::exit(run_case(matrix[case_id][0], matrix[case_id][1], matrix[case_id][2]) ? 1 : 0);
        }
        int status = 0;
        need(waitpid(child, &status, 0) == child, "waitpid_failed");
        need(WIFEXITED(status) && WEXITSTATUS(status) <= 1, "child_failed");
        if (WEXITSTATUS(status) == 1) {'''
    prefix, main = source.split('int main() {', 1)
    require(main.count(before) == 1, 'Original main loop changed')
    result = '#include <sys/wait.h>\n#include <unistd.h>\n' + prefix + 'int main() {' + main.replace(before, after)
    require(result.split('int main() {',1)[0] == '#include <sys/wait.h>\n#include <unistd.h>\n'+prefix,
            'Non-main source changed')
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    pins = {}
    state = dict(state='PREFLIGHT', qemu_runs=0, qemu_limit_seconds=180, repack_recompiled=False,
                 installed=False, rtl_changed=False, performance_measured=False)

    def save(name, value):
        (OUT/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')

    def pin(paths):
        merge(pins, {str(p):digest(p) for p in paths})

    def run(argv, label, limit=30, binary=None):
        argv = list(map(str,argv))
        save(label+'.command.json',dict(argv=argv,cwd=str(OUT),limit_seconds=limit))
        start, code, timed_out = time.monotonic(), None, False
        with (OUT/(label+'.log')).open('xb') as log:
            target = binary.open('xb') if binary else log
            try:
                with subprocess.Popen(argv,cwd=OUT,stdout=target,stderr=log) as process:
                    state.update(state=label.upper(),child_pid=process.pid)
                    save('status.json',state)
                    print(label,process.pid,flush=True)
                    try:
                        code = process.wait(timeout=limit)
                    except BaseException as exc:
                        timed_out = isinstance(exc,subprocess.TimeoutExpired)
                        process.kill()
                        code = process.wait()
                        raise
            finally:
                if binary:
                    target.close()
                save(label+'.exit.json',dict(returncode=code,timed_out=timed_out,
                     host_elapsed_seconds=time.monotonic()-start,timing_scope='workflow only'))
        require(code == 0,label+' failed')

    try:
        for inventory in (PRIOR/'manifest.json', PRIOR/'evidence-audit/source-pins.json', ACTIVE):
            merge(pins,read(inventory))
            pin([inventory])
        pin([p for p in PRIOR.iterdir() if p.is_file()])
        pin([p for p in (PRIOR/'evidence-audit').iterdir() if p.is_file()])
        pin([Path(__file__),HERE/'README-isolated.md'])
        require(digest(ACTIVE) == ACTIVE_SHA and len(read(ACTIVE)) == 1880, 'Active identity')
        require(read(PRIOR/'numeric-audit.json')['finite_bitexact_outputs'] == 704, 'Same-process evidence')
        verify(pins)
        save('source-pins.json',pins)
        original = (HERE.parent/'test.cpp').read_text()
        candidate = isolate(original)
        (OUT/'test.cpp').write_text(candidate)
        (OUT/'driver.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),
                                     fromfile=str(HERE.parent/'test.cpp'),tofile=str(OUT/'test.cpp'))))
        parent_setup = original.split('int main() {',1)[1].split('    for (case_id =',1)[0]
        require('ggml_' not in parent_setup and 'run_case(' not in parent_setup, 'GGML initialized before fork')
        save('driver-audit.json',dict(run_case_and_all_pre_main_code_byte_identical=True,
             added_headers=['sys/wait.h','unistd.h'],only_main_loop_changed=True,
             parent_setup=parent_setup,parent_ggml_initialization=False,
             child_exit='std::exit emits each child atexit coverage',parent_wait='waitpid; stop on failure'))
        command = read(BASE/'compile-test.command.json')['argv']
        command[command.index('-c')+1] = str(OUT/'test.cpp')
        command[command.index('-o')+1] = str(OUT/'test.o')
        run(command,'compile-test',120)
        link = read(PREPARED/'link.command.json')['argv']
        require(link[2] == str(BASE/'test.o') and link[3] == str(PREPARED/'repack.o'), 'Frozen link recipe')
        link[2] = str(OUT/'test.o')
        link[link.index('-o')+1] = str(OUT/'test')
        link = ['-Wl,-Map='+str(OUT/'link.map') if a.startswith('-Wl,-Map=') else a for a in link]
        run(link,'link',120)
        nm = read(PREPARED/'private-symbols.command.json')['argv'][0]
        require(str(nm) in pins,'Unpinned symbol tool')
        run([nm,'-C','--defined-only',OUT/'test'],'linked-symbols')
        mapping = (OUT/'link.map').read_text().splitlines()
        evidence = []
        for symbol in (TRAIT+'::compute_forward(ggml_compute_params*, ggml_tensor*)','vtable for '+TRAIT):
            for path in (PREPARED/'private-symbols.log',OUT/'linked-symbols.log'):
                require(sum(l.split(' ',2)[-1] == symbol for l in path.read_text().splitlines()) == 1,'Ordinary symbol')
            indexes = [i for i,l in enumerate(mapping) if l.strip() and l.strip().split(None,1)[-1] == symbol]
            require(len(indexes) == 1,'Map symbol')
            i = indexes[0]
            require(mapping[i-1].split()[-1] == str(PREPARED/'repack.o') and
                    int(mapping[i-1].split()[0],16) == int(mapping[i].split()[0],16),'Private provider')
            evidence.append(mapping[i-2:i+1])
        save('symbol-provider.json',dict(trait=TRAIT,provider=str(PREPARED/'repack.o'),ordinary_not_qbs=True,evidence=evidence))
        listing = (BASE/'initramfs.list').read_text()
        require(listing.count(str(BASE/'test')) == 1,'ELF entry')
        (OUT/'initramfs.list').write_text(listing.replace(str(BASE/'test'),str(OUT/'test')))
        cpio = read(BASE/'initramfs.command.json')['argv'][0]
        run([cpio,OUT/'initramfs.list'],'initramfs',binary=OUT/'initramfs.cpio')
        pin([OUT/name for name in ('test.cpp','driver.patch','test.o','test','link.map','initramfs.list','initramfs.cpio')])
        save('manifest.json',pins)
        verify(pins)
        qemu = read(BASE/'qemu.command.json')['argv']
        require(qemu[qemu.index('-cpu')+1] == 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=false','QEMU CPU')
        qemu[qemu.index('-initrd')+1] = str(OUT/'initramfs.cpio')
        state['qemu_runs'] = 1
        run(qemu,'qemu',180)
        measured = check((OUT/'qemu.log').read_text())
        save('comparison.json',measured)
        require(measured['completed_cases'] == 4 and measured['native_qbs_calls'] == 0 and
                all(c['mismatches'] == 0 for c in measured['cases']),'Strict functional acceptance')
        run([sys.executable,'-B',HERE/'test_check.py','--log',OUT/'qemu.log'],'checker-tests')
        verify(pins)
        state.update(state='PASS',measured=measured,active_inventory_unchanged=True,
                     inherited_pins_unchanged=True,checker_mutations_pass=True,
                     log_sha256=digest(OUT/'qemu.log'),
                     scope='Private fork-isolated ordinary RVV functional acceptance; no installed runtime, RTL or performance claim')
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc))
        raise
    finally:
        state['child_pid'] = None
        save('status.json',state)
        save('result.json',state)
        print(json.dumps(state),flush=True)


if __name__ == '__main__':
    main()
