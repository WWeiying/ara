"""Entire legacy-compatible host model. Synthetic EL IDs are NOT native evidence."""
from pathlib import Path
import tempfile
import tkinter
import unittest

import prepare_qbs_full1792_qualification as p


class Full(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact, cls.original, cls.pins, cls.actual = p.inputs()

    def model(self, output, fault=None):
        t = tkinter.Tcl(); t.tk.wantobjects(False)
        t.eval('''
            foreach command {lassign dict lmap try coroutine tailcall apply} {
                if {[llength [info commands $command]]} {rename $command {}}
            }
            rename lsort host_lsort
            proc lsort {args} {
                if {[lsearch -exact $args -unique] >= 0} {error "Not legacy lsort"}
                return [host_lsort [lindex $args 0]]
            }
            set qn_test_only 1
        ''')
        t.eval(p.TCL.read_text()); t.eval(p.selection(self.artifact,self.original,output))
        groups = p.full.groups(self.artifact)
        properties = {}; roots = {}; names = {}; metas = {}; selected = dict(scope='',cond='',vector='')
        active = set()
        for bank, scope in enumerate(sorted(self.artifact['scope_protection'])):
            local = [g for g in groups if g['scope'] == scope]; top = [g for g in local if not g['parent']]
            roots[scope] = 'host%d_root0' % bank
            for i,g in enumerate(top):
                handle = 'host%d_root%d' % (bank,i)
                child = next((c for c in local if c['parent'] == g['expression']),None)
                ch = 'host%d_child%d' % (bank,i) if child else ''
                props = {'-path':g['expression'],'-meta':g['expression'],'-firstChild':ch,
                    '-nextSibling':'host%d_root%d' % (bank,i+1) if i+1 < len(top) else ''}
                for k,v in props.items(): properties[(scope,handle,k)] = v
                names[(scope,g['expression'])] = g['names']; metas[(scope,g['expression'])] = g['expression']
                if child:
                    meta = g['expression']+'  .'+child['expression']
                    names[(scope,meta)] = child['names']; metas[(scope,meta)] = child['expression']
                    for k,v in dict(zip(('-path','-meta','-firstChild','-nextSibling'),
                        (g['expression']+'.'+child['expression'],meta,'',''))).items(): properties[(scope,ch,k)] = v
        candidates = {(c['scope'],c['point']['expression'],c['point']['vector']):c for c in self.artifact['candidates']}
        group_ids = {(g['scope'],g['expression']):200000+i for i,g in enumerate(groups)}
        def get(*args):
            option=args[2]; handle=args[3] if len(args)>3 else None
            return roots[selected['scope']] if handle is None and option=='-firstChild' else properties[(selected['scope'],handle,option)]
        def action(*args): selected.update(scope=args[-1],cond='',vector=''); return ''
        def select(*args):
            view=args[args.index('-list')+1]
            selected[view] = '' if '-unselect' in args else t.splitlist(args[-1])[0]
            return ''
        def values(*args):
            view=args[args.index('-list')+1]
            if '-count' in args: return str(int(bool(selected[view])))
            if '-all' in args:
                data = names[(selected['scope'],selected['cond'])] if view=='vector' else [g['expression'] for g in groups if g['scope']==selected['scope'] and not g['parent']]
                return t.call('list',*data)
            return t.call('list',selected[view])
        def key(): return selected['scope'],metas[(selected['scope'],selected['cond'])],selected['vector']
        def exclude(*args):
            assert args[args.index('-list')+1]=='vector' and key() in candidates
            active.add(key()); return ''
        def exclusion(*args):
            if args==('-reset',):
                if fault!='reset': active.clear()
                return ''
            if '-recalculate' in args: return ''
            if '-excluded' in args:
                value=key() in active
                if fault=='neighbor' and active and key() not in candidates: value=True
                return str(int(value))
            raise AssertionError(args)
        def el(*args):
            path=Path(t.splitlist(args[-1])[0])
            if '-load' in args: active.update(candidates); return ''
            if not active: path.write_bytes(b''); return ''
            lines=[]
            for scope,expression,vector in sorted(active):
                c=candidates[(scope,expression,vector)]; point=c['point']; attrs=point['attributes']
                identity=group_ids[(scope,expression)]; vid=int(vector,2)+11
                if fault=='alias': identity=200000
                if fault=='reload' and path.name=='second.el': vid+=100
                lines.extend(['CHECKSUM: "'+c['module_checksum']+' '+c['checksum']+'"', 'INSTANCE: '+scope,
                    'ANNOTATION: "'+p.f.proof.ANNOTATION+'"',
                    'Condition %d "%s" "%s %s -1" (%d "%s")' % (identity,attrs['chksum'],expression,attrs['width'],vid,vector)])
            if fault=='missing': lines=lines[:-4]
            if fault=='extra': lines+=lines[:4]
            if fault=='whole': lines[-1]='Condition 123'
            if fault=='checksum': lines[0]='CHECKSUM: "1 2947893042"'
            path.write_text('\n'.join(lines)+'\n'); return ''
        for name in ('gui_cov_show_cond_ids','gui_list_expand'): t.createcommand(name,lambda *a:'')
        for name,fn in dict(gui_list_get=get,gui_list_action=action,gui_list_select=select,gui_list_get_selected=values,
            gui_covdetail_query=lambda *a:'Condition',gui_exclusion=exclusion,gui_exclude_items=exclude,gui_exclusion_file=el).items():
            t.createcommand(name,fn)
        t.eval('set qbf_stream [open [file join $qs_output native-qualification.tcllist] w]')
        try:
            t.eval('qn_run')
            t.eval('gui_exclusion -reset; qn_save cleanup-empty.el 1; qn_log [list terminal 0 {} 0 {}]')
        finally: t.eval('close $qbf_stream')

    def test_actual_parent_singleton_numeric_not_compiled_guess(self):
        self.assertEqual(self.actual['records'][0]['native_id'],'8260')
        self.assertEqual(self.actual['records'][0]['vector_id'],'3')
        self.assertNotEqual(self.actual['records'][0]['native_id'],'8259')
        p.safe()

    def test_full1344_1792_five_stages_legacy_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); self.model(out); actual=p.inspect(out,self.artifact)
            self.assertEqual(len(actual['actual_native_records']),1792)
            self.assertEqual(actual['protected_count'],41214)
            self.assertFalse(actual['application'])

    def test_runtime_signature_and_protection_negatives(self):
        for fault in ('neighbor','reset','alias','reload','missing','extra','whole','checksum'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(tkinter.TclError): self.model(Path(tmp),fault)

    def test_independent_EL_and_lifecycle_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); self.model(out)
            el=(out/'first.el').read_bytes()
            for changed in (el+el,el[:-100],el+b'\xff\n',el.replace(b' 1 -1',b' 2 -1',1),el.replace(b'bank0',b'bank2',1)):
                self.assertNotEqual(changed,el); (out/'first.el').write_bytes(changed)
                with self.assertRaises(ValueError): p.inspect(out,self.artifact)
            (out/'first.el').write_bytes(el)
            path=out/'native-qualification.tcllist'; raw=path.read_text(); rows=raw.splitlines(True)
            idx=next(i for i,r in enumerate(rows) if r.startswith('audit selected') and r.endswith(' 0\n'))
            for replacement in ('',rows[idx]+rows[idx],rows[idx][:-2]+'1\n'):
                changed=''.join(rows[:idx])+replacement+''.join(rows[idx+1:]); self.assertNotEqual(changed,raw)
                path.write_text(changed)
                with self.assertRaises(ValueError): p.inspect(out,self.artifact)
            path.write_text(raw.replace('terminal 0 {} 0 {}','terminal 1 error 0 {}'))
            with self.assertRaises(ValueError): p.inspect(out,self.artifact)

    def test_input_pin_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source'; path.write_bytes(b'frozen'); ledger={str(path):p.f.sha(path)}
            p.f.check_pins(ledger); path.write_bytes(b'drift')
            with self.assertRaises(ValueError): p.f.check_pins(ledger)

    def test_scope_control_and_exact_complement(self):
        protection=p.single.audit.protection(self.artifact)
        self.assertEqual(sum(r['protected_count'] for r in protection.values()),41214)
        self.assertEqual(sum(r['target_count'] for r in protection.values()),1792)
        self.assertTrue(p.f.SCOPE_BOUNDARY)


if __name__=='__main__': unittest.main()
