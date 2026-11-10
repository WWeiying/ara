#!/usr/bin/env python3
"""Exact repaired callback host checks and unchanged build admission mutations."""
import argparse
import copy
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
import build_v10 as v
import test_build_v4 as old

OUTPUT = None
COMMANDS = []
TRAP_PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <setjmp.h>
#include <stdio.h>
#define G_NORETURN _Noreturn
#define RISCV_EXCP_ILLEGAL_INST 2
typedef struct { uint32_t bins; uint64_t pc; } CPURISCVState;
typedef struct { CPURISCVState *env; uintptr_t retaddr; } AkvQemuCall;
static unsigned restores;
static uint32_t observed;
static jmp_buf trap;
static CPURISCVState *env_cpu(CPURISCVState *env) { return env; }
static void cpu_restore_state(CPURISCVState *env, uintptr_t retaddr)
{ assert(retaddr==12345); restores++; env->bins=0; env->pc=0x80000138; }
static G_NORETURN void riscv_raise_exception(CPURISCVState *env, int exception, uintptr_t retaddr)
{
    assert(exception==2);
    if(retaddr) cpu_restore_state(env,retaddr);
    assert(retaddr==0 && restores==1 && env->pc==0x80000138);
    observed=env->bins; longjmp(trap,1);
}
'''
TRAP_SUFFIX = r'''
int main(void)
{
    static const uint32_t values[]={0,0x00b5605b,0x0605705b,0xffffffff};
    for(unsigned i=0;i<4;i++) {
        CPURISCVState env={0xdeadbeef,0}; AkvQemuCall call={&env,12345}; restores=0; observed=0;
        if(!setjmp(trap)) akv_raise_illegal(&call,values[i]);
        assert(observed==values[i] && restores==1);
    }
    puts("AKV trap PASS cases=4 restore-once-before-bins=1"); return 0;
}
'''
EOC_PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint64_t hwaddr;
typedef struct { unsigned ignored; } MemTxAttrs;
typedef struct { uint64_t dram_end; } AraStage4Transport;
#define SHUTDOWN_CAUSE_GUEST_SHUTDOWN 3
#define DEVICE_LITTLE_ENDIAN 0
typedef struct {
    uint64_t (*read)(void *,hwaddr,unsigned);
    void (*write)(void *,hwaddr,uint64_t,unsigned);
    int endianness;
    struct { unsigned min_access_size,max_access_size; bool unaligned;
             bool (*accepts)(void *,hwaddr,unsigned,bool,MemTxAttrs); } valid;
    struct { unsigned min_access_size,max_access_size; } impl;
} MemoryRegionOps;
static unsigned calls; static int exit_code;
static void qemu_system_shutdown_request_with_code(int reason,int code)
{ assert(reason==SHUTDOWN_CAUSE_GUEST_SHUTDOWN); calls++; exit_code=code; }
'''
EOC_SUFFIX = r'''
int main(void)
{
    AraStage4Transport s={UINT64_C(0x81000000)}; MemTxAttrs attrs={0};
    static const unsigned sizes[]={1,2,4,8};
    static const hwaddr addresses[]={0,4,8,16,24};
    unsigned combinations=0;
    assert(ara_control_ops.valid.min_access_size==4 && ara_control_ops.valid.max_access_size==8);
    assert(ara_control_ops.impl.min_access_size==4 && ara_control_ops.impl.max_access_size==8);
    assert(!ara_control_ops.valid.unaligned);
    for(unsigned i=0;i<4;i++) for(unsigned j=0;j<5;j++) for(unsigned write=0;write<2;write++) {
        unsigned size=sizes[i]; hwaddr address=addresses[j];
        bool allowed=size>=ara_control_ops.valid.min_access_size && size<=ara_control_ops.valid.max_access_size &&
                     address%size==0 && ara_control_ops.valid.accepts(&s,address,size,write,attrs);
        bool expected=(size==8 && address%8==0) || (size==4 && write && address==0);
        assert(allowed==expected); combinations++;
        if(allowed && write) { calls=0; ara_control_ops.write(&s,address,0,size); assert(calls==(address==0)); }
    }
    const uint64_t values[]={0,1,UINT64_C(0x100000000),UINT64_MAX};
    for(unsigned i=0;i<4;i++) { calls=0; ara_control_ops.write(&s,0,values[i],8);
        assert(calls==1 && exit_code==(values[i]!=0)); }
    for(unsigned i=0;i<2;i++) { calls=0; ara_control_ops.write(&s,0,i,4); assert(calls==1 && exit_code==(int)i); }
    assert(ara_control_ops.read(&s,8,8)==UINT64_C(0x80000000));
    assert(ara_control_ops.read(&s,16,8)==s.dram_end);
    assert(ara_control_ops.read(&s,24,8)==0);
    printf("EOC PASS access-combinations=%u exit-values=6 high64-preserved=1\n",combinations); return 0;
}
'''


def execute(argv, label):
    start = time.time_ns()
    result = subprocess.run(argv, cwd=OUTPUT, capture_output=True, timeout=30,
                            env=dict(PATH='/usr/bin:/bin', LANG='C', LC_ALL='C'))
    (OUTPUT / (label + '.stdout')).write_bytes(result.stdout)
    (OUTPUT / (label + '.stderr')).write_bytes(result.stderr)
    COMMANDS.append(dict(argv=argv, cwd=str(OUTPUT), timeout=30, started_ns=start, ended_ns=time.time_ns(),
                         returncode=result.returncode, stdout_sha256=v.sha(OUTPUT / (label + '.stdout')),
                         stderr_sha256=v.sha(OUTPUT / (label + '.stderr'))))
    return result


class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        v.checked_syntax()
        cls.records, cls.payload, diff = v.repairs()
        (OUTPUT / 'adapter-repairs.patch').write_text(diff)
        v.v4.base().write_new(OUTPUT / 'adapter-repairs.json', cls.records)

    def test_exact_two_independently_syntax_checked_candidates(self):
        self.assertEqual(set(self.records), {'target/riscv/akv_helper.c', 'hw/riscv/ara_stage4.c'})
        helper = self.payload['target/riscv/akv_helper.c'].decode()
        before = (v.PARENT / 'qemu-10.2.0/target/riscv/akv_helper.c').read_text()
        expected = before.replace('    call->env->bins = tval;',
            '    cpu_restore_state(env_cpu(call->env), call->retaddr);\n    call->env->bins = tval;').replace(
            'riscv_raise_exception(call->env, RISCV_EXCP_ILLEGAL_INST, call->retaddr);',
            'riscv_raise_exception(call->env, RISCV_EXCP_ILLEGAL_INST, 0);')
        self.assertEqual(helper, expected)
        self.assertIn('akv_raise_illegal(&call, result.fault_addr);', helper)

    def test_exact_illegal_body_native_restore_order_and_zero_opcode_cases(self):
        text = self.payload['target/riscv/akv_helper.c'].decode()
        body = text[text.index('static G_NORETURN void akv_raise_illegal'):text.index('static G_NORETURN void akv_raise_access')]
        (OUTPUT / 'trap.c').write_text(TRAP_PREFIX + body + TRAP_SUFFIX)
        result = execute(['/usr/bin/gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', 'trap.c', '-o', 'trap'], 'trap-compile')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = execute([str(OUTPUT / 'trap')], 'trap')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'AKV trap PASS cases=4 restore-once-before-bins=1\n')

    def test_exact_eoc_callbacks_width_policy_and_full_64bit_exit(self):
        text = self.payload['hw/riscv/ara_stage4.c'].decode()
        read_write = text[text.index('static uint64_t ara_control_read'):text.index('static void ara_uart_write')]
        accepts_ops = text[text.index('static bool ara_control_accepts'):text.index('static const MemoryRegionOps ara_uart_ops')]
        (OUTPUT / 'eoc.c').write_text(EOC_PREFIX + read_write + accepts_ops + EOC_SUFFIX)
        result = execute(['/usr/bin/gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', 'eoc.c', '-o', 'eoc'], 'eoc-compile')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = execute([str(OUTPUT / 'eoc')], 'eoc')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'EOC PASS access-combinations=40 exit-values=6 high64-preserved=1\n')

    def test_copy_inventory_changes_exactly_two_files_and_lock_only_after(self):
        path = OUTPUT / 'not-created'
        expected = {str(path / Path(p).relative_to(v.PARENT)): row
                    for p, row in v.v4.base().read(v.PARENT / 'tree-inventory.json').items()}
        actual = v.expected_inventory(path)
        self.assertEqual(set(actual), set(expected))
        self.assertEqual({p for p in actual if actual[p] != expected[p]},
                         {str(path / 'qemu-10.2.0' / p) for p in v.PATCHES})
        self.assertEqual(set(v.expected_inventory(path, True)) - set(actual),
                         {str(path / 'qemu-10.2.0' / v.v7.LOCK)})
        self.assertEqual(actual[str(path / 'qemu-10.2.0/target/riscv/qbs_helper.c')]['sha256'], v.QBS_SHA)

    def test_repair_before_and_after_hash_mutations_rejected(self):
        for field in ('before', 'after'):
            rows = copy.deepcopy(v.PATCHES)
            rows['target/riscv/akv_helper.c'][field] = '0' * 64
            with patch.object(v, 'PATCHES', rows), self.assertRaises(ValueError):
                v.repairs()

    def fixture(self, mutation=None):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            path = Path(tmp)
            report, prepared = old.BuildTests().fixture(path)
            prepared['configure_argv'][0] = str(path / 'variant/qemu-10.2.0/configure')
            (path / 'variant/qemu-10.2.0' / v.v9.SCRATCH).mkdir(parents=True)
            report.update(schema='stage5-qemu-build-v10', prepared=str(path / 'variant'),
                          prepare_sha256='1' * 64, original_prepare_sha256=v.v7.PREPARE_SHA,
                          preflight=str(v.v5.TOOLENV), preflight_sha256=v.v5.TOOLENV_SHA,
                          predecessor_validator_sha256=v.V9_SHA, fdt_selection='internal',
                          source_review_sha256=v.identity()[1], generated_metadata_before={},
                          generated_metadata_after=v.v7.lock_metadata(path / 'variant', True),
                          generated_directories_before=v.v9.scratch_metadata(path / 'variant'),
                          generated_directories_after=v.v9.scratch_metadata(path / 'variant'))
            report['commands'][0]['argv'] = v.v5.configure_argv(prepared)
            if mutation:
                mutation(report)
            v.v4.base().write_new(path / 'build.json', report)
            with patch.object(v, 'checked_variant', return_value=prepared) as check:
                result = v.checked_build(path, v.sha(path / 'build.json'))
                check.assert_called_once_with(str(path / 'variant'), '1' * 64, after_build=True)
                return result

    def test_positive_build_receipt_uses_unchanged_flags_and_limits(self):
        self.assertEqual(self.fixture()['state'], 'BUILT_NOT_EXECUTED')
        args = v.v5.configure_argv(v.v4.base().read(v.PARENT / 'prepare.json'))
        self.assertEqual(args[-3:], ['--python=/usr/bin/python3.11', '--ninja=/usr/bin/ninja', '--enable-fdt=internal'])
        self.assertIn('--disable-download', args)

    def test_build_identity_and_generated_metadata_mutations(self):
        for key, value in (('schema', 'stage5-qemu-build-v9'), ('state', 'FAIL'),
                           ('source_review_sha256', '0' * 64), ('preflight_sha256', '0' * 64),
                           ('predecessor_validator_sha256', '0' * 64), ('executable_sha256', '0' * 64),
                           ('post_pins_match', False), ('generated_metadata_after', {}),
                           ('generated_directories_after', {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.fixture(lambda r: r.update({key: value}))

    def test_command_argv_environment_owner_timeouts_and_logs_mutations(self):
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
                self.fixture(mutate)

    def test_original_image_parent_qbs_and_failed_gate_preserved(self):
        self.assertEqual(v.sha(v.PARENT / 'prepare.json'), v.PARENT_SHA)
        self.assertEqual(v.sha(v.HERE / 'build_v9.py'), v.V9_SHA)
        self.assertEqual(v.sha(v.PARENT / 'qemu-10.2.0/target/riscv/qbs_helper.c'), v.QBS_SHA)
        self.assertEqual(v.sha(v.OUT / 'stage5_qemu_build_20261110_06/build.json'), v.BUILD06_SHA)
        self.assertEqual(v.sha(v.OUT / 'stage5_qemu_execution_20261110_01/result.json'),
                         '2db44e35049e78526923b9a13f753f80768b70a93fe7cb320c06a197d79a1f8c')

    def test_exact_empty_scratch_and_current_syntax_receipts(self):
        self.assertEqual(v.v9.scratch_metadata(v.PARENT),
                         {str(v.PARENT / 'qemu-10.2.0' / v.v9.SCRATCH): dict(kind='directory')})
        self.assertEqual(v.sha(v.SYNTAX03 / 'result.json'), v.SYNTAX03_SHA)
        self.assertEqual(v.sha(v.SYNTAX04 / 'result.json'), v.SYNTAX04_SHA)


def main():
    global OUTPUT
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    r = v.v4.base()
    OUTPUT = r.fresh(args.output, 'stage5_qemu_build_v10_host_')
    files, review = v.identity()
    report = dict(schema='stage5-qemu-build-v10-host', state='FAIL', files=files, source_review_sha256=review,
                  guest_executed=False, configure_executed=False, qemu_compiled=False)
    def expired(sig, frame):
        raise TimeoutError('180-second host bound')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        with (OUTPUT / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(RepairTests))
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        v.require(result.wasSuccessful(), 'V10 host checks failed')
        v.require(v.identity() == (files, review), 'V10 source drift')
        report['state'] = 'BUILD_V10_STATIC_HOST_PASS_NOT_BUILT'
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
