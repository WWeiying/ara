#!/usr/bin/env python3
"""Audit and execute the frozen -02 image without rebuilding or relinking."""
import json
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from accept import HERE, ROOT, BASE, ACTIVE, ACTIVE_SHA, digest, read, merge, verify, require
from check import check

PREPARED = ROOT / 'verification/out/m4-stride-rvv-repair-20261027-02'
OUT = ROOT / 'verification/out/m4-stride-rvv-repair-20261027-03'
TRAIT = 'ggml::cpu::repack::tensor_traits<block_q4_K, 1l, 32l, (ggml_type)15>'


def main():
    if OUT.exists():
        require({p.name for p in OUT.iterdir()} == {'preflight-attempt-01'}, 'Output already used')
        require(read(OUT/'preflight-attempt-01/result.json')['qemu_runs'] == 0, 'No QEMU retry')
    else:
        OUT.mkdir(parents=True)
    pins = {}
    state = dict(state='PREFLIGHT', qemu_runs=0, qemu_limit_seconds=180,
                 installed=False, recompiled=False, relinked=False, performance_measured=False,
                 rtl_changed=False, prepared_elf=str(PREPARED/'test'))

    def save(name, data):
        (OUT/name).write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')

    def pin(paths):
        merge(pins, {str(p): digest(p) for p in paths})

    def run(argv, label, limit=30, binary=None):
        argv = list(map(str, argv))
        save(label+'.command.json', dict(argv=argv, cwd=str(OUT), limit_seconds=limit))
        start = time.monotonic()
        code, timed_out = None, False
        with (OUT/(label+'.log')).open('xb') as log:
            target = binary.open('xb') if binary else log
            try:
                with subprocess.Popen(argv, cwd=OUT, stdout=target, stderr=log) as process:
                    state.update(state=label.upper(), child_pid=process.pid)
                    save('status.json', state)
                    print(label, process.pid, flush=True)
                    try:
                        code = process.wait(timeout=limit)
                    except BaseException as exc:
                        timed_out = isinstance(exc, subprocess.TimeoutExpired)
                        process.kill()
                        code = process.wait()
                        raise
            finally:
                if binary:
                    target.close()
                save(label+'.exit.json', dict(returncode=code, timed_out=timed_out,
                     host_elapsed_seconds=time.monotonic()-start, timing_scope='workflow only'))
        require(code == 0, label+' failed')

    try:
        for inventory in (PREPARED/'source-pins.json', BASE/'manifest.json', ACTIVE):
            merge(pins, read(inventory))
            pin([inventory])
        require(len(read(ACTIVE)) == 1880 and digest(ACTIVE) == ACTIVE_SHA, 'Active identity')
        pin([p for p in PREPARED.iterdir() if p.is_file()])
        first = ROOT/'verification/out/m4-stride-rvv-repair-20261027-01'
        pin([p for p in first.iterdir() if p.is_file()])
        pin([Path(__file__), HERE/'README-prepared.md'])
        archive = OUT/'preflight-attempt-01'
        if archive.exists():
            pin([p for p in archive.iterdir() if p.is_file()])
        require(read(PREPARED/'result.json')['qemu_runs'] == 0, 'Prepared execution history')
        for label in ('compile-repair', 'link', 'private-symbols', 'linked-symbols'):
            require(read(PREPARED/(label+'.exit.json'))['returncode'] == 0, label+' prerequisite')
        old_link = read(BASE/'link.command.json')['argv']
        expected = old_link[:]
        expected.insert(3, str(PREPARED/'repack.o'))
        expected[expected.index('-o')+1] = str(PREPARED/'test')
        expected = ['-Wl,-Map='+str(PREPARED/'link.map') if a.startswith('-Wl,-Map=') else a for a in expected]
        require(read(PREPARED/'link.command.json')['argv'] == expected, 'Frozen link command')
        original = (HERE.parent/'check.py').read_text()
        before = '[dict(enabled="0", path="generic", k="512")]*3'
        after = '[dict(enabled="0", path="generic", k="512")]*2 + [dict(enabled="0", path="generic", k="256")]*2'
        require(original.count(before) == 1 and (HERE/'check.py').read_text() == original.replace(before, after), 'Numerical checker drift')
        verify(pins)
        save('source-pins.json', pins)

        source = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp')
        header = Path('/home/wangwy/llama/llama.cpp/ggml/include/ggml.h')
        require(str(source) in pins and str(header) in pins, 'Source definitions unpinned')
        fragments = [
            'template <typename BLOC_TYPE, int64_t INTER_SIZE, int64_t NB_COLS, ggml_type PARAM_TYPE> class tensor_traits',
            'tensor_traits<block_q4_K, 1, 32, GGML_TYPE_Q8_K> q4_K_32x1_q8_K;',
            '__riscv_vlenb() * 8 == 1024 && cur->ne[1] % 32 == 0',
            'return &q4_K_32x1_q8_K;',
            'case GGML_OP_MUL_MAT:\n                forward_mul_mat(params, op);',
            'template <typename T> struct is_qbs_block_type : std::false_type {};',
            'ggml_gemm_q4_K_32x1_q8_K(n, s, bs, vx, vy, nr, nc);',
        ]
        for path in (source, PREPARED/'repack.cpp'):
            require(all(f in path.read_text() for f in fragments), 'Ordinary source dispatch definition')
        require('GGML_TYPE_Q8_K    = 15,' in header.read_text(), 'Enum definition')
        nm = read(PREPARED/'private-symbols.command.json')['argv'][0]
        pin([Path(nm), Path(nm).resolve()])
        run([nm, '-C', '--defined-only', PREPARED/'repack.o'], 'private-symbols')
        run([nm, '-C', '--defined-only', PREPARED/'test'], 'linked-symbols')
        for label in ('private-symbols', 'linked-symbols'):
            require((OUT/(label+'.log')).read_bytes() == (PREPARED/(label+'.log')).read_bytes(), 'Frozen symbol drift')
        mapping = (PREPARED/'link.map').read_text().splitlines()
        symbols = [TRAIT+'::compute_forward(ggml_compute_params*, ggml_tensor*)', 'vtable for '+TRAIT]
        evidence = []
        for symbol in symbols:
            for label in ('private-symbols', 'linked-symbols'):
                matches = [l for l in (OUT/(label+'.log')).read_text().splitlines() if l.split(' ', 2)[-1] == symbol]
                require(len(matches) == 1, 'Exact ordinary symbol missing: '+symbol)
            indexes = [i for i,l in enumerate(mapping) if l.strip() and l.strip().split(None, 1)[-1] == symbol]
            require(len(indexes) == 1, 'Exact map symbol missing')
            i = indexes[0]
            require(mapping[i-1].split()[-1] == str(PREPARED/'repack.o'), 'Wrong provider')
            require(int(mapping[i-1].split()[0],16) == int(mapping[i].split()[0],16), 'Provider address mismatch')
            evidence.append(dict(symbol=symbol, map_lines=mapping[i-2:i+1]))
        save('symbol-provider.json', dict(provider=str(PREPARED/'repack.o'), trait=TRAIT,
             ordinary_not_qbs=True, evidence=evidence, source=str(source), source_fragments=fragments,
             enum_definition='GGML_TYPE_Q8_K = 15', forward_mul_mat_inlined_into_compute_forward=True))

        listing = (BASE/'initramfs.list').read_text()
        require(listing.count(str(BASE/'test')) == 1, 'Original ELF entry')
        (OUT/'initramfs.list').write_text(listing.replace(str(BASE/'test'),str(PREPARED/'test')))
        cpio = read(BASE/'initramfs.command.json')['argv'][0]
        require(str(cpio) in pins, 'Unpinned initramfs tool')
        run([cpio, OUT/'initramfs.list'], 'initramfs', binary=OUT/'initramfs.cpio')
        pin([OUT/'initramfs.list', OUT/'initramfs.cpio'])
        save('manifest.json', pins)
        verify(pins)
        qemu = read(BASE/'qemu.command.json')['argv']
        require(qemu[qemu.index('-cpu')+1] == 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=false', 'QEMU CPU')
        qemu[qemu.index('-initrd')+1] = str(OUT/'initramfs.cpio')
        state['qemu_runs'] = 1
        run(qemu, 'qemu', 180)
        measured = check((OUT/'qemu.log').read_text())
        save('comparison.json', measured)
        require(measured['completed_cases'] == 4 and measured['native_qbs_calls'] == 0 and
                all(c['mismatches'] == 0 for c in measured['cases']), 'Numerical acceptance failure')
        run([sys.executable, '-B', HERE/'test_check.py', '--log', OUT/'qemu.log'], 'checker-tests')
        verify(pins)
        state.update(state='PASS', measured=measured, active_inventory_unchanged=True,
                     prepared_inputs_unchanged=True, input_sha_check_after='PASS',
                     log_sha256=digest(OUT/'qemu.log'),
                     scope='Private ordinary RVV functional acceptance only; no runtime installation, RTL or performance claim')
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        raise
    finally:
        state['child_pid'] = None
        save('status.json', state)
        save('result.json', state)
        print(json.dumps(state), flush=True)


if __name__ == '__main__':
    main()
