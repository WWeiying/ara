#!/usr/bin/env python3
"""Actual FP32 linked positive-CFG proof. No execution/emulator/reference."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUN = HERE / 'execution01'
BASE = ROOT.parent / 'fp_compare_unboxed_full17920_prepare01'
NAME = 'fp_compare_unboxed_e32_mf2_full17920_main'
ELFS = {'soc': '520b652eb8a4d4dc634a17a36a9d5e71c382a4679afeb8aeb54746d18a37be73',
        'spike': '9b6f3e8fa391514816fc6731aeb8b9628d374fbe5f0e1ccb85fb6a2e929e1254'}

# Exact Spike PC ranges read from the single authorized linked artifact.
# SoC has an extra mask-base materialization, checked independently below.
BLOCKS = [
    ('entry_capacity',0xe0,0x106,1), ('return',0x118,0x134,1),
    ('fixed_initialization',0x136,0x16a,1), ('seed_initialization',0x16c,0x176,32),
    ('nonzero_mask_constant',0x178,0x178,13440), ('fresh_setup_call',0x17c,0x25e,17920),
    ('packed_result',0x260,0x298,17920), ('flags_guards_positive',0x29c,0x2d4,17920),
    ('sticky_increment',0x394,0x39c,17920), ('sticky0_fallthrough',0x3a0,0x3a0,8960),
    ('vl_mode_branch',0x3a2,0x3aa,17920), ('zero_mask_jump',0x3ae,0x3ae,4480),
    ('mode_increment',0x3ba,0x3be,8960), ('mode_initialization',0x3c2,0x3d4,8960),
    ('length_increment',0x3d6,0x3dc,2240), ('record_input_addresses',0x3e0,0x414,2240),
    ('op_increment',0x416,0x41c,320), ('op_function_selection',0x420,0x436,320),
    ('seed_increment',0x438,0x43e,32), ('summary_selection',0x442,0x44a,1),
    ('summary_calls_return',0x454,0x49c,1),
]
ZEROS = [('capacity_failure',0x10a,0x116), ('error_detail',0x2d8,0x392),
         ('badbit_popcount',0x3b0,0x3b8), ('failure_summary',0x44c,0x450)]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main():
    gen = load('fp32_generate_definition', HERE / 'generate.py')
    old = load('sealed_disassembly_parser', BASE / 'compile01/inspect_linked.py')
    base = gen.load_base()
    old.RUN = RUN  # Local module instance only; sealed source remains unchanged.
    require, save, sha = gen.require, gen.save, gen.sha
    out = HERE / 'linked_cfg01'
    out.mkdir()
    pins = json.loads((RUN / 'inputs_after.json').read_text())
    pins.update({str(p): sha(p) for p in RUN.rglob('*') if p.is_file()})
    for p in [Path(__file__), BASE / 'compile01/inspect_linked.py', HERE / 'generated01/helper_identity.json',
              HERE / 'generated01/software/generated_tables.h']:
        pins[str(p)] = sha(p)
    require(all(sha(Path(p)) == digest for p, digest in pins.items()), 'All original/generated/tool pins')
    save(out / 'inputs_before.json', pins)
    try:
        helpers = json.loads((HERE / 'generated01/helper_identity.json').read_text())['helpers']
        report = {}
        for backend in ('soc', 'spike'):
            d, code, funcs, sym, sizes = old.parse(backend)
            require(sha(d / 'program.elf') == ELFS[backend], 'Single actual linked ELF')
            blob = (d / 'program.elf').read_bytes()
            for pc, row in code.items():
                raw = bytes.fromhex(row['insn'])[::-1]
                require(base.elf_bytes(blob, pc, len(raw)) == raw, 'Disassembly/ELF crosscheck')
            helper_pcs, helper_bytes = set(), bytearray()
            for expected in helpers:
                actual = funcs[expected['name']]
                require([r['insn'] for r in actual] == expected['codes'], 'Original exact helper ' + expected['name'])
                helper_pcs.update(r['pc'] for r in actual)
                helper_bytes.extend(b''.join(bytes.fromhex(r['insn'])[::-1] for r in actual))
            require(len(helper_pcs) == 185 and len(helper_bytes) == 696, 'Original helper complete geometry')
            extra = [r for pc, r in code.items() if (r['op'].startswith('v') or
                     (len(r['insn']) == 8 and int(r['insn'],16) & 127 == 0x53)) and pc not in helper_pcs]
            require(not extra, 'No extra vector/FP code')
            body = funcs[NAME]
            bodypcs = {r['pc'] for r in body}

            def addr(offset):
                return 0x80000000 + offset - (0 if backend == 'spike' else 10 if offset <= 0x182 else 6)

            counts, ledger, zeros = Counter(), [], {}
            for label, lo, hi, n in BLOCKS:
                first, last = addr(lo), addr(hi)
                require(first in bodypcs and last in bodypcs, 'Actual range endpoints ' + label)
                pcs = [r['pc'] for r in body if first <= r['pc'] <= last]
                for pc in pcs:
                    require(pc not in counts, 'Disjoint successful ranges')
                    counts[pc] = n
                ledger.append(dict(name=label, first_pc=hex(first), last_pc=hex(last),
                                   static_instructions=len(pcs), executions=n, total=len(pcs)*n))
            for label, lo, hi in ZEROS:
                for r in body:
                    if addr(lo) <= r['pc'] <= addr(hi): zeros[r['pc']] = label
            require(bodypcs == set(counts) | set(zeros) and not set(counts) & set(zeros), 'Full successful/error CFG partition')
            anchors = {0x106:('beq','a4,a5,'),0x25e:('jalr','t2'),0x298:('bnez','a5,'),
                       0x2ba:('bne','a0,a6,'),0x2d4:('beq','t6,s0,'),0x39c:('beq','a3,a4,'),
                       0x3aa:('bne','s3,a5,'),0x3be:('beq','s3,a4,'),0x3dc:('beq','a4,t1,'),
                       0x41c:('beq','s4,a4,'),0x43e:('bne','s5,a4,'),0x44a:('beqz','s0,')}
            for offset, (op, args) in anchors.items():
                require(code[addr(offset)]['op'] == op and code[addr(offset)]['args'].startswith(args), 'Actual branch discriminator')
            taken = {addr(pc): n for pc,n in {0x106:1,0x298:0,0x2ba:0,0x2d4:17920,0x39c:8960,
                     0x3aa:13440,0x3be:2240,0x3dc:320,0x41c:32,0x43e:31,0x44a:1}.items()}
            incoming, edges = Counter({body[0]['pc']:1}), []
            for r in body:
                pc, n = r['pc'], counts.get(r['pc'],0)
                if not n: continue
                nextpc = pc + len(r['insn']) // 2
                if r['op'] == 'ret':
                    require(n == 1, 'One completed source function'); continue
                if r['op'] == 'j':
                    dests = [(int(r['args'].split()[0],16),n)]
                elif r['op'] in ('beq','bne','bnez','beqz','bltu','bgeu','blt','bge','bltz','bgez'):
                    require(pc in taken, 'Every successful conditional classified')
                    target = int(r['args'].split(',')[-1].split()[0],16)
                    dests = [(target,taken[pc]),(nextpc,n-taken[pc])]
                else:
                    dests = [(nextpc,n)]
                for dest, weight in dests:
                    require(weight >= 0 and (not weight or dest in bodypcs), 'No positive edge escapes')
                    incoming[dest] += weight
                    if weight: edges.append(dict(source=hex(pc),destination=hex(dest),executions=weight))
            require(all(incoming[pc] == counts.get(pc,0) for pc in bodypcs), 'Full instruction-level CFG flow conservation')
            stores = [r for r in body if addr(0x17c) <= r['pc'] <= addr(0x25e) and
                      r['op'] in ('sd','sh') and '(sp)' not in r['args']]
            want = [('sd','a4,%d(a5)'%o) for o in range(0,128,8)]
            for o in range(0,64,8):
                want += [('sd','a2,%d(a0)'%o),('sd',('a4' if o == 56 else 'a2')+',%d(a1)'%o)]
            want += [('sd','s1,%d(s0)'%o) for o in range(0,128,8)] + [('sh','a4,128(s0)')]
            require([(r['op'],r['args']) for r in stores] == want, '49 actual complete fresh stores')
            input_loads = [r for r in body if addr(0x1ba) <= r['pc'] <= addr(0x20e) and r['op'] == 'ld']
            want_loads = []
            for o in range(0,64,8):
                want_loads += ['a2,%d(s2)'%o, ('a4' if o == 56 else 'a2')+',%d(a4)'%o]
            require([r['args'] for r in input_loads] == want_loads, '16 input ROM LD sites')
            require(all(counts[r['pc']] == 17920 for r in stores + input_loads), 'No fresh input/output hoisting')
            require(code[addr(0x26e)]['text'] == 'lwu s0,0(s0)' and counts[addr(0x26e)] == 17920, 'Exactly one aligned output LWU per call')
            require(code[addr(0x3f2)]['text'] == 'ld s6,0(a4)' and counts[addr(0x3f2)] == 2240, '2240 immutable record LD')
            abi = {0x17c:'sd s7,56(sp)',0x17e:'sd t1,48(sp)',0x180:'sd t6,40(sp)',
                   0x260:'ld t0,56(sp)',0x262:'srli a4,s6,0x20',0x26a:'or a4,a4,t0',
                   0x288:'ld t6,40(sp)',0x28a:'ld t1,48(sp)'}
            for offset, text in abi.items(): require(code[addr(offset)]['text'] == text, 'Actual caller/live-register spill ABI')
            for helper in helpers:
                for r in funcs[helper['name']]:
                    require(not re.search(r'\bs(?:[0-9]|1[01])\b',r['args']), 'Helper respects preserved registers')
            require(body[0]['text'] == 'addi sp,sp,-224', 'Actual source frame224')
            require(funcs['main'][0]['text'] == 'addi sp,sp,-16' and funcs['num'][0]['text'] == 'addi sp,sp,-48', 'Actual wrapper/number frames')
            require(sizes['a'] == sizes['b'] == 4096 and sizes['mask'] == 128 and sizes['output'] == 130, 'Full FP32 backing objects')
            require(sizes['input_periods'] == 3072 and sizes['oracle_records'] == 17920, 'ROM geometry')
            require(all(sym[n] % 8 == 0 for n in ('a','b','mask','output','input_periods','oracle_records')), 'Eight-byte alignment')
            require(sym['__bss_end'] < sym['__stack_top'] - 65536 and sym['__stack_top'] == 0x800ffff0, '1MiB with 64KiB stack reserve')
            header = (HERE / 'generated01/software/generated_tables.h').read_text()
            vals = [int(x,16) for x in re.findall(r'UINT64_C\((0x[0-9a-f]+)\)', header)]
            require(len(vals) == 48*8 + 2240, 'Full immutable table layout')
            for name, values in [('input_periods',vals[:384]),('oracle_records',vals[384:])]:
                raw = b''.join(struct.pack('<Q',v) for v in values)
                require(base.elf_bytes(blob,sym[name],len(raw)) == raw, 'Linked immutable table byte equality')
            function_table = base.elf_bytes(blob,sym['functions'],80)
            require(list(struct.unpack('<10Q',function_table)) == [sym['op_'+str(i)] for i in range(10)], 'Original operation order/indirect call table')
            raw32_sites = []
            for op in range(4,10):
                f = funcs['op_'+str(op)]
                require(f[6]['insn'] == '0005e383' and f[7]['insn'] == 'f2038053', 'Actual raw LWU then FMV.D.X')
                raw32_sites.append(dict(op=op, lwu_pc=hex(f[6]['pc']), fmv_pc=hex(f[7]['pc']),
                                        calls=1792, scope='Static committed-writeback qualification sites; not dynamic FPR evidence'))
            bss_size = sym['__bss_end'] - sym['__bss_start']
            require(bss_size % 8 == 0, 'Exact startup BSS words')
            startup_loop = [r['text'] for r in funcs['_start'] if 0x80000042 <= r['pc'] <= 0x8000004c]
            require(startup_loop == ['bgeu t0,t1,8000004e <_start+0x4e>', 'sd zero,0(t0)', 'addi t0,t0,8', 'j 80000042 <_start+0x42>'], 'Actual four-instruction BSS loop')
            startup_upper = 4*(bss_size//8)+100
            # Successful wrappers: <256 characters, <=16 text/number invocations,
            # <=64 instructions/character including scans, buffer copies and digits.
            # Function-size and source/ELF identity gates apply to both backends.
            require(len(funcs['replay_text']) <= 32 and len(funcs['replay_write']) <= 48 and
                    len(funcs['num']) <= 32 and len(funcs['main']) <= 40, 'Bounded successful runtime structure')
            printing_upper = 256*64 + 16*128
            core = sum(counts.values())
            helper_count = 7168*17 + 10752*19 + 3
            upper = core + helper_count + startup_upper + printing_upper
            result = dict(status='COMPILED_POSITIVE_CFG_LT_3M_PENDING_INDEPENDENT_REVIEW' if upper < 3000000 else 'HOLD_COST_GE_3M',
                 elf_sha256=ELFS[backend], complete_source_calls=17920, result_bits=286720, guard_values=35840,
                 flag_samples=17920,vstart_samples=17920, blocks=ledger, CFG_edges=edges,
                 zero_positive_execution_PCs={hex(k):v for k,v in zeros.items()}, all_body_PCs_partitioned=True,
                 flow_conservation=True, disassembly_crosschecked_against_ELF=True, original_static_helpers=185,
                 original_helper_bytes=696, original_dynamic_helpers=helper_count, raw32_sites=raw32_sites,
                 fresh_stores=stores,input_LD_sites=input_loads,dynamic_fresh_stores=878080,
                 dynamic_input_LD=286720,output_LWU=17920,record_LD=2240,helper_memory_owners=89600,
                 nonempty_target_owners=15360,VL0_target_elidable=2560,total_required_owners=104960,
                 input_backing_each=4096,input_upper_zero_BSS_each=4032,packed_ROM_bytes=20992,
                 mapped_BSS_end=hex(sym['__bss_end']),used_through_BSS=sym['__bss_end']-0x80000000,
                 source_frame=224,main_frame=16,num_frame=48,normal_nested_stack=288,stack_reserved=65536,
                 actual_ABI=abi, extra_vector_FP=[],harness_positive_instructions=core,BSS_words=bss_size//8,
                 startup_upper=startup_upper,wrapper_printing_upper=printing_upper,whole_positive_upper=upper,
                 margin_to_3M=3000000-upper, original_Linux_recompiled=False,reference=False,DUT=False,
                 limitation='Conditional all-correct terminating CFG bound, not measured reference cost, DUT-cycle bound or Linux closure. Park excluded.')
            save(out / (backend+'.json'),result)
            report[backend] = {k:result[k] for k in ('status','elf_sha256','whole_positive_upper','margin_to_3M')}
        require(all(sha(Path(p)) == digest for p,digest in pins.items()), 'Audit input drift')
        save(out / 'inputs_after.json',pins)
        save(out / 'RESULT.json',dict(status='LINKED_POSITIVE_CFG_COMPLETE_PENDING_INDEPENDENT_REVIEW',
             backends=report,inputs_unchanged=True,reference=False,DUT=False))
        print(json.dumps(report),flush=True)
    except BaseException as error:
        save(out / 'FIRST_FAILURE.json',dict(type=type(error).__name__,error=str(error),reference=False,DUT=False))
        raise


if __name__ == '__main__':
    main()
