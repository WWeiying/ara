"""Exact compiled PMP fixture and full Tcl host model; no EDA in tests."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch
import qualify_csr_pmp0_native765 as m


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.i=m.instance()
        cls.c=dict(instances=[cls.i],timeout_seconds=900,population_application=False,automatic_retry=False)
        cls.text='CHECKSUM: "%s %s"\nINSTANCE: %s\n' % (
            cls.i['design_module_checksum'],cls.i['toggle_checksum'],cls.i['scope'])
        cls.text+=''.join('Toggle %s "logic %s%s"\n' % (n['name'],m.bounds(n),n['name']) for n in cls.i['targets'])
        cls.rows=[[str(k+1),n['name']+m.bounds(n),n['name']+m.bounds(n),n['name']+m.bounds(n)]
                  for k,n in enumerate(cls.i['targets']+cls.i['protected'])]

    def inventory(self,rows):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            with (out/'native_before_0.tsv').open('w',newline='') as s:
                w=csv.writer(s,delimiter='\t');w.writerow(['handle','path','meta','name']);w.writerows(rows)
            return m.inventory(out,self.c,'before',0)

    def rejected(self,text):
        with self.assertRaises(ValueError):m.parse_el(text,self.c)

    def test_exact_capacity_complement_and_ports(self):
        self.assertEqual(len(m.parse_el(self.text,self.c)),770)
        self.assertEqual(len(self.inventory(self.rows)),2077)
        self.assertEqual(len(self.i['protected']),1307)
        self.assertEqual(sum(n['portnode']!='0' for n in self.i['targets']),0)
        self.assertEqual(sum(n['name'].startswith('pmpcfg_d[') for n in self.i['protected']),384)

    def test_prefix_and_suffix_multidimensional_types(self):
        text=self.text
        for n in self.i['targets']:
            text=text.replace('"logic '+m.bounds(n)+n['name']+'"','"logic '+n['name']+m.bounds(n)+'"')
        self.assertEqual(m.parse_el(text,self.c),m.parse_el(self.text,self.c))

    def test_array_rank_width_order_and_name_rejected(self):
        old='"logic [63:0][53:0]pmpaddr_q"'
        self.assertIn(old,self.text)
        for new in ('"logic [53:0][63:0]pmpaddr_q"','"logic [63:0][52:0]pmpaddr_q"',
                    '"logic [3455:0]pmpaddr_q"','"logic [63:0][53:0]pmpaddr_d"'):
            self.rejected(self.text.replace(old,new))

    def test_d_ports_and_other_csr_extra_rejected(self):
        for name in ('pmpaddr_d','pmpaddr_o','csr_addr_i'):
            self.rejected(self.text+'Toggle '+name+' "logic '+name+'"\n')

    def test_missing_duplicate_and_wrong_checksum_scope(self):
        lines=self.text.splitlines()
        self.rejected('\n'.join(lines[:-1]))
        self.rejected(self.text+lines[-1]+'\n')
        self.rejected(self.text.replace(self.i['toggle_checksum'],'1176918776'))
        self.rejected(self.text.replace(self.i['scope'],self.i['scope']+'.child'))

    def test_complete_directions_not_one_direction(self):
        paired=[]
        for line in self.text.splitlines():
            if line.startswith('Toggle '):paired.extend([line.replace('Toggle ','Toggle 0to1 ',1),line.replace('Toggle ','Toggle 1to0 ',1)])
            else:paired.append(line)
        text='\n'.join(paired)
        self.assertEqual(m.parse_el(text,self.c),m.parse_el(self.text,self.c))
        self.rejected('\n'.join(paired[:-1]))
        self.rejected(text+'\n'+paired[-1])
        self.rejected(text.replace('Toggle 1to0 ','Toggle 0to1 ',1))

    def test_no_other_metric_or_broad_exclusion(self):
        for line in ('Line 310','Toggle pmpcfg_q "logic pmpcfg_q"','Branch 1'):
            self.rejected(self.text+line+'\n')

    def test_inventory_missing_d_or_output_alias(self):
        for name in ('pmpaddr_d','pmpaddr_o','pmpcfg_d[0].locked','rst_ni'):
            node=next(n for n in self.i['protected'] if n['name']==name)
            rows=[r for r in self.rows if r[3] not in m.aliases(node)]
            self.assertLess(len(rows),len(self.rows))
            with self.assertRaises(ValueError):self.inventory(rows)

    def test_inventory_duplicate_wrong_meta_path_and_array_bound(self):
        with self.assertRaises(ValueError):self.inventory(self.rows+[self.rows[0]])
        for col in (1,2,3):
            rows=copy.deepcopy(self.rows);rows[0][col]+='_wrong'
            with self.assertRaises(ValueError):self.inventory(rows)
        rows=copy.deepcopy(self.rows)
        k=next(k for k,r in enumerate(rows) if r[3]=='pmpaddr_q[63:0][53:0]')
        rows[k][1:]=['pmpaddr_q[3455:0]']*3
        with self.assertRaises(ValueError):self.inventory(rows)

    def test_singleton_alias_only_explicit_compiled(self):
        rows=copy.deepcopy(self.rows)
        for r in rows:
            if r[3]=='pmpaddr_o[0:0][53:0]':r[1:]=['pmpaddr_o[0][53:0]']*3
        self.assertEqual(len(self.inventory(rows)),2077)
        rows=copy.deepcopy(self.rows)
        for r in rows:
            if r[3]=='pmpaddr_o[0:0][53:0]':r[1:]=['pmpaddr_o[53:0]']*3
        with self.assertRaises(ValueError):self.inventory(rows)

    def test_contract_scope_count_complement_budget_application(self):
        with patch.object(m,'instance',return_value=self.i):
            m.contract(self.c)
            for key,value in [('timeout_seconds',1800),('population_application',True),('automatic_retry',True)]:
                c=copy.deepcopy(self.c);c[key]=value
                with self.assertRaises(ValueError):m.contract(c)
            c=copy.deepcopy(self.c);c['instances'][0]['protected'].pop()
            with self.assertRaises(ValueError):m.contract(c)

    def test_empty_all_scopes_no_residue(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);p=out/'final-empty.el';p.write_bytes(b'')
            self.assertEqual(m.check_file(out,self.c,p.name),0)
            p.write_text('// residue\n')
            with self.assertRaises(ValueError):m.check_file(out,self.c,p.name)

    def test_pin_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture';p.write_bytes(b'a');pins={str(p):m.life.digest(p)}
            m.life.check(pins);p.write_bytes(b'b')
            with self.assertRaises(ValueError):m.life.check(pins)

    def test_full_tcl_body_five_stages_and_exact_selection(self):
        t=tkinter.Tcl();t.eval('set ::pmp_test_only 1')
        t.eval('source {%s}' % (m.HERE/'qualify_csr_pmp0_native765.tcl'))
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);t.setvar('env(DVE_COVERAGE_OUTPUT)',d)
            vals=dict(fma_design='HOST_ONLY',fma_vdb='HOST_ONLY',fma_test='HOST_ONLY',
                fma_python='HOST_ONLY',fma_helper='HOST_ONLY',qfp_primitives=str(m.HERE/'fma_datapath_native.tcl'))
            selection=''.join('set %s {%s}\n' % x for x in vals.items())
            selection+='set fma_instances [list [list {%s} {%s} {%s} 0]]\n' % (
                self.i['scope'],' '.join(n['name']+m.bounds(n) for n in self.i['targets']),
                ' '.join(n['name']+m.bounds(n) for n in self.i['protected']))
            (out/'selection.tcl').write_text(selection)
            t.eval('set labels {%s}' % ' '.join(r[3] for r in self.rows))
            t.eval('''
set selected {}; set excluded {}; set saves {}; set chosen {}; set checks {}
proc gui_open_cov {args} {}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_exclusion {args} {if {[lindex $args 0] eq "-reset"} {set ::excluded {}}}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_cov_excl_review {args} {return 1}
proc gui_list_get {args} {
    set op [lindex $args 2];set n [lindex $args end]
    if {$op eq "-firstChild"} {if {[llength $args] == 3} {return 1};return 0}
    if {$op eq "-nextSibling"} {if {$n < [llength $::labels]} {return [expr {$n+1}]};return 0}
    return [lindex $::labels [expr {$n-1}]]
}
proc gui_list_get_selected {args} {
    if {[lindex $args end] eq "-count"} {return [llength $::selected]}
    return $::selected
}
proc gui_list_select {args} {
    if {[lindex $args 2] eq "-unselect"} {set ::selected {};return}
    set ::selected [lindex $args 3]
}
proc gui_exclude_items {args} {
    if {[llength $::selected] != 1} {error "bad selection"}
    lappend ::chosen [lindex $::selected 0];lappend ::excluded [lindex $::selected 0]
}
proc gui_exclusion_file {args} {
    if {[lindex $args 0] eq "-save"} {lappend ::saves [file tail [lindex [lindex $args end] 0]]}
}
rename exec real_exec
proc exec {args} {lappend ::checks $args;return HOST_MODEL_CHECK}
qfp_session
''')
            self.assertEqual(int(t.eval('llength $chosen')),770)
            self.assertEqual(set(t.splitlist(t.eval('set chosen'))),{n['name']+m.bounds(n) for n in self.i['targets']})
            self.assertEqual(t.splitlist(t.eval('set saves')),('initial-empty.el','first.el','reset-empty.el','second.el','final-empty.el'))
            self.assertEqual(t.eval('llength $excluded'),'0')
            for stage in m.STAGES:self.assertEqual(len(m.inventory(out,self.c,stage,0)),2077)


if __name__=='__main__':unittest.main()
