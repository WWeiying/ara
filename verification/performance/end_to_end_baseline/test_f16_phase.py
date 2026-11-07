#!/usr/bin/env python3
"""Host-only source reversibility, scope, and deterministic accounting checks."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import prepare_f16_phase as p


class F16PhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.raw=p.SOURCE.read_text()

    def test_exact_source_and_renamed_control(self):
        observed,control,report=p.transform(self.raw)
        self.assertTrue(report['original_text_reversibility_checked'])
        self.assertEqual(report['nested_observation_regions'],0)
        for old,new in p.CONTROL.items():control=re.sub(r'\b'+new+r'(?=\s*\()',old,control)
        self.assertEqual(control,self.raw)
        self.assertEqual(len(re.findall(r'^akv_status_t f16_phase_execute_v2_',observed,re.M)),3)
        self.assertEqual(observed.count('#include "f16_phase_probe.h"'),1)

    def test_no_static_helper_or_other_shape_edits(self):
        observed,_,report=p.transform(self.raw)
        marker=p.SIGNATURES['with_features_native']
        prefix=observed.split('akv_status_t f16_phase_execute_v2_with_features_native(\n')[0]
        self.assertEqual(prefix.replace('#include "f16_phase_probe.h"\n',''),self.raw.split(marker)[0])
        self.assertIn('features == NULL',observed)
        self.assertIn('plan->descriptor.q_rows == 2u',observed)
        self.assertIn('problem->query_tokens == 64u',observed)
        self.assertIn('problem->query_heads == 2u*problem->kv_heads',observed)
        # Protected scope never modifies assembly kernels, expf, reductions or helper bodies.
        self.assertEqual(observed.count('__asm__'),self.raw.count('__asm__'))
        self.assertEqual(observed.count('__riscv_'),self.raw.count('__riscv_'))
        self.assertEqual(observed.count('return '),self.raw.count('return ')-10)
        self.assertTrue(all(r['occurrences'] in (1,2) for r in report['operations']))

    def test_sha_and_anchor_fail_closed(self):
        for raw in (self.raw+'\n',self.raw.replace('issue_release();','issue_release( );',1)):
            with self.assertRaisesRegex(ValueError,'SHA'):p.transform(raw)
        for raw in (self.raw.replace('  initialize_workspace(workspace, q_rows, head_dim);',''),
                    self.raw.replace('  initialize_workspace(workspace, q_rows, head_dim);',
                                     '  initialize_workspace(workspace, q_rows, head_dim);\n  initialize_workspace(workspace, q_rows, head_dim);')):
            with patch.object(p,'SOURCE_SHA',p.sha(raw.encode())):
                with self.assertRaisesRegex(ValueError,'anchor count'):p.transform(raw)

    def test_retain_calls_in_order(self):
        observed,_,_=p.transform(self.raw)
        # All source lines, except explicit return wrappers/export names, survive
        # in their original order. No math/callback/schedule statement is replaced.
        for old,new in p.NAMES.items():observed=re.sub(r'\b'+new+r'(?=\s*\()',old,observed)
        observed=re.sub(r'F16_PHASE_RETURN\(f16_scope, ([^;]+)\);',r'return \1;',observed)
        kept='\n'.join(line for line in observed.splitlines() if not (
            'F16_PHASE_SCOPE(' in line or 'F16_PHASE_SWITCH(' in line or line=='#include "f16_phase_probe.h"'))+'\n'
        self.assertEqual(kept,self.raw)

    def test_fresh_preparation_and_pins(self):
        with tempfile.TemporaryDirectory() as d,patch.object(p,'RUNS',Path(d)):
            out=Path(d)/'fresh';report=p.prepare(p.SOURCE,out)
            self.assertEqual(report['state'],'F16_PHASE_OBSERVATION_CLONES_PREPARED_NOT_BUILT_NOT_EXECUTED')
            for path,expected in report['artifacts'].items():self.assertEqual(p.sha(Path(path).read_bytes()),expected)
            pins=json.loads((out/'source-pins.json').read_text())
            for path,expected in pins.items():self.assertEqual(p.sha(Path(path).read_bytes()),expected)
            self.assertEqual((out/'native-original.c').read_bytes(),p.SOURCE.read_bytes())
            self.assertEqual(json.loads((out/'transform.json').read_text())['quote_include_flags'][-1],str(p.SOURCE.parent))
            with self.assertRaises(FileExistsError):p.prepare(p.SOURCE,out)

    def test_header_host_accounting_not_target_execution(self):
        cc=shutil.which('cc');self.assertIsNotNone(cc)
        code=r'''
#define F16_PHASE_HOST_TEST 1
#include "f16_phase_probe.h"
#include <assert.h>
typedef int akv_status_t;
uint64_t f16_phase_cycles[F16_PHASE_COUNT], f16_phase_calls[F16_PHASE_COUNT];
static uint64_t clock_value=100;
uint64_t f16_phase_test_raw(void) { return clock_value+=3; }
uint64_t f16_phase_test_drained(void) { return clock_value+=7; }
void f16_phase_reset(void) {
  for (unsigned i=0;i<F16_PHASE_COUNT;i++) { f16_phase_cycles[i]=0;f16_phase_calls[i]=0; }
}
static int marker=17;
static int return_once(void) {
  F16_PHASE_SCOPE(scope,1);
  F16_PHASE_RETURN(scope,marker++);
}
int main(void) {
  f16_phase_reset();
  f16_phase_scope_t s=f16_phase_begin(0);
  F16_PHASE_SWITCH(s,F16_PHASE_PV);f16_phase_end(&s,0);
  assert(clock_value==100);
  s=f16_phase_begin(1);
  clock_value+=20;F16_PHASE_SWITCH(s,F16_PHASE_INIT);
  clock_value+=40;F16_PHASE_SWITCH(s,F16_PHASE_QK);
  clock_value+=60;f16_phase_end(&s,0);
  uint64_t c[F16_PHASE_COUNT],n[F16_PHASE_COUNT];
  assert(f16_phase_snapshot(c,n)==0 && f16_phase_snapshot(0,n)==-1);
  uint64_t total=0;for(unsigned i=0;i<F16_PHASE_EXCLUSIVE_COUNT;i++)total+=c[i];
  assert(total==s.last-s.start && total==157);
  assert(c[F16_PHASE_BARRIER]==28 && n[F16_PHASE_BARRIER]==4);
  assert(c[F16_PHASE_PREFLIGHT]==37 && c[F16_PHASE_INIT]==50 && c[F16_PHASE_QK]==70);
  assert(n[F16_PHASE_COMPLETED]==1 && n[F16_PHASE_REJECTED]==0 && n[F16_PHASE_ERRORS]==0);
  assert(F16_PHASE_COUNT==15 && f16_phase_names[F16_PHASE_QK][0]=='q');
  f16_phase_reset();assert(return_once()==17 && marker==18);
  assert(f16_phase_calls[F16_PHASE_COMPLETED]==1 && f16_phase_calls[F16_PHASE_REJECTED]==1);
  s=f16_phase_begin(1);F16_PHASE_SWITCH(s,F16_PHASE_COUNT);f16_phase_end(&s,0);
  assert(f16_phase_calls[F16_PHASE_ERRORS]==1);
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'accounting.c';source.write_text(code)
            result=subprocess.run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(p.HERE),source,'-o',root/'accounting'],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            run=subprocess.run([root/'accounting'],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)


if __name__=='__main__':unittest.main()
