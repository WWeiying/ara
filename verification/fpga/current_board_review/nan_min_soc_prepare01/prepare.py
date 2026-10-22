"""Source-faithful single adapters. Software compilation only, no DUT/image build."""
import shutil
from common import *
from oracle import bitwise_oracle

ARCHIVE = CAMPAIGN / 'rvv_fp_redspecial03'
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')


def prepare_case(shape):
    c = config(shape)
    dest = HERE / shape
    dest.mkdir()
    out = dest / 'prepared'
    out.mkdir()
    manifest = read(ARCHIVE / 'manifest.json')
    original = SOURCE / 'fp_reduction_oracle.c'
    pins = {}
    for name in ('fp_reduction_oracle.c', 'fp_reduction_inputs.h', 'fp_reduction_fixture.c',
                 'fp_reduction_special.py', 'reductions.py'):
        p = SOURCE / name
        require(sha(p) == manifest['source_sha256'][name], 'original source ' + name)
        pins[str(p)] = sha(p)
    for p in (ARCHIVE / 'manifest.json', CC, OBJDUMP, SPIKE, INTEGRATION / 'prepare.py'):
        pins[str(p)] = sha(p)
    require(sha(SPIKE) == 'c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2', 'Spike identity')
    for name in ('operations.S', 'operations.h', 'fixtures.h', 'fixtures.json'):
        p = ARCHIVE / 'e32/m1' / name
        shutil.copyfile(p, out / name)
        pins[str(p)] = sha(p)
    p = ARCHIVE / 'e32/input_bits.h'
    require(sha(p) == '53fec31fda99b5f0f7d26ccfa5f3918ba3277599d5fc442904b0d07cae28ab3d', 'archived input table')
    shutil.copyfile(p, out / 'input_bits.h')
    pins[str(p)] = sha(p)
    shutil.copyfile(SOURCE / 'fp_reduction_inputs.h', out / 'fp_reduction_inputs.h')
    require(sha(out / 'operations.S') == '64859679b372c4ab1f57e7c81d27af03eb41b727314fdf764e0bd342a9d68818', 'archived helper')
    require(sha(out / 'fixtures.json') == '59bd5276e2306391784b16263818f725424392421bebc355b1db6c25cbebd53a', 'archived fixture')
    linux = ARCHIVE / 'overlay/opt/ara-tests/rvv_fp_redspecial_e32_m1'
    require(sha(linux) == '6bdf00a1600f10ebfc7a8b519bfea655d31e6b6b2b62d89f9e459d266eb597bc', 'original Linux ELF')
    pins[str(linux)] = sha(linux)
    shutil.copyfile(linux, out / 'original.elf')
    shutil.copyfile(original, out / 'original.c')
    text = original.read_text()
    anchor = '            for(unsigned sticky=0;sticky<2;++sticky){\n'
    require(text.count(anchor) == 1, 'exact selector location')
    selector = f"                if(!(scenario==1 && l==3 && mode=={c['mode']} && rm==0 && op==1 && sticky==0))continue;\n"
    selected = text.replace(anchor, anchor + selector, 1)
    require(selected.replace(selector, '', 1) == text, 'only single selector changed')
    (out / 'scenario.c').write_text(selected)
    (out / 'case.c').write_text(load_adapter().adapt(selected, c['identity']))
    pairs = fixtures(out / 'fixtures.h')
    js = read(out / 'fixtures.json')
    require('for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)' in text and
            'for(unsigned rm=0;rm<5;++rm)for(unsigned op=0;op<3;++op)' in text and
            'scenario*420+index++' in text, 'original loop nesting/fixture indexing')
    calls = [(scenario,l,mode,rm,op,sticky)
             for scenario in range(8) for l in range(7) for mode in range(4)
             for rm in range(5) for op in range(3) for sticky in range(2)]
    require(calls[c['original_call']] == (1,3,c['mode'],0,1,0) and
            c['fixture_row'] == 420+3*60+c['mode']*15+1,
            'original zero-based MIN call/fixture proof')
    expected = bitwise_oracle(c['seed_payload'], [c['seed_payload']]*3, c['mask_byte'])
    require(list(expected) == js[1][c['fixture_row']] == pairs[3360+c['fixture_row']], 'independent bitwise/fixture agreement')
    require(expected == (c['expected'], 0), 'exact original oracle')
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(INTEGRATION / name, out / name)
        pins[str(INTEGRATION / name)] = sha(INTEGRATION / name)
    ident = c['identity']
    (out / 'main.c').write_text(f'''extern int {ident}_main(void);
extern void replay_text(const char *);
int main(void) {{
 unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
 if(n!=128) {{replay_text("BOARD_VLEN_FAIL\\n"); return 2;}}
 replay_text("BOARD_CASE_BEGIN {ident}\\n");
 int status={ident}_main();
 if(status) {{replay_text("BOARD_CASE_FAIL {ident}\\n"); return status;}}
 replay_text("BOARD_CASE_PASS {ident}\\nBOARD_REPLAY_PASS\\n"); return 0;
}}
''')
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-ffreestanding',
             '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
             '-msmall-data-limit=0', '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra',
             '-Werror', '-DSEW=32', '-DCAP512=16', '-DCAP1024=32', '-I' + str(out)]
    archived = instructions(disassemble(linux))
    windows = {}
    for kind in ('soc', 'spike'):
        folder = dest / kind
        folder.mkdir()
        execute([CC, *flags, *(['-DSPIKE_REFERENCE=1'] if kind == 'spike' else []),
                 '-nostdlib', '-static', '-Wl,--build-id=none', '-Wl,--gc-sections',
                 '-Wl,-Map=' + str(folder / 'program.map'), '-T', out / 'replay.ld',
                 *[out / n for n in ('startup.S', 'runtime.c', 'main.c', 'case.c', 'operations.S')],
                 '-lgcc', '-o', folder / 'program.elf'], folder / 'compile.log')
        dis = disassemble(folder / 'program.elf')
        (folder / 'program.dis').write_text(dis)
        syms = symbols(folder / 'program.elf')
        save(folder / 'symbols.json', syms)
        ins = instructions(dis)
        windows[kind] = {}
        for name, encoding in [('op_0', '0c881c57'), ('op_1', '14881c57'), ('op_2', '1c881c57')]:
            oi, = [i for i, r in enumerate(archived) if r[1] == encoding]
            ni, = [i for i, r in enumerate(ins) if r[1] == encoding]
            a, b = archived[oi-11:oi+10], ins[ni-11:ni+10]
            require(len(b) == 21 and b[0][0] == syms[name] and
                    [r[1] for r in a] == [r[1] for r in b], 'full original 21 helper encodings')
            windows[kind][name] = {'original': a, 'new': b}
    save(dest / 'sourceproof.json', {'config': c, 'scope': 'one source single; no prefix/full Linux/parent/DUT acceptance',
         'fixture_bank': 1, 'fixture_row': c['fixture_row'], 'independent_bits_flags': list(expected),
         'original_call_zero_based': c['original_call'], 'helper_windows': windows,
         'external_pins': pins, 'prepared_pins': {str(p):sha(p) for p in out.iterdir()},
         'profile': ISA, 'limits': LIMITS, 'floating_regenerated': False,
         'source_selector_only': True, 'original_loop_tuple': list(calls[c['original_call']]),
         'selected_operation': 'op_1/vfredmin.vs/14881c57'})
    print(shape, 'SOFTWARE_COMPILED_NOT_DUT', flush=True)


if __name__ == '__main__':
    try:
        save(HERE / 'PREPARE_STARTED.json', {'shapes': SHAPES})
        for shape in SHAPES:
            prepare_case(shape)
    except BaseException as error:
        save(HERE / 'STOPPED_PREPARE.json', {'first_error': repr(error), 'no_retry': True})
        raise
