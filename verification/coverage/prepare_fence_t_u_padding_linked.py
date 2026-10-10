"""Read-only linked ELF audit and bounded run plan; never launch a simulator."""
import hashlib
import inspect
import json
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'verification/tests'))
import build_gap36_fence as legacy
import fence_rvfi_audit as rvfi

require = legacy.require
OUT = ROOT/'verification/out'
REVIEW = OUT/'fence-t-u-padding-static-agent-727-v2-20261006-01/review.json'
REVIEW_SHA = 'b7db0d745971f16654d3ed007811c627f2825fa6af574607e8137622f1fcf30f'
BUILD = OUT/'fence-t-u-padding-build-parent-727-20261006-01'
ELF_SHA = 'cfd003ebd8ee84d1e0cca8365e407e74ee4a12e4053d5cebf176f7b0406dd418'
LEGACY_SHA = '7eeac3f479e82859e9aede2949b0508c48d6dde59312d7c103d0da6c2749fc83'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''): h.update(chunk)
    return h.hexdigest()


def audit(metadata, blob):
    require(sha(Path(legacy.__file__)) == LEGACY_SHA, 'Frozen ELF auditor drift')
    source = inspect.getsource(legacy.audit_elf)
    changes = [('[symbol("gap36_fence0"), symbol("gap36_fence1")]',
                '[symbol("gap36_fence0"), symbol("gap36_fence1"), symbol("gap36_fence2")]'),
               ('range(2)', 'range(3)'), ('"canonical_custom0_sites": 2', '"canonical_custom0_sites": 3')]
    for before, after in changes:
        require(source.count(before) == 1, 'Exact three-site boundary differs')
        source = source.replace(before, after)
    namespace = dict(legacy.audit_elf.__globals__)
    exec(compile(source, __file__+':three-sites', 'exec'), namespace)
    result = namespace['audit_elf'](metadata, blob)
    code = rvfi.elf_instructions(metadata, blob)
    symbols = {s['Symbol']['Name']['Name']: s['Symbol'] for s in metadata['Symbols']}
    def pc(name): return symbols[name]['Value']
    enter, back, ecall = map(pc, ('padding_enter_mret', 'padding_return_mret', 'padding_u_ecall'))
    require(code[enter] == code[back] == 0x30200073 and code[ecall] == 0x73,
            'Exact MRET/ECALL opcodes differ')
    require(ecall == enter+20 and [code[enter+4*i] for i in range(1, 5)] == [0x13]*4,
            'Bare U must contain exactly four NOPs then ECALL')
    require(code[pc('padding_enter_u')] == 0x000062b7 and
            code[pc('padding_enter_u')+4] == 0x30029073,
            'Entry must set mstatus=0x6000 (MPP=U, FS=Dirty, interrupts off)')
    require(pc('padding_m_resume') == ecall+4 and code[ecall+4] == 0x8067,
            'Explicit M resume changed')
    handler = symbols['padding_handler']
    handler_code = [code[p] for p in sorted(code)
                    if handler['Value'] <= p < handler['Value']+handler['Size']]
    stores = [w for w in handler_code if w & 127 == 0x23]
    require(stores == [legacy.store_insn(6, 5, n) for n in (8,16,24,32,40)],
            'Exact five t1/t0 trap ledger stores differ')
    require(symbols['padding_trap']['Size'] == 56, 'Trap ledger extent differs')
    require([w for w in handler_code if w & 127 == 0x73] ==
            [0x34202373,0x34102373,0x34302373,0x30002373,
             0x30031073,0x34129073,0x30200073], 'Handler CSR/MRET sequence differs')
    obj = json.loads(subprocess.run(
        [str(ROOT/'install/riscv-llvm/bin/llvm-readobj'), '--elf-output-style=JSON',
         '--symbols', str(BUILD/'main.c.o')], check=True, capture_output=True,
        timeout=15).stdout)[0]
    app_names = [s['Symbol']['Name']['Name'] for s in obj['Symbols']
                 if s['Symbol']['Type']['Name']=='Function' and s['Symbol']['Size']>0]
    require(app_names and all(n in symbols for n in app_names), 'Missing linked app C function')
    ranges = [(symbols[n]['Value'],symbols[n]['Value']+symbols[n]['Size']) for n in app_names]
    runtime_fp = []
    for address, word in code.items():
        compressed = word & 3 != 3
        fp = ((word & 127) in (7,0x27,0x43,0x47,0x4b,0x4f,0x53)
              if not compressed else ((word >> 13) & 7 in (1,5) and word & 3 in (0,2)))
        require(not fp or not any(lo <= address < hi for lo,hi in ranges),
                'Implicit FP in app C function: '+hex(address))
        if fp: runtime_fp.append(hex(address))
    result.update(capture_stores_static=195, trap_ledger_stores_static=5,
                  bare_U_four_nops=True, precise_ecall=True, two_exact_MRETs=True,
                  no_implicit_FP_in_app_C=True, app_C_functions=app_names,
                  linked_FP_static_positions=runtime_fp,
                  linked_runtime_FP_present=True,
                  ELF_only_not_retirement_evidence=True)
    return result


def prepare(output):
    require(output.parent == OUT and not output.exists() and output.resolve() == output,
            'Fresh independent output required')
    require(sha(REVIEW) == REVIEW_SHA and sha(BUILD/'input.elf') == ELF_SHA, 'Review/ELF identity differs')
    review = json.loads(REVIEW.read_bytes())
    pins = dict(review['pins'])
    for path, digest in pins.items(): require(sha(path) == digest, 'Input drift: '+path)
    for path in (REVIEW, BUILD/'input.elf', BUILD/'elf_metadata.json', BUILD/'input.dis',
                 BUILD/'input.readelf', BUILD/'main.c.o', Path(__file__), Path(legacy.__file__),
                 ROOT/'verification/coverage/test_prepare_fence_t_u_padding_linked.py'):
        pins[str(path)] = sha(path)
    metadata = json.loads((BUILD/'elf_metadata.json').read_bytes())[0]
    proof = audit(metadata, (BUILD/'input.elf').read_bytes())
    sourcepins = json.loads((OUT/'repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
    soc = ROOT/'hardware/src/ara_soc.sv'
    pmp = ROOT/'hardware/deps/cva6/core/pmp/src/pmp.sv'
    require(sha(soc) == sourcepins[str(soc)] and sha(pmp) == sourcepins[str(pmp)], 'Frozen PMP path differs')
    require('cfg.NrPMPEntries          = 0;' in soc.read_text() and "assign allow_o = 1'b1;" in pmp.read_text(),
            'PMP0 source contract differs')
    pins[str(soc)] = sha(soc); pins[str(pmp)] = sha(pmp)
    original = OUT/'gap37-control-current-20261004-01/results/fence_t_gap36_smoke/tests/app_fence_t_gap36_smoke/work/coverage.command.json'
    pins[str(original)] = sha(original)
    argv = json.loads(original.read_bytes())['command']
    run = OUT/'fence-t-u-padding-run-parent-727-20261006-01'
    require(not run.exists(), 'Run output already exists')
    mapping = {'+PRELOAD=': str(BUILD/'input.elf'), '+TESTCASE=': 'fence_t_u_padding_successor',
               '+COMMIT_TRACE=': str(run/'commit_trace.csv')}
    for i, value in enumerate(argv):
        for prefix, replacement in mapping.items():
            if value.startswith(prefix): argv[i] = prefix+replacement
    argv[argv.index('-cm_dir')+1] = str(run/'code.vdb')
    argv[argv.index('-cm_name')+1] = 'fence_t_u_padding_successor'
    require(sha(argv[0]) == pins[argv[0]], 'Old image executable drift')
    result = dict(status='LINKED_ELF_AUDITED_RUN_NOT_LAUNCHED', ELF_sha256=ELF_SHA,
                  baseline=review['baseline'], baseline_seal=review['baseline_seal'],
                  proof=proof, PMP_entries=0, pins=pins,
                  run=dict(cwd=str(run), argv=['timeout','--signal=TERM','--kill-after=10s','600s',*argv],
                           create_fresh_cwd_only_after_parent_review=True,
                           stdout='console.log', stderr='console.log', retry=False),
                  verification=['UART legacy458+extra241', 'unfiltered RVFI including unique ECALL trap1',
                                'all retired opcodes vs ELF; three fences and 195 capture stores',
                                'five trap ledger stores and cause8/EPC/TVAL0/MPP=U',
                                'native retired CEIL CSR read vs UART; zero is not DUTFAIL',
                                'raw bitmap/protection delta relative727; no automatic admission'],
                  continuous_native_counter_available=False, exactcycleproof=False,
                  VCS_approved=False, application_approval=False)
    for path,digest in pins.items(): require(sha(path)==digest, 'Input changed before sealing')
    output.mkdir()
    (output/'review.json').write_text(json.dumps(result,indent=2)+'\n')
    seal=sha(output/'review.json')
    (output/'seal.json').write_text(json.dumps(dict(review_sha256=seal))+'\n')
    print(json.dumps(dict(output=str(output),seal=seal,pins=len(pins),sites=proof['sites'],
                         capture_stores_static=proof['capture_stores_static'])))


if __name__ == '__main__':
    require(len(sys.argv)==2, 'Only fresh output argument allowed')
    prepare(Path(sys.argv[1]).absolute())
