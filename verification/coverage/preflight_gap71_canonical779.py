"""One relocated gap71 fault fixture; LLVM/host/Spike only, never EDA."""
import argparse
import importlib.util
import json
from pathlib import Path
from types import FunctionType
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
spec = importlib.util.spec_from_file_location('canonical_gap71_build', ROOT / 'verification/tests/build_gap71_custom.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
audit, h = old.audit, old.helpers
need = h.require
BASE = ROOT / 'verification/out/btb-ring-admitted779-parent-20261008-01'
BASE_SHA = '299cc1cf1bd65f2f64f495c9f791c3a190ba5329e86344f035224678ccfbb9ca'
WINDOWS = {'positive': 0x1555400000, 'negative': 0xffffffeaaaa00000}
RTL = ('hardware/src/vlsu/qbs/qbs_read_engine.sv',
       'hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv',
       'hardware/src/vlsu/qbs/qbs_engine.sv', 'hardware/src/vlsu/akv/akv_engine.sv',
       'hardware/src/vlsu/vlsu.sv', 'hardware/src/ara.sv', 'hardware/src/ara_soc.sv')


def window_gate(base):
    need(type(base) is int and 0 <= base < 1 << 64 and base % (1 << 21) == 0, '2MiB window')
    need(base >> 39 == ((1 << 25) - 1 if base >> 38 & 1 else 0), 'Sv39 canonical window')
    need((base >> 30 & 511) != 2 and base + 0x3000 < 1 << 64, 'No identity-root collision or range overflow')


def driver_gate(text):
    need("assign physical_check_valid_o = plan_state_q == QBS_PLAN_TRANSLATE &&\n"
         "      !fault_pending_q && !mmu_exception_valid_i &&\n"
         "      (!en_ld_st_translation_i || mmu_valid_i);" in text, 'PMA after successful translation only')
    need('planner_fault_mmu_exception = mmu_exception_i;' in text and
         'fault_mmu_exception_q <= planner_fault_mmu_exception;' in text and
         'fault_vaddr_q <= planner_fault_vaddr;' in text, 'Complete fault address/exception producer')


def pages(base, akv, fault, window):
    window_gate(window)
    p = audit.pages(base, akv, fault)
    pointer = p[0][1]; p[0][1] = 0; p[0][window >> 30 & 511] = pointer
    pointer = p[1][0]; p[1][0] = 0; p[1][window >> 21 & 511] = pointer
    if akv:
        p[3][3:6] = [window + 0x1080, window + 0x2080, window + 0x2200]
    else:
        p[3][1] = window + 0x1080
    return p


def relocate(text, window):
    window_gate(window)
    for before, offset in (('0x40000000', 0), ('0x40001080', 0x1080),
                           ('0x40002080', 0x2080), ('0x40002200', 0x2200)):
        text = text.replace(before, hex(window + offset))
    return text


def source_data(window):
    text = relocate((ROOT / 'apps/common/gap71_data.h').read_text(), window)
    text = text.replace('p[0][1]=', 'p[0][%d]=' % (window >> 30 & 511))
    text = text.replace('p[1][0]=', 'p[1][%d]=' % (window >> 21 & 511))
    for before, relative in (('qbs_abi.h', 'apps/common/qbs_abi.h'),
                             ('../../verification/qbs/qbs_ref.h', 'verification/qbs/qbs_ref.h'),
                             ('../../software/akv/include/akv/akv_abi.h', 'software/akv/include/akv/akv_abi.h')):
        text = text.replace('"' + before + '"', '"' + str(ROOT / relative) + '"')
    return text


def recovery_word(i):
    return 0x719ac35e2608b4df ^ (i * 0x100010001) ^ 0x123456789abcdef0


def source_header(window):
    text = relocate((ROOT / 'apps/common/gap71_sv39_custom.h').read_text(), window)
    text = text.replace('static unsigned gap71_checks,gap71_errors;',
        'static volatile uint64_t canon_recovery_in[16] __attribute__((used,aligned(128)));\n'
        'static volatile uint64_t canon_recovery_out[16] __attribute__((used,aligned(128)));\n'
        'static unsigned gap71_checks,gap71_errors;')
    need(text.count('  gap71_enter();') == 1 and text.count('  G71_WRITE(satp)') == 1, 'Exact source insertion sites')
    text = text.replace('  gap71_enter();',
        '  for(unsigned i=0;i<16;i++) { canon_recovery_in[i]=gap71_seed_word(i)^UINT64_C(0x123456789abcdef0); canon_recovery_out[i]=0; }\n'
        '  gap71_enter();')
    text = text.replace('  G71_WRITE(satp)',
        '  __asm__ volatile("li t0,16\\nvsetvli zero,t0,e64,m1,tu,mu\\ncsrw vstart,zero\\n"'
        '\n    ".global canon_recovery_site\\ncanon_recovery_site: vle64.v v10,(%0)\\n"'
        '\n    "vadd.vv v11,v10,v10\\nvse64.v v11,(%1)\\n" :: "r"(canon_recovery_in),"r"(canon_recovery_out) : "t0","v10","v11","memory");\n'
        '  for(unsigned i=0;i<16;i++) gap71_check(canon_recovery_out[i]==2*canon_recovery_in[i]);\n'
        '  G71_WRITE(satp)')
    return text


def oracle(window):
    # Only address/PTE and added recovery data differ; all original trace/CSR/VRF gates remain.
    ns = dict(vars(audit))
    for name, value in vars(audit).items():
        if isinstance(value, FunctionType) and value.__module__ == audit.__name__:
            ns[name] = FunctionType(value.__code__, ns, name, value.__defaults__, value.__closure__)
    ns['pages'] = lambda base, akv, fault: pages(base, akv, fault, window)
    ns['checks'] = lambda name: audit.checks(name) + 16
    original = ns['final_memory']
    def memory(name, info):
        result = original(name, info)
        for key, multiplier in (('canon_recovery_in', 1), ('canon_recovery_out', 2)):
            result.update({info['symbols'][key] + i*8: recovery_word(i)*multiplier & audit.M64 for i in range(16)})
        return result
    ns['final_memory'] = memory
    return ns


def prepare(out, family, window_name):
    need(out.parent == ROOT / 'verification/out' and not out.exists(), 'Fresh output only')
    window = WINDOWS[window_name]; window_gate(window)
    manifest = h.read(BASE / 'admission-manifest.json')
    need(h.sha(BASE / 'admission-manifest.json') == BASE_SHA and manifest['coverage_admitted'] is True, 'Formal779 seal')
    ledger_path = BASE / 'combined-inputs.txt'
    h.verify({str(ledger_path): manifest['output_pins'][str(ledger_path)]})
    ledger = ledger_path.read_text().splitlines()
    need(len(ledger) == len(set(ledger)) == 780, 'Exact779 prefix ledger')
    book_path = ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    book = h.read(book_path)
    protected = {str(ROOT/p): book[str(ROOT/p)] for p in RTL}
    protected.update(h.pins([book_path, BASE/'admission-manifest.json', ledger_path,
        ROOT/'apps/common/gap71_data.h', ROOT/'apps/common/gap71_sv39_custom.h',
        Path(audit.__file__), ROOT/'verification/tests/build_gap71_custom.py',
        ROOT/'verification/tests/build_gap38_i8_f16_lane3.py', old.HOST, Path(__file__),
        Path(__file__).with_name('test_preflight_gap71_canonical779.py')]))
    h.verify(protected); driver_gate((ROOT / RTL[0]).read_text())
    plan_path = ROOT / 'verification/out/repaired-aligned-600-20260930-01/plan.json'
    prior = next(c for c in h.read(plan_path)['cases'] if c.get('spike'))
    spike = Path(prior['spike']); need(h.sha(spike) == prior['spike_sha256'], 'Frozen Spike')
    out.mkdir(); profile = out / 'software'; profile.mkdir()
    (profile/'gap71_data.h').write_text(source_data(window))
    (profile/'gap71_sv39_custom.h').write_text(source_header(window))
    name = 'gap71_%s_fault' % family
    main = profile/'main.c'
    main.write_text('#define GAP71_AKV %d\n#define GAP71_FAULT 1\n#define GAP71_NAME "%s"\n#include "gap71_sv39_custom.h"\n' % (family == 'akv', name))
    host = profile/'host.c'
    host.write_text(old.HOST.read_text().replace('../../apps/common/gap71_data.h', 'gap71_data.h'))
    b = h.Build(out); b.sources = dict(protected)
    b.sources.update(h.pins(profile.iterdir())); b.tools.update(h.pins([spike]))
    objs = [b.compile(host, 'host', host=True), b.compile(ROOT/'verification/qbs/qbs_ref.c', 'host-ref', host=True)]
    exe = out/'host-reference'; b.link([b.host, *objs, '-lm', '-o', exe], 'host-link')
    result = b.run([exe], 'host-reference', timeout=30)
    actual = [tuple(int(x,16) if j == 4 else int(x) for j,x in enumerate(line.split()[1:]))
              for line in result.stdout.decode().splitlines() if line.startswith('P ')]
    expected = [(a,f,p,i,v) for a in range(2) for f in range(2)
                for p,page in enumerate(pages(0x80040000,a,f,window)) for i,v in enumerate(page)]
    need(actual == expected, 'All12288 relocated host PTE/data words differ')
    q = [line for line in result.stdout.decode().splitlines() if line.startswith('Q ')]
    need(q == ['Q %d %d %08x' % (f,i,0xc0c00000 if i == 0 else 0) for f in range(2) for i in range(32)], 'Independent QBS numerical gold')
    common = [b.compile(b.common/n, 'dut-'+n) for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    dut = out/'input.elf'; obj = b.compile(main, 'dut-main')
    b.bind_sources([b.common/'link.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections','-T'+str(b.common/'link.ld'),obj,*common,'-lm','-L'+str(b.llvm/'lib/generic'),'-lclang_rt.builtins-riscv64','-o',dut], 'dut-link')
    runtime = ROOT/'apps/riscv-tests/benchmarks/common'
    extra = ['-D__SPIKE__=1','-DGAP71_SOFTWARE_REFERENCE=1','-DPREALLOCATE=1','-I'+str(runtime),'-I'+str(ROOT/'apps/riscv-tests/env'),'-fno-function-sections','-fno-data-sections']
    common = [b.compile(s,n,extra) for s,n in ((runtime/'crt.S','spike-crt'),(runtime/'syscalls.c','spike-syscalls'))]
    soft = out/'reference.elf'; obj = b.compile(main, 'reference-main', extra)
    b.bind_sources([runtime/'test.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostdlib','-T'+str(runtime/'test.ld'),obj,*common,'-o',soft], 'reference-link')
    fit = ROOT/'verification/coverage/check_elf_fit.py'
    b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',dut,'--ram-bytes','0x200000','--output',out/'elf-fit.json'], 'elf-fit')
    ns = oracle(window); metadata = {}
    for label, elf, software in (('dut',dut,False),('reference',soft,True)):
        r = b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols','--program-headers',elf],label+'-metadata')
        obj = json.loads(r.stdout)[0]; info = audit.metadata(obj,elf.read_bytes(),name,software)
        symbols = {row['Symbol']['Name']['Name']: row['Symbol']['Value'] for row in obj['Symbols']}
        info['symbols'].update({key:symbols[key] for key in ('canon_recovery_in','canon_recovery_out','canon_recovery_site')})
        metadata[label] = dict(elf=str(elf),sha256=h.sha(elf),metadata=info)
    command = [str(spike),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(soft)]
    r = b.run(command,'spike',timeout=120)
    uart = ns['validate_log'](r.stdout.decode(),name,'software-reference')
    trace = ns['spike_trace'](r.stderr.decode(),name,metadata['reference']['metadata'])
    h.verify(protected); h.verify(b.sources); h.verify(b.tools); h.verify(b.link_inputs)
    h.save(out/'preflight.json', dict(status='CANONICAL_GAP71_SOFTWARE_PREFLIGHT_PASS_NOT_DUT_QUALIFIED',
        family=family,window=hex(window),fault_address=hex(window+0x2080),formal_population=779,
        formal_manifest_sha256=BASE_SHA,baseline_ledger_sha256=h.sha(ledger_path),
        host_compared_words=12288,host_numeric_words=64,uart=uart,trace=trace,artifacts=metadata,
        input_pins=protected,source_pins=b.sources,tool_pins=b.tools,link_pins=b.link_inputs,
        output_pins=h.pins(p for p in out.iterdir() if p.is_file()),
        VCS_budget_seconds_per_fixture=600,EDA_launched=False,RTL_modified=False,
        custom_instruction_execution_verified=False,internal_drain_verified=False,
        future_native_probes=['plan_state_q==QBS_PLAN_TRANSLATE and en_ld_st_translation_i',
            'mmu_exception_valid_i with cause13 and exact tval before physical_check_valid_o',
            'planner_fault_event/fault_pending_q -> fault_valid_o only after outstanding bursts drain',
            'fault_ready_i acknowledgement, engine idle and ordinary RVV recovery completion'],
        numerical_gain_claim=None))
    print(json.dumps(dict(output=str(out),seal=h.sha(out/'preflight.json'),retired=trace['retired'],checks=uart['checks'])),flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--family',choices=('qbs','akv'),default='qbs')
    p.add_argument('--window',choices=WINDOWS,default='positive')
    args = p.parse_args(); prepare(args.output.resolve(),args.family,args.window)
