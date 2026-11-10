#!/usr/bin/env python3
"""Bounded real-decoder generation/routing and build admission checks."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_v9 as v
import test_build_v4 as old_tests

OUTPUT = None
COMMANDS = []
HARNESS = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef struct DisasContext { uint32_t opcode, raw; int kind, rd, rs1, rs2; } DisasContext;
static uint32_t extract32(uint32_t value, int start, int length)
{ return (value >> start) & ((UINT32_C(1) << length) - 1); }
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-parameter"
#include "generated.c.inc"
#pragma GCC diagnostic pop
static bool trans_akvinfo(DisasContext *ctx, arg_akvinfo *a)
{ ctx->kind=1; ctx->rd=a->rd; ctx->rs1=a->rs1; ctx->raw=ctx->opcode; return true; }
static bool trans_akvexec(DisasContext *ctx, arg_akvexec *a)
{ ctx->kind=2; ctx->rd=a->rd; ctx->rs1=a->rs1; ctx->rs2=a->rs2; ctx->raw=ctx->opcode; return true; }
static int check(uint32_t word, int expected)
{
    DisasContext ctx = { .opcode=word };
    bool accepted=decode_probe(&ctx, word);
    if (accepted != (expected != 0) || ctx.kind != expected) return 1;
    if (!expected) return 0;
    if (ctx.raw != word || ctx.rd != ((word >> 7) & 31) || ctx.rs1 != ((word >> 15) & 31)) return 2;
    if (expected == 2 && ctx.rs2 != ((word >> 20) & 31)) return 3;
    return 0;
}
int main(void)
{
    unsigned count=0;
    for (unsigned f7=0; f7<128; f7++) for (unsigned f3=0; f3<8; f3++)
        for (unsigned rs2=0; rs2<32; rs2++) {
            uint32_t w=(f7<<25)|(rs2<<20)|(31<<15)|(f3<<12)|(31<<7)|0x5b;
            int expected=(f3==2 || f3==3 || f3==5 || f3==6 || f3==7) ? 2 :
                         (f3==4 && f7==0 && rs2==0 ? 1 : 0);
            if (check(w,expected)) return 10;
            if (check(w ^ 0x04,0)) return 11;
            count+=2;
        }
    const uint32_t explicit_words[]={0x0605705b,0x0485705b,0x00b5605b,0x02a0605b,
        0x0000505b,0x0205745b,0x0005745b,0x0005345b,0x0405345b,0x0205345b,
        0xfe05705b,0x048570db};
    for (unsigned i=0;i<sizeof(explicit_words)/sizeof(*explicit_words);i++) {
        if (check(explicit_words[i],2)) return 12;
        count++;
    }
    printf("decoder routing PASS checks=%u raw-reserved-forwarded=1\n",count);
    return 0;
}
'''
RAM_PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <setjmp.h>
#include <stdio.h>
typedef uint64_t target_ulong;
typedef uint64_t ram_addr_t;
typedef struct CPURISCVState { int unused; } CPURISCVState;
typedef struct { CPURISCVState *env; uintptr_t retaddr; } AkvQemuCall;
typedef struct MemoryRegion { bool ram, rom; uint64_t size; } MemoryRegion;
static MemoryRegion region;
static unsigned depth, locks, lookups, probes;
static int mode;
static uint64_t region_offset;
static jmp_buf trap;
#define MIN(a,b) ((a)<(b)?(a):(b))
#define TARGET_PAGE_MASK (~UINT64_C(4095))
#define TLB_MMIO 1
#define MMU_DATA_LOAD 0
static void *env_cpu(CPURISCVState *e) { return e; }
static int cpu_mmu_index(void *c, bool x) { (void)c; (void)x; return 0; }
static target_ulong adjust_addr(CPURISCVState *e, uint64_t a) { (void)e; return a; }
static void akv_raise_access(AkvQemuCall *c, uint64_t a, size_t n)
{ (void)c; (void)a; (void)n; assert(depth==0); longjmp(trap,1); }
static int probe_access_flags(CPURISCVState *e, uint64_t a, size_t n,
    int t, int m, bool b, void **host, uintptr_t r)
{
    (void)e; (void)a; (void)n; (void)t; (void)m; (void)b; (void)r;
    probes++; *host=mode==7 ? NULL : &region;
    return mode==6 ? TLB_MMIO : mode==8 ? 4 : 0;
}
static void rcu_read_lock(void) { assert(depth==0); depth++; locks++; }
static void rcu_read_unlock(void) { assert(depth==1); depth--; }
static MemoryRegion *memory_region_from_host(void *h, ram_addr_t *o)
{ assert(depth==1 && h); lookups++; *o=region_offset; return mode==3 ? NULL : &region; }
static bool memory_region_is_ram(MemoryRegion *m) { assert(depth==1); return m->ram; }
static bool memory_region_is_rom(MemoryRegion *m) { assert(depth==1); return m->rom; }
static uint64_t memory_region_size(MemoryRegion *m) { assert(depth==1); return m->size; }
'''
RAM_SUFFIX = r'''
static int run(int m, bool ram, bool rom, uint64_t size, uint64_t offset,
               uint64_t address, size_t bytes, bool fails, unsigned expected_probes,
               unsigned expected_locks)
{
    CPURISCVState env={0}; AkvQemuCall call={&env,0};
    region=(MemoryRegion){ram,rom,size}; region_offset=offset; mode=m;
    depth=locks=lookups=probes=0;
    bool fault=setjmp(trap)!=0;
    if (!fault && !akv_ram_probe(&call,address,bytes)) return 1;
    if (fault!=fails || depth || probes!=expected_probes || locks!=expected_locks || lookups!=locks) return 2;
    return 0;
}
int main(void)
{
    const struct { int mode; bool ram,rom; uint64_t size,offset,address; size_t bytes;
                   bool fails; unsigned probes,locks; } cases[]={
        {0,1,0,4096,0,0x1000,64,0,1,1},
        {8,1,0,4096,0,0x1000,64,0,1,1},
        {0,1,1,4096,0,0x1000,64,1,1,1},
        {0,0,0,4096,0,0x1000,64,1,1,1},
        {3,1,0,4096,0,0x1000,64,1,1,1},
        {0,1,0,4096,4096,0x1000,1,1,1,1},
        {0,1,0,4096,4032,0x1000,64,0,1,1},
        {0,1,0,4096,4033,0x1000,64,1,1,1},
        {0,1,0,4096,UINT64_MAX,0x1000,64,1,1,1},
        {7,1,0,4096,0,0x1000,64,1,1,0},
        {6,1,0,4096,0,0x1000,64,1,1,0},
        {0,1,0,4096,0,0x1ff0,32,0,2,2},
        {0,1,0,4096,0,0x1000,0,0,0,0},
        {0,1,0,4096,0,UINT64_MAX-3,8,1,0,0},
    };
    for (unsigned i=0;i<sizeof(cases)/sizeof(*cases);i++) {
        if (run(cases[i].mode,cases[i].ram,cases[i].rom,cases[i].size,cases[i].offset,
                cases[i].address,cases[i].bytes,cases[i].fails,cases[i].probes,cases[i].locks)) return 10+i;
    }
    puts("RAM probe PASS cases=14 unlock-before-trap=1");
    return 0;
}
'''


def command(argv, name):
    start = time.time_ns()
    result = subprocess.run(argv, cwd=OUTPUT, capture_output=True, timeout=30,
                            env=dict(PATH='/usr/bin:/bin', LANG='C', LC_ALL='C', PYTHONNOUSERSITE='1'))
    (OUTPUT / (name + '.stdout')).write_bytes(result.stdout)
    (OUTPUT / (name + '.stderr')).write_bytes(result.stderr)
    COMMANDS.append(dict(argv=argv, cwd=str(OUTPUT), timeout=30, started_ns=start, ended_ns=time.time_ns(),
                         returncode=result.returncode, stdout_sha256=v.sha(OUTPUT / (name + '.stdout')),
                         stderr_sha256=v.sha(OUTPUT / (name + '.stderr'))))
    return result


class DecoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = v.PARENT / 'qemu-10.2.0'
        generator = source / 'scripts/decodetree.py'
        v.require(v.sha(generator) == v.GENERATOR_SHA, 'Real decoder generator drift')
        cls.before = (source / v.REPAIR_PATH).read_bytes()
        cls.after = v.repaired(cls.before)
        (OUTPUT / 'before.decode').write_bytes(cls.before)
        (OUTPUT / 'after.decode').write_bytes(cls.after)
        cls.negative = command(['/usr/bin/python3.11', '-B', str(generator),
            '--static-decode=decode_probe', '-o', 'negative.c.inc', 'before.decode'], 'negative')
        cls.positive = command(['/usr/bin/python3.11', '-B', str(generator),
            '--static-decode=decode_probe', '-o', 'generated.c.inc', 'after.decode'], 'positive')

    def test_old_real_generator_rejected_exact_missing_bits(self):
        self.assertNotEqual(self.negative.returncode, 0)
        self.assertIn(b'bits left unspecified  (0xfe000000)', self.negative.stderr)

    def test_new_real_generator_and_native_dispatch_all_funct7(self):
        self.assertEqual(self.positive.returncode, 0, self.positive.stderr)
        (OUTPUT / 'routing.c').write_text(HARNESS)
        compiled = command(['/usr/bin/gcc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-sign-compare', 'routing.c', '-o', 'routing'], 'compile')
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        result = command([str(OUTPUT / 'routing')], 'routing')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'decoder routing PASS checks=65548 raw-reserved-forwarded=1\n')

    def test_exact_five_pattern_only_patch_and_mutations(self):
        changes = [(a, b) for a, b in zip(self.before.splitlines(), self.after.splitlines()) if a != b]
        self.assertEqual(len(changes), 5)
        for a, b in changes:
            self.assertEqual(b, a.replace(b'.......', b'-------', 1))
        for bad in (self.after, self.before + b' ', self.before.replace(b'.......', b'0000000', 1)):
            with self.assertRaises(ValueError):
                v.repaired(bad)

    def test_inventory_two_source_changes_and_exact_post_lock(self):
        parent = v.v4.base().read(v.PARENT / 'tree-inventory.json')
        path = OUTPUT / 'not-created'
        expected = {str(path / Path(p).relative_to(v.PARENT)): row for p, row in parent.items()}
        expected[str(path / 'qemu-10.2.0' / v.SCRATCH)] = dict(kind='directory')
        actual = v.expected_inventory(path)
        self.assertEqual(set(actual), set(expected))
        self.assertEqual({p for p in actual if actual[p] != expected[p]},
                         {str(path / 'qemu-10.2.0' / p) for p in (v.REPAIR_PATH, v.RAM_PATH)})
        self.assertEqual(set(v.expected_inventory(path, True)) - set(actual),
                         {str(path / 'qemu-10.2.0' / v.v7.LOCK)})

    def build_fixture(self, mutation=None):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            path = Path(tmp)
            report, prepared = old_tests.BuildTests().fixture(path)
            prepared['configure_argv'][0] = str(path / 'variant/qemu-10.2.0/configure')
            report.update(schema='stage5-qemu-build-v9', prepared=str(path / 'variant'),
                          prepare_sha256='1' * 64, original_prepare_sha256=v.v7.PREPARE_SHA,
                          preflight=str(v.v5.TOOLENV), preflight_sha256=v.v5.TOOLENV_SHA,
                          predecessor_validator_sha256=v.V8_SHA, fdt_selection='internal',
                          source_review_sha256=v.identity()[1], generated_metadata_before={},
                          generated_metadata_after=v.v7.lock_metadata(path / 'variant', True))
            scratch = path / 'variant/qemu-10.2.0' / v.SCRATCH
            scratch.mkdir(parents=True)
            report.update(generated_directories_before=v.scratch_metadata(path / 'variant'),
                          generated_directories_after=v.scratch_metadata(path / 'variant'))
            report['commands'][0]['argv'] = v.v5.configure_argv(prepared)
            if mutation:
                mutation(report)
            v.v4.base().write_new(path / 'build.json', report)
            with patch.object(v, 'checked_variant', return_value=prepared) as check:
                result = v.checked_build(path, v.sha(path / 'build.json'))
                check.assert_called_once_with(str(path / 'variant'), '1' * 64, after_build=True)
                return result

    def test_positive_build_and_retained_environment_flags(self):
        self.assertEqual(self.build_fixture()['state'], 'BUILT_NOT_EXECUTED')
        args = v.v5.configure_argv(v.v4.base().read(v.PARENT / 'prepare.json'))
        self.assertEqual(args[-3:], ['--python=/usr/bin/python3.11', '--ninja=/usr/bin/ninja', '--enable-fdt=internal'])
        self.assertIn('--disable-download', args)

    def test_build_identity_and_generated_metadata_mutations(self):
        for key, value in (('schema', 'stage5-qemu-build-v8'), ('state', 'FAIL'),
                           ('source_review_sha256', '0' * 64), ('preflight_sha256', '0' * 64),
                           ('predecessor_validator_sha256', '0' * 64), ('executable_sha256', '0' * 64),
                           ('post_pins_match', False), ('generated_metadata_after', {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.build_fixture(lambda r: r.update({key: value}))
        with self.assertRaises(ValueError):
            self.build_fixture(lambda r: r.update(generated_directories_after={}))

    def test_argv_environment_owner_and_command_mutations(self):
        for mutate in (lambda r: r['commands'][0]['argv'].pop(),
                       lambda r: r['commands'][1]['argv'].__setitem__(1, '-j8'),
                       lambda r: r['commands'][0].update(timeout=901),
                       lambda r: r['commands'][0].update(cwd='/wrong'),
                       lambda r: r['commands'][1].update(returncode=1),
                       lambda r: r['commands'][0].update(log_sha256='0' * 64),
                       lambda r: r['environment'].update(LD_PRELOAD='/bad'),
                       lambda r: r['service_owner'].update(main_pid=0),
                       lambda r: r['commands'].pop()):
            with self.assertRaises(ValueError):
                self.build_fixture(mutate)

    def test_old_failure_and_frozen_parent_unchanged(self):
        self.assertEqual(v.sha(v.PARENT / 'prepare.json'), v.PARENT_SHA)
        self.assertEqual(v.sha(v.HERE / 'build_v8.py'), v.V8_SHA)
        self.assertEqual(v.sha(v.OUT / 'stage5_qemu_build_20261110_05/build.json'), v.FAIL05_SHA)
        self.assertEqual((v.PARENT / 'qemu-10.2.0' / v.REPAIR_PATH).read_bytes(), self.before)

    def test_translator_raw_opcode_and_resident_fields_not_changed(self):
        source = (v.PARENT / 'qemu-10.2.0/target/riscv/insn_trans/trans_xaraakv.c.inc').read_text()
        self.assertIn('tcg_constant_i32(ctx->opcode)', source)
        self.assertIn('funct7 == 2 || funct7 == 3', source)
        self.assertEqual(self.after.count(b'akvexec    -------'), 5)
        self.assertIn(b'akvinfo    0000000 00000', self.after)

    def test_ram_patch_matches_actual_qemu_syntax_review(self):
        row, after, diff = v.ram_record()
        self.assertEqual(row['after_sha256'], v.RAM_AFTER)
        self.assertEqual(after, (v.SYNTAX / 'inputs/akv_helper.c').read_bytes())
        self.assertEqual(v.sha(v.SYNTAX / 'result.json'), v.SYNTAX_SHA)
        self.assertEqual(v.v4.base().read(v.SYNTAX / 'result.json')['returncode'], 0)
        (OUTPUT / 'ram-helper.c').write_bytes(after)
        (OUTPUT / 'ram-repair.patch').write_text(diff)
        for bad in (after, (v.PARENT / 'qemu-10.2.0' / v.RAM_PATH).read_bytes() + b' '):
            with self.assertRaises(ValueError):
                v.ram_repaired(bad)

    def test_exact_repaired_ram_probe_native_contract(self):
        after = v.ram_record()[1].decode()
        body = after[after.index('static bool akv_ram_probe('):after.index('static bool akv_ram_read(')]
        self.assertEqual(body.count('rcu_read_lock();'), 1)
        self.assertEqual(body.count('rcu_read_unlock();'), 1)
        (OUTPUT / 'ram-probe.c').write_text(RAM_PREFIX + body + RAM_SUFFIX)
        result = command(['/usr/bin/gcc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                          'ram-probe.c', '-o', 'ram-probe'], 'ram-compile')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = command([str(OUTPUT / 'ram-probe')], 'ram-probe')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'RAM probe PASS cases=14 unlock-before-trap=1\n')

    def test_only_exact_empty_generated_directory_accepted(self):
        self.assertEqual(v.scratch_metadata(v.PARENT),
                         {str(v.PARENT / 'qemu-10.2.0' / v.SCRATCH): dict(kind='directory')})
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            root = Path(tmp)
            target = root / 'qemu-10.2.0' / v.SCRATCH
            with self.assertRaises(ValueError):
                v.scratch_metadata(root)
            target.mkdir(parents=True)
            self.assertEqual(v.scratch_metadata(root), {str(target): dict(kind='directory')})
            (target / 'unexpected').write_bytes(b'')
            with self.assertRaises(ValueError):
                v.scratch_metadata(root)
            (target / 'unexpected').unlink()
            target.rmdir()
            target.symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                v.scratch_metadata(root)


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    r = v.v4.base()
    OUTPUT = r.fresh(args.output, 'stage5_qemu_build_v9_host_')
    pins, review = v.identity()
    report = dict(schema='stage5-qemu-build-v9-host', state='FAIL', files=pins,
                  source_review_sha256=review, generator_sha256=v.GENERATOR_SHA,
                  parent_prepare_sha256=v.PARENT_SHA, guest_executed=False,
                  configure_executed=False, qemu_compiled=False)
    def expired(signum, frame):
        raise TimeoutError('180-second host bound')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        with (OUTPUT / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(DecoderTests))
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        v.require(result.wasSuccessful(), 'V9 host checks failed')
        v.require(v.identity() == (pins, review), 'V9 source drift')
        report['state'] = 'BUILD_V9_STATIC_HOST_PASS_NOT_BUILT'
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        signal.alarm(0)
        report.update(commands=COMMANDS, artifacts=r.tree_pins(OUTPUT))
        r.write_new(OUTPUT / 'result.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
