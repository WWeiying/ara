#!/usr/bin/env python3
"""Execute the captured loader prefix on frozen CVA6/Ara in controlled RAM.

No board access. This tests instruction-level reachability, not historical
board timing. No cache, MMU or pipeline signal is forced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from analyze_loader_stall import inspect_task_capture
from read_current_restore import physical
from read_stalled_task import saved_user_context
from analyze_loader_cpu_chain import run_result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('package', 'capture', 'loader', 'models', 'xpm', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--gcc', required=True)
    p.add_argument('--objcopy', required=True)
    p.add_argument('--glbl', type=Path, required=True)
    p.add_argument('--pli', type=Path, help='Verdi VCS PLI directory for bounded FSDB')
    p.add_argument('--candidate', action='store_true')
    a = p.parse_args()
    root, out = a.package.resolve(), a.out.resolve()
    report, summary = inspect_task_capture(a.capture, a.loader.read_bytes())
    if summary['loader_pc_offset'] != '0x11b4a' or summary['target_offset'] != '0xd0dc':
        raise ValueError('Only the reviewed loader prefix is supported')
    saved = saved_user_context((a.capture/'saved_kernel_stack_page.bin').read_bytes())
    if report['historical_user_context']['sp'] != hex(saved['sp']):
        raise ValueError('Saved stack pointer differs from raw frame')
    out.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    pgd = physical(int(report['pgd_va'], 16))
    entry = int(summary['loader_base'], 16) + 0x11ad0
    target = int(summary['jal_target'], 16)
    target_info = next(row for row in report['pages'] if row['label'] == 'target_page')
    root_line = int(target_info['page_walk'][0]['pa'], 16) & ~31
    memory = {}
    for row in report['reads']:
        for offset, byte in enumerate(bytes.fromhex(row['data'])):
            address = int(row['pa'], 16) + offset
            if address in memory and memory[address] != byte:
                raise ValueError('Inconsistent overlapping memory observations')
            memory[address] = byte
    boot = out/'boot.elf'
    subprocess.run([a.gcc, '-nostdlib', '-static', '-march=rv64gcv', '-mabi=lp64d',
                    '-Wl,--build-id=none,-Ttext=0x80000000,-e,_start',
                    f'-DROOT_SATP={hex((8 << 60) | (pgd >> 12))}',
                    f'-DUSER_SP={hex(saved["sp"])}', f'-DUSER_ENTRY={hex(entry)}',
                    str(here/'loader_cpu_boot.S'), '-o', str(boot)], check=True, timeout=30)
    subprocess.run([a.objcopy, '-O', 'binary', str(boot), str(out/'boot.bin')], check=True, timeout=30)
    boot_data = (out/'boot.bin').read_bytes()
    if len(boot_data) >= 4096:
        raise ValueError('Unexpected bootstrap extent')
    for offset, byte in enumerate(boot_data):
        if 0x80000000 + offset in memory:
            raise ValueError('Bootstrap overlaps captured memory')
        memory[0x80000000 + offset] = byte
    image = out/'memory.hex'
    image.write_text(''.join(f'{address:016x} {byte:02x}\n' for address, byte in sorted(memory.items())))

    manifest = json.loads((root/'manifest.json').read_text())
    board = (root/'rtl/board/ara_dsa_vcu118.sv').read_text()
    matches = re.findall(r'function automatic cheshire_cfg_t board_cfg\(\);.*?endfunction', board, re.S)
    if len(matches) != 1:
        raise ValueError('Board configuration anchor mismatch')
    (out/'loader_board_cfg.svh').write_text(matches[0] + '\n')
    files = [a.xpm.resolve(), a.glbl.resolve()]
    original_hashes = {}
    for relative in manifest['files']:
        path = root/relative
        original_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        if relative.endswith('/tc_sram_wrapper.sv'):
            contents = path.read_text()
            if contents.count('.SimInit(SimInit)') != 1:
                raise ValueError('RAM initialization anchor mismatch')
            path = out/'tc_sram_wrapper_sim.sv'
            path.write_text(contents.replace('.SimInit(SimInit)', '.SimInit("zeros")'))
        if relative.endswith('/unread.sv'):
            # Outputless lint sink: its Vivado-only workaround drives an input
            # variable, which VCS correctly rejects. Do not change the callers.
            contents = path.read_text()
            workaround = '`ifdef TARGET_VIVADO\n    logic x;\n    assign d_i = x;\n`endif'
            if contents.count(workaround) != 1:
                raise ValueError('Unread simulation compatibility anchor mismatch')
            path = out/'unread_sim.sv'
            path.write_text(contents.replace(workaround, ''))
        if relative.endswith('/cheshire_pkg.sv'):
            # VCS rejects this unpacked localparam inside a constant function.
            # An initialized automatic local has the same read-only value here.
            contents = path.read_text()
            old = "localparam int unsigned DefaultMapEntry[2] = '{0, 0};"
            if contents.count(old) != 1:
                raise ValueError('Cheshire simulation compatibility anchor mismatch')
            path = out/'cheshire_pkg_sim.sv'
            path.write_text(contents.replace(old, "int unsigned DefaultMapEntry[2] = '{0, 0};"))
        if a.candidate and relative.endswith('/wt_axi_adapter.sv'):
            old = 'axi_rd_rdy        = ~invalidate;'
            contents = path.read_text()
            if contents.count(old) != 1:
                raise ValueError('Read-ready repair anchor mismatch')
            path = out/'wt_axi_adapter_candidate.sv'
            path.write_text(contents.replace(old, 'axi_rd_rdy        = ~invalidate & ~inval_valid_i;'))
        files.append(path)
    files += [root/'rtl/cva6/core/include/instr_tracer_pkg.sv',
              root/'rtl/cva6/common/local/util/instr_tracer.sv',
              here/'loader_cpu_chain_tb.sv']
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    (out/'sources.json').write_text(json.dumps(dict(original=original_hashes, compiled=hashes), indent=2))
    summary.update(scope='full CPU/Ara, reset caches, controlled memory; not board timing',
                   initial_arguments='a0/a1/a2/a3=0, not captured live registers',
                   entry=hex(entry), sp=hex(saved['sp']), root_line=hex(root_line),
                   board_cfg_sha256=hashlib.sha256(matches[0].encode()).hexdigest())
    (out/'fixture_summary.json').write_text(json.dumps(summary, indent=2))
    command = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps', '-j8',
               '-top', 'loader_cpu_chain_tb', '-top', 'glbl',
               '+libext+.v', '-y', str(a.models.resolve())]
    command += ['+incdir+'+str(root/d) for d in manifest['include_dirs']]
    command += ['+incdir+'+str(out)]
    if a.pli:
        command += ['-debug_access+all', '-P', str(a.pli/'novas.tab'),
                    str(a.pli/'pli.a'), '+define+LOADER_FSDB']
    for key, value in dict(manifest['defines'], ARA_FPGA_HOST=None).items():
        command.append('+define+' + key + ('' if value is None else '=' + str(value)))
    filelist = out/'files.f'
    filelist.write_text(''.join('"' + str(path) + '"\n' for path in files))
    with (out/'compile.log').open('w') as log:
        compiled = subprocess.run(command + ['-f', str(filelist), '-o', 'simv', '-Mdir=csrc'],
                                  cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    if compiled.returncode:
        raise RuntimeError('Compilation failed; inspect ' + str(out/'compile.log'))
    results = []
    for collision in (0, 1):
        path = out/f'run_{collision}.log'
        with path.open('w') as log:
            run = subprocess.run([str(out/'simv'), '-no_save', f'+memory={image}',
                                  f'+entry={entry:x}', f'+target={target:x}', f'+root={root_line:x}',
                                  f'+collision={collision}', f'+wave={out}/run_{collision}.fsdb'], cwd=out, stdout=log,
                                 stderr=subprocess.STDOUT, timeout=120)
        result = dict(collision_schedule=collision, exit_code=run.returncode,
                      **run_result(path.read_text(), run.returncode, target))
        results.append(result)
        print(json.dumps(result), flush=True)
        if collision == 0 and not result['target_reached']:
            break  # A failed baseline cannot validate a collision experiment.
    (out/'results.json').write_text(json.dumps(results, indent=2))
    return 0 if all(row['target_reached'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
