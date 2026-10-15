#!/usr/bin/env python3
"""Two authentic source prefixes: original binary proof, Host, one Spike each."""
import argparse
import ast
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
G = HERE.parent
sys.path.insert(0, str(G))
import prepare_batch as base
from audit_accepted8 import instructions, archived_window, OBJDUMP
from prepare_successor import SPIKE, symbol

C = base.CAMPAIGN
PART = C/'rvv_permute_partitions01'
SOURCE = C/'rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c'
SOURCE_SHA = 'b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca'
ORIGINAL_CC = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc')
CONFIG = {
    'e8_m4': dict(sew=8, lmul='m4', regs=4, vtype=2,
        elf_sha='498805cf438a11729e74f0ac7b74068fa5e19bbcf56318790b01afc798d18b65',
        asm_sha='118a8c9572532a2b332749165cff3cea9323a49722641dcf64b14fd501ccd774', pc=0x10600),
    'e16_m8': dict(sew=16, lmul='m8', regs=8, vtype=11,
        elf_sha='13a9b694ade91e25687108b4bf93b50ecc2d80c3a2a6fd532b269dac3b4aafcf',
        asm_sha='40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf', pc=0x1060e),
}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    with Path(path).open('x') as f:
        json.dump(obj, f, indent=2);f.write('\n')


def run(command, log, seconds=30):
    started = time.monotonic()
    with log.open('x') as f:
        result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, timeout=seconds)
    receipt = dict(command=list(map(str, command)), returncode=result.returncode,
                   elapsed_s=time.monotonic()-started, timeout_s=seconds, retries=0)
    save(log.with_suffix('.execution.json'), receipt)
    require(type(result.returncode) is int and result.returncode == 0, 'Actual nonzero: '+str(log))
    return receipt


def replace(text, old, new, expected=None):
    count = text.count(old)
    require(count > 0 and (expected is None or count == expected), 'Template anchor drift: '+old)
    return text.replace(old, new)


def render_reference(out, config, name):
    # Adapt one accepted cap512 checker, preserving its full vector/scalar oracle.
    template = G/'e8_m4_ops3_prefix66_prepare01/reference_check.py'
    text = template.read_text()
    pairs = [
        ('str(HERE.parent)', 'str(HERE.parents[1])'),
        ('VTYPE, PREDICATE_BYTES, VLENB, SETUP_VALUES,', 'VTYPE, PREDICATE_BYTES, VLENB, SETUP_VALUES, SEW, LMUL, WORD_BYTES,'),
        ('natural boundary must be66', 'natural boundary must be112'),
        ('rng & 255', 'rng & ((1 << SEW)-1)'),
        ('index & 255', 'index & ((1 << SEW)-1)'),
        ('op != 3', 'op != 2'), ('data[31]', 'data[0]'),
        ('[0,3,0,4,0,1]', '[0,2,0,6,3,3]'),
        ("x.to_bytes(1,'little')", "x.to_bytes(WORD_BYTES,'little')"),
        ("dict(sew=8, lmul='m4'", "dict(sew=SEW, lmul=LMUL"),
        ('data[0] == 185', 'data[0] == (185 if SEW == 8 else 61881)'),
        ('excluded_ops0_through2_empty_iterations=2688', 'excluded_ops0_through1_empty_iterations=1792'),
        ("NAME+'_op_3'", "NAME+'_op_2'"), ('308fbc57', '30803c57'),
        ("return list(b''.join(vectors[n].to_bytes(VLENB,'little') for n in range(first,first+LMUL_REGS)))",
         "raw = b''.join(vectors[n].to_bytes(VLENB,'little') for n in range(first,first+LMUL_REGS))\n        return [int.from_bytes(raw[i:i+WORD_BYTES], 'little') for i in range(0,len(raw),WORD_BYTES)]"),
        ("capacity_vset['insn'] == '0022f557'", "capacity_vset['insn'] == f'{VTYPE:03x}2f557'"),
        ("addresses['output']+1", "addresses['output']+WORD_BYTES"),
        ("('input',expected['input'],1), ('indices',expected['indices'],1)",
         "('input',expected['input'],WORD_BYTES), ('indices',expected['indices'],WORD_BYTES)"),
        ("('output',[91]*(CAP+2),1)", "('output',[91]*(CAP+2),WORD_BYTES)"),
        ('& 31 == 31', '& 31 == 0'), ('immediate31', 'immediate0'),
        ('actual_source31', 'actual_source0'), ("group(8)[31]", "group(8)[0]"),
        ("expected['input'][31]", "expected['input'][0]"),
        ("['immediate_unsigned'] = 31", "['immediate_unsigned'] = 0"),
        ("addresses['output']+WORD_BYTES+k", "addresses['output']+WORD_BYTES*(1+k)"),
        ("addresses['output']+(CAP+2)", "addresses['output']+WORD_BYTES*(CAP+2)"),
        ('((code>>12)&7)==4', '((code>>12)&7)==(4 if WORD_BYTES==1 else 5)'),
        ("index = address-addresses['output']", "require((address-addresses['output'])%WORD_BYTES==0, 'Aligned oracle')\n                    index = (address-addresses['output'])//WORD_BYTES"),
        ('RVV_GATHER_PREFIX_PASS sew=8 cases=66 errors=0', f'RVV_GATHER_PREFIX_PASS sew={config["sew"]} cases=112 errors=0'),
        ('RAW66', 'RAW112'), ('checks=66', 'checks=BOUND'), ('hits=66', 'hits=BOUND'),
        ('zero=66', 'zero=BOUND'),
    ]
    for old, new in pairs:
        text = replace(text, old, new)
    require('group(8)[31]' not in text and '308fbc57' not in text and 'checks=66' not in text,
            'Residual old numerical scope')
    (out/'reference_check.py').write_text(text)
    (out/'reference_delta.diff').write_text(''.join(difflib.unified_diff(
        template.read_text().splitlines(True), text.splitlines(True), fromfile=str(template), tofile='owned/reference_check.py')))
    width = config['sew']//8
    scope = f'''RUNTIME_ID = {name!r}
SEW, LMUL, LMUL_REGS, VTYPE = {config['sew']}, {config['lmul']!r}, {config['regs']}, {config['vtype']}
WORD_BYTES = {width}
CAP, BOUND, VLENB, PREDICATE_BYTES = 512, 112, 128, 128
SETUP_VALUES = 2178
RESULT_CHECKS, GUARD_CHECKS, ORACLE_LOADS = 57344, 224, 57568
MAX_RETIRED = 4000000
'''
    (out/'scope.py').write_text(scope)
    sys.path.insert(0, str(out))
    spec = importlib.util.spec_from_file_location('owned_vi0_reference', out/'reference_check.py')
    module = importlib.util.module_from_spec(spec);sys.modules[spec.name] = module;spec.loader.exec_module(module)
    return module


def host(out, prepared, name, config, gold):
    folder = out/'host';folder.mkdir()
    case = (prepared/name/'case.c').read_text()
    csr = '__asm__ volatile("csrr %0,vlenb":"=r"(max_start));'
    require(case.count(csr) == 1, 'Original vlenb Host hook')
    (folder/'case.c').write_text(case.replace(csr, 'max_start=128;')+
        '\nconst uint16_t *host_indices16(void) { return indices16; }\n')
    dtype = 'uint8_t' if config['sew'] == 8 else 'uint16_t'

    def array(label, values, typ):
        return f'static const {typ} {label}[]={{'+','.join(map(str, values))+'};\n'

    fixture = array('data', gold['input'], dtype)+array('index', gold['indices'], dtype)
    fixture += array('index16', gold['indices16'], 'uint16_t')
    fixture += array('vl_g', [r['vl'] for r in gold['rows']], 'unsigned long')
    fixture += array('start_g', [r['vstart'] for r in gold['rows']], 'unsigned long')
    fixture += array('mask_g', [x for r in gold['rows'] for x in r['predicate']], 'uint8_t')
    fixture += array('out_g', [x for r in gold['rows'] for x in r['output']], dtype)
    code = '''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
FIXTURE
typedef DTYPE word;
extern const uint16_t *host_indices16(void);
static unsigned calls,injected;
static const char *mutation="none";
static void demand(int ok){if(!ok)exit(90);}
unsigned long capacity(void){return 512;}
long replay_write(long n,long fd,long p,long len){demand(n==64 && fd==1);return fwrite((void*)p,1,len,stdout);}
static unsigned long mock(unsigned op,const void *a,const void *b,void *c,unsigned long vl,unsigned long cap,const void *m,unsigned long scalar,unsigned long start){
 demand(op==2 && calls<112 && cap==512 && scalar==0);unsigned j=calls++;
 demand(vl==vl_g[j] && start==start_g[j]);
 demand(!memcmp(a,data,sizeof(word)*512) && !memcmp(b,index,sizeof(word)*512));
 demand(!memcmp(host_indices16(),index16,1024) && !memcmp(m,mask_g+j*128,128));
 word *d=c;demand(d[-1]==91 && d[512]==91);for(unsigned i=0;i<512;++i)demand(d[i]==91);
 memcpy(d,out_g+j*512,sizeof(word)*512);
 if(!injected && strcmp(mutation,"none")){
  long at=-2;
  if(!strcmp(mutation,"guard0"))at=-1;
  if(!strcmp(mutation,"guard1"))at=512;
  if(!strcmp(mutation,"prestart") && start>0 && start<vl)at=0;
  if(!strcmp(mutation,"tail") && start<vl && vl<512)at=vl;
  if(!strcmp(mutation,"active") || !strcmp(mutation,"inactive"))for(unsigned i=start;i<vl;++i){
   int pick=(((uint8_t*)m)[i/8]>>(i%8))&1;
   if((pick&&!strcmp(mutation,"active"))||(!pick&&!strcmp(mutation,"inactive"))){at=i;break;}}
  if(!strcmp(mutation,"vstart")){injected=1;return 1;}
  if(at>=-1){d[at]^=1;injected=1;}
 }return 0;
}
FUNCTIONS
extern int ID_main(void);
int main(int argc,char **argv){if(argc==2)mutation=argv[1];int rc=ID_main();demand(calls==112 && (!strcmp(mutation,"none")||injected));printf("HOST_CALLS=%u INJECTED=%u\\n",calls,injected);return rc;}
'''
    functions = '\n'.join(f'unsigned long op_{i}(const void*a,const void*b,void*c,unsigned long d,unsigned long e,const void*f,unsigned long g,unsigned long h){{return mock({i},a,b,c,d,e,f,g,h);}}' for i in range(21))
    (folder/'shim.c').write_text(code.replace('FIXTURE', fixture).replace('DTYPE', dtype).replace('FUNCTIONS', functions).replace('ID_main', name+'_main'))
    command = ['/usr/bin/gcc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
        '-fno-tree-vectorize', f'-DSEW={config["sew"]}', '-DRESTART_PERMUTATIONS=1', '-DPERMUTE_OP_MASK=4',
        '-I'+str(prepared/name/'original'), str(folder/'case.c'), str(folder/'shim.c'), '-o', str(folder/'case.host')]
    run(command, folder/'compile.log')
    tests = []
    for mutation in ('none', 'prestart', 'active', 'inactive', 'tail', 'guard0', 'guard1', 'vstart'):
        cmd = [str(folder/'case.host'), mutation];start = time.monotonic()
        r = subprocess.run(cmd, text=True, capture_output=True, timeout=15)
        (folder/(mutation+'.log')).write_text(r.stdout+r.stderr)
        expected = 0 if mutation == 'none' else 1
        require(r.returncode == expected and 'HOST_CALLS=112' in r.stdout and
            f'RVV_GATHER_PREFIX_{"PASS" if expected==0 else "FAIL"} sew={config["sew"]} cases=112 errors=' in r.stdout,
            'Host mutation failed: '+mutation)
        tests.append(dict(mutation=mutation, actual_returncode=r.returncode, elapsed_s=time.monotonic()-start))
    save(folder/'host.json', dict(status='PASS_ORIGINAL_C_ONE_POSITIVE_SEVEN_ORACLE_MUTATIONS', tests=tests))


def prepare(kind):
    config = CONFIG[kind];out = HERE/kind
    require(not out.exists(), 'Fresh preparation only, no retry');out.mkdir()
    label = 'rvv_permute_restart_'+kind+'_ops2'
    name = 'gather_vi0_'+kind+'_prefix112'
    original_elf = PART/'release/binaries'/label
    original = out/'prepared'/name/'original';original.mkdir(parents=True)
    require(sha(SOURCE) == SOURCE_SHA and sha(original_elf) == config['elf_sha'], 'Actual source/ELF identity')
    require(sha(PART/label/'operations.S') == config['asm_sha'], 'Actual source assembly identity')
    manifest = json.loads((PART/'manifest.json').read_text())
    case, = [r for r in manifest['cases'] if r['name'] == label]
    require(case['sew'] == config['sew'] and case['lmul'] == config['lmul'] and
            case['operation_ids'] == [2] and case['configurations'] == 2688 and case['sha256'] == config['elf_sha'], 'Original case manifest')
    for src, target in [(SOURCE, 'scenario.c'), (PART/label/'operations.S', 'operations.S'),
                         (PART/label/'operations.h', 'operations.h'), (original_elf, 'original_linux.elf')]:
        shutil.copyfile(src, original/target)
    template = G/'e8_m4_ops3_prefix66_prepare01/reference_check.py'
    command_source = G/'e8_m4_ops3_prefix66_prepare01/original_linux_rebuild02/archived_command_source.txt'
    proof_source = G/'e8_m4_ops3_prefix66_prepare01/original_linux_rebuild02/proof.json'
    proof = json.loads(proof_source.read_text())
    require(proof['pins'][str(command_source)] == sha(command_source), 'Frozen authentic compiler expression')
    inputs = [SOURCE, original_elf, PART/label/'operations.S', PART/label/'operations.h',
              PART/'manifest.json', command_source, proof_source, template, Path(__file__),
              base.INTEGRATION/'prepare.py', SPIKE, ORIGINAL_CC,
              ORIGINAL_CC.with_name(ORIGINAL_CC.name+'.br_real'),
              (base.ROOT/'install/riscv-gcc/bin/riscv64-unknown-elf-gcc').resolve(strict=True),
              Path('/usr/bin/gcc').resolve(strict=True),
              G/'gather_stall_exact_trigger_review01/REPORT.md']
    inputs += [base.INTEGRATION/f for f in ('runtime.c', 'startup.S', 'replay.ld')]
    pins = {str(p): sha(p) for p in inputs};save(out/'input_pins.json', pins)
    # Derive the original Linux flags from the preserved, hash-bound generator expression.
    node = ast.parse(command_source.read_text()).body[0].value
    binary = out/'original_rebuilt.elf'
    context = dict(cross=str(ORIGINAL_CC)[:-3], sew=config['sew'], restart=True,
        directory=original, partitioned=True, ids=[2], source=original/'scenario.c',
        asm=original/'operations.S', binary=binary)
    cmd = eval(compile(ast.Expression(node.args[0]), str(command_source), 'eval'),
        {'__builtins__': {}, 'str': str, 'int': int, 'sum': sum}, context)
    version = subprocess.check_output([str(ORIGINAL_CC), '--version'], text=True, timeout=5)
    require('(Buildroot 2026.02) 14.3.0' in version, 'Exact original compiler version')
    (out/'linux_compiler_version.txt').write_text(version)
    execution = run(cmd, out/'linux_rebuild.log', 30)
    require(binary.read_bytes() == original_elf.read_bytes(), 'Original Linux binary mismatch; stop, no second compile')
    save(out/'original_binary_proof.json', dict(status='PASS_FULL_ORIGINAL_LINUX_ELF_BYTE_IDENTICAL',
        source_label=label, original_elf=str(original_elf), original_elf_sha256=config['elf_sha'],
        rebuilt_elf_sha256=sha(binary), execution=execution,
        command_expression_sha256=sha(command_source), original_generator_sha256=proof['generator_sha256']))
    sys.path.insert(0, str(base.INTEGRATION))
    spec = importlib.util.spec_from_file_location('owned_integration_adapter', base.INTEGRATION/'prepare.py')
    adapter = importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    source = SOURCE.read_text();adapted = adapter.adapt(source, name)
    ref = render_reference(out, config, name)
    port = ref.prefix(adapted, 112)
    anchor = '            ++cases;\n';a = source.index('    for(unsigned seed=')
    require(adapted[adapted.index('    for(unsigned seed='):adapted.index(anchor)+len(anchor)] == port[port.index('    for(unsigned seed='):port.index(anchor)+len(anchor)],
            'Original RNG/loops/setup/fulloracle changed')
    require('for(unsigned i=0;i<128;++i)predicate[i]=0;' in port, 'Original physical mask storage/clear')
    (original.parent/'case.c').write_text(port)
    for suffix, before, after in [('adapter', source, adapted), ('prefix', adapted, port)]:
        (out/(suffix+'.diff')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True))))
    prepared = out/'prepared'
    for f in ('runtime.c', 'startup.S', 'replay.ld'):shutil.copyfile(base.INTEGRATION/f, prepared/f)
    gold = ref.model()
    require(len(gold['rows']) == 112 and gold['rows'][-1]['tuple'] == [0, 2, 0, 6, 3, 3], 'Full first scalar block')
    require(all(r['predicate'][64:] == [0]*64 for r in gold['rows']), 'Upper physical mask zeros')
    save(out/'model.json', gold)
    host(out, prepared, name, config, gold)
    entry = dict(id=name, source_label=label, original_case=case, assembly='operations.S',
        defines=[f'SEW={config["sew"]}', 'RESTART_PERMUTATIONS=1', 'PERMUTE_OP_MASK=4'],
        pass_markers=[f'BOARD_CASE_PASS {name}', 'BOARD_REPLAY_PASS',
                      f'RVV_GATHER_PREFIX_PASS sew={config["sew"]} cases=112 errors=0'])
    provenance = dict(cases=[entry], vlen=1024, nr_lanes=4, source_label=label,
        scope='Natural first112/111 predecessors, not historical stall/full2688/Linux',
        files={str(p.relative_to(prepared)): sha(p) for p in prepared.rglob('*') if p.is_file()})
    save(prepared/'provenance.json', provenance)
    base.HERE = out
    soc = base.build(prepared, provenance, 'soc')[name]
    spike = base.build(prepared, provenance, 'spike')[name]
    rr = instructions(Path(soc['path']), name+'_op_2');sr = instructions(Path(spike['path']), name+'_op_2')
    ar = archived_window(original_elf, rr)
    require(len(rr) == 13 and [r['insn'] for r in rr] == [r['insn'] for r in sr] == [r['insn'] for r in ar]
            and ar[8]['pc'] == config['pc'] and rr[8]['insn'] == '30803c57', 'Original13 VI0 helper equivalence')
    save(out/'source_elf_proof.json', dict(source_label=label, original_routine=ar,
        soc_routine=rr, spike_routine=sr, entire_original_linux_binary_rebuild_proven=True,
        original_c_sha256=SOURCE_SHA, assembly_sha256=config['asm_sha'], original_elf_sha256=config['elf_sha']))
    reference = out/'reference';reference.mkdir()
    command_file = reference/'spike.cmd'
    command_file.write_text(f'rs 4050000\nstr {symbol(Path(spike["path"]), "replay_log", OBJDUMP)[0]:x}\nquit\n')
    cmd = [str(SPIKE), '-d', '--debug-cmd='+str(command_file), '--isa=rv64gcv_zvl1024b', '-m2',
           '--log-commits', '--log='+str(reference/'commits.log'), spike['path']]
    save(reference/'command.json', dict(command=cmd, timeout_s=120, debug_steps=4050000,
        max_firmware_retired=4000000, max_output_bytes=768*1024*1024, retries=0))
    def limit():resource.setrlimit(resource.RLIMIT_FSIZE, (768*1024*1024, 768*1024*1024))
    print(kind+' HOST8+ORIGINAL_ELF+13ASM PASS; SPIKE_ONCE', flush=True)
    started = time.monotonic()
    with (reference/'spike.log').open('x') as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=120, preexec_fn=limit)
    execution = dict(command=cmd, returncode=r.returncode, elapsed_s=time.monotonic()-started, retries=0)
    save(reference/'execution.json', execution)
    require(type(r.returncode) is int and r.returncode == 0, 'Reference actual nonzero')
    measured = ref.audit_trace(reference/'commits.log', Path(spike['path']), gold)
    save(reference/'reference.json', dict(**measured, actual_execution=execution,
        commit_sha256=sha(reference/'commits.log'), commit_bytes=(reference/'commits.log').stat().st_size,
        commit_parses=1))
    for p, digest in pins.items():require(sha(p) == digest, 'Preparation input changed: '+p)
    ready = dict(status='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT', source_label=label,
        runtime_id=name, sew=config['sew'], lmul=config['lmul'], vlenb=128, capacity=512,
        calls=112, predecessors=111, results=57344, guards=224, helpers=1456,
        setup_values_per_call=2178, physical_predicate_bytes=128,
        setup_bytes_per_call=2*512*(config['sew']//8)+1024+128+514*(config['sew']//8),
        endpoint=[0,2,0,6,3,3], soc_elf=soc, spike_elf=spike,
        actual_firmware_retired=measured['firmware_retired_to_htif_store'],
        actual_reference_elapsed_s=execution['elapsed_s'], actual_reference_returncode=r.returncode,
        reference_sha256=sha(reference/'reference.json'), host_sha256=sha(out/'host/host.json'),
        original_binary_proof_sha256=sha(out/'original_binary_proof.json'),
        source_proof_sha256=sha(out/'source_elf_proof.json'), historical_stall_closed=False,
        full2688_accepted=False, Linux_execution=False, new_DUT_runs=0)
    ready['pins'] = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
    save(out/'READY.json', ready)
    print(kind+' REFERENCE_PASS '+str(ready['actual_firmware_retired'])+' retired', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('case', choices=CONFIG)
    args = parser.parse_args()
    try:
        prepare(args.case)
    except BaseException as error:
        out = HERE/args.case
        if out.exists() and not (out/'STOPPED.json').exists():
            save(out/'STOPPED.json', dict(status='PREPARATION_FAILED_NO_RETRY', error=repr(error), new_DUT_runs=0))
        raise
