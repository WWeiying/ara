"""Exact SLDU2 native qualification with FIRST_WORD-local ownership proof."""
import argparse
import csv
from itertools import product
import json
from pathlib import Path
import re
import types

import review_sldu_two_boundaries763 as proof
import capture_dispatcher_four762 as prior

life, require, native, tools = prior.life, prior.require, prior.native, prior.tools
HERE = Path(__file__).resolve().parent
TCL = prior.TCL
AUDIT = life.OUT/'sldu-two-boundaries-source-review763-parent-20261007-01.json'
AUDIT_SHA = '59473b48e5443dde91135e5f3b5cb148cd8c5a878bd65221109082fb5c46f7d7'
REVIEW = life.OUT/'sldu-two-boundaries-independent-review763-agent-20261007-01.json'
REVIEW_SHA = '4f82954a4b17b8c8b36b2f6274268d95977f76c11b34a3f8a3da666d4e8c5e8b'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'


def owner_contract(source):
    writers = [(source[:m.start()].count('\n')+1, m.group(1).strip())
               for m in re.finditer(r'\bstate_d\s*=(?!=)\s*([^;]+);', source)]
    require([x[0] for x in writers] == [538,622,647,669,683,801,850,898,912,914,989,1021,1030,1041,1058,1072],
            'State override inventory changed')
    pointers = [(source[:m.start()].count('\n')+1,m.group(0)) for m in
                re.finditer(r'vinsn_queue_d\.issue_pnt\s*(?:\+=|-=|=(?!=))[^;]+;',source)]
    require([p[0] for p in pointers] == [916,990,1023] and
            all(p[1]=='vinsn_queue_d.issue_pnt += 1;' for p in pointers), 'Issue pointer writer changed')
    slots = [(source[:m.start()].count('\n')+1,m.group(0)) for m in
             re.finditer(r'vinsn_queue_d\.vinsn\[[^\n;]+?\]\s*(?:\.[\w.]+)?\s*=(?!=)[^;]+;',source)]
    require([x[0] for x in slots] == [1162,1167,1171] and
            slots[0][1]=='vinsn_queue_d.vinsn[vinsn_queue_q.accept_pnt] = pe_req_i;' and
            '.stride =' in slots[1][1] and '.vtype.vsew = EW64;' in slots[2][1], 'Descriptor writer changed')
    anchors = ["`FF(vinsn_issue_q, vinsn_queue_d.vinsn[vinsn_queue_d.issue_pnt], '0)",
               'assign vinsn_queue_full = (vinsn_queue_q.commit_cnt == VInsnQueueDepth);',
               'vinsn_queue_d = vinsn_queue_q;',
               "if (vinsn_commit_valid && commit_cnt_d == '0) begin",
               'if (!vinsn_queue_full && pe_req_valid_i && !vinsn_running_d[pe_req_i.id] &&',
               'if (state_q != SLIDE_NP2_COMMIT)\n            state_d = SLIDE_RUN;',
               'if (vinsn_issue_q.use_scalar_op)\n                state_d = SLIDE_RUN_VSLIDE1UP_FIRST_WORD;',
               'if (vinsn_issue_q.op == VSLIDEDOWN && vinsn_issue_q.use_scalar_op) begin',
               "commit_cnt_q <= result_queue_bytes_q[result_queue_read_pnt_q]",
               'state_d = SLIDE_IDLE;\n              // Increment vector instruction queue pointers and counters\n              vinsn_queue_d.issue_pnt += 1;']
    require(all(a in source for a in anchors), 'FIRST_WORD owner guard changed')
    idle = source.split('      SLIDE_IDLE: begin')[1].split(
        '      SLIDE_RUN, SLIDE_RUN_VSLIDE1UP_FIRST_WORD, SLIDE_NP2_COMMIT: begin')[0]
    require('VSLIDEUP: begin' in idle and
            idle.index('VSLIDEUP: begin') < idle.index('state_d = SLIDE_RUN_VSLIDE1UP_FIRST_WORD;') <
            idle.index('VSLIDEDOWN: begin') and 'result_queue_valid_d[' not in idle,
            'FIRST_WORD entry opcode or prior result producer changed')
    return dict(state_writers=writers, issue_pointer_writers=pointers, descriptor_writers=slots,
        invariant='FIRST_WORD implies owned descriptor.op=VSLIDEUP and use_scalar_op=1. '
                  'On entry IDLE produced no current result. On blocked FIRST_WORD no issue pointer '
                  'or current-result write advances. Its first successful beat leaves FIRST_WORD '
                  'for RUN or IDLE before a successor descriptor can become current.',
        free_slot='Depth2 reset-established legal ring: outstanding FIRST_WORD owner cannot commit '
                  'before its first result exists. Older commits can free only older slots. '
                  'Accept writes old accept_pnt free slot, not owned issue_pnt; register reads d-pointer.',
        limit='Local FIRST_WORD invariant, not arbitrary queue corruption or a global all-state FIFO proof')


def slot_step(owner, older, accept, commit, beat, corrupt=False):
    # Exhaust the physical two-slot placement and competing first-word events.
    occupied = {owner} | ({1-owner} if older else set())
    before_full = len(occupied) == 2
    if commit and older: occupied.remove(1-owner)
    accepted_slot = None
    if accept and not before_full:
        accepted_slot = owner if corrupt else 1-owner
        require(accepted_slot not in occupied, 'Accepted descriptor overwrote FIRST_WORD owner')
    return dict(owner_retained=not beat, pointer_moves=bool(beat),
                next_state='RUN_OR_IDLE' if beat else 'FIRST_WORD', accepted_slot=accepted_slot)


def slot_induction():
    cases=0
    for owner,older,accept,commit,beat in product(range(2),repeat=5):
        state=slot_step(owner,older,accept,commit,beat)
        require(not state['pointer_moves'] or state['next_state']!='FIRST_WORD','Pointer moved within FIRST_WORD')
        cases+=1
    return dict(cases=cases, counterexamples=0, depth=2,
                model='Source-derived first-result boundary; normal free-slot ring semantics only')


def bound():
    a=life.read_bound(AUDIT,AUDIT_SHA); life.check(a['pins'])
    r=life.read_bound(REVIEW,REVIEW_SHA)
    require(r['source_sha256']==proof.SOURCE_SHA and r['targets']==2 and r['protected']==34,
            'Independent review binding differs')
    book=life.read_bound(proof.BOOK,BOOK_SHA)
    require(book[str(life.ROOT/'hardware/src/sldu/sldu.sv')]==proof.SOURCE_SHA and
            life.digest(proof.SOURCE)==proof.SOURCE_SHA,'Frozen SLDU source differs')
    owner=owner_contract(proof.SOURCE.read_text())
    dispatcher=life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    pkg=life.ROOT/'hardware/include/ara_pkg.sv'
    pins={str(dispatcher):book[str(life.ROOT/'hardware/src/ara_dispatcher.sv')],
          str(pkg):book[str(pkg)]}
    life.check(pins)
    require('SlduInsnQueueDepth = 2;' in pkg.read_text(), 'Frozen ring depth differs')
    text=dispatcher.read_text()
    require('csr_vstart_q >= csr_vl_q || mask_mem_noop || null_vslideup' in text and
            "ara_req_valid  = 1'b0;" in text and 'ara_req.op     = ara_pkg::VSLIDEUP;' in text,
            'Legal positive-VL producer differs')
    owner['legal_producer']=('Dispatcher suppresses VL0/vstart>=VL ordinary slides; scalar UP/DOWN '
                             'remain distinct opcodes. Positive first-word destination byte count.')
    owner['slot_induction']=slot_induction()
    return a,owner,pins


def prepare(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh output required')
    a,owner,extra=bound()
    book=life.read_bound(proof.BASE/'admission-manifest.json',proof.BASE_SHA)
    bp=proof.BASE/'combined-bits.json'; lp=proof.BASE/'combined-inputs.txt'
    bits=life.read_bound(bp,book['output_pins'][str(bp)])
    require(life.digest(lp)==book['output_pins'][str(lp)],'Ledger drift')
    ledger=lp.read_text().splitlines()
    require(ledger[1:]==bits['tests'] and len(ledger)==len(set(ledger))==764,'Exact763 differs')
    design,sample=Path(ledger[0]),Path(ledger[1]); membership={}
    pins=life.merge_pins(a['pins'],extra)
    inherited=life.merge_pins(book['input_pins'],book['output_pins'])
    for root in (design,sample):
        require(root.resolve()==root and root.is_dir() and not
                any(p.is_symlink() for p in root.rglob('*')),'Aliased VDB')
        files=sorted(p for p in root.rglob('*') if p.is_file()); require(files,'Empty VDB')
        membership[str(root)]=[str(p.relative_to(root)) for p in files]
        for p in files:
            sha=life.digest(p)
            require(str(p) not in inherited or inherited[str(p)]==sha,'Historical VDB differs')
            pins[str(p)]=sha
    shape=design/'snps/coverage/db/shape/fsm.verilog.shape.xml'
    require(pins[str(shape)]==bits['design']['shape/fsm.verilog.shape.xml'],'FSM shape drift')
    gs=proof.rows(native.read_xml(shape),bits); require(gs==a['groups'],'Source/compiled plan differs')
    plan=dict(groups=gs,targets=2,protected=34,strategy='direct-transition-only-66',
              point_query_authority='saved-native-identity')
    expected=native.expected_records(plan,native.Design(design))
    tests=list((sample/'snps/coverage/db/testdata').iterdir())
    require(len(tests)==1 and tests[0].is_dir(),'Not one historical sample')
    selected=str(sample.with_suffix('')/tests[0].name)
    rawpath,rawsha=prior.runner.native.inherited.admission.RAW,prior.runner.native.inherited.admission.RAW_SHA
    raw=life.read_bound(rawpath,rawsha);tools.revalidate(raw['tool_identity'])
    deps=[Path(__file__).resolve(),HERE/'test_capture_sldu_two763.py',
          HERE/'capture_sldu_two763.py', HERE/'test_capture_sldu_two763_json.py',Path(proof.__file__),
          Path(prior.__file__),Path(prior.runner.__file__),Path(native.__file__),Path(life.__file__),
          Path(tools.__file__),TCL,AUDIT,REVIEW,rawpath]
    deps += [HERE/n for n in ('fsm741_transition_native.tcl','fsm741_transition_batch.tcl',
        'fsm741_native_singleton.tcl','fsm741_native_probe.tcl','discover_ptw_pmp0_fsm_v2.tcl',
        'apply_points740_v4.tcl','inventory_operand_debug.py','closure_point_inventory.py')]
    for p in deps:pins[str(p.resolve())]=life.digest(p)
    atom=prior.runner.atom; lines=['set fx_groups {}\n']
    for g in gs:
        fields=[g['scope'],str(proof.SOURCE),g['machine']['name'],g['mode']]
        lines.append('lappend fx_groups [list '+' '.join(map(atom,fields))+' [list '+
            ' '.join(atom(r['name']) for r in g['rows'])+'] [list '+
            ' '.join(atom(r['name']) for r in g['rows'] if r['target'])+']]\n')
    lines += ['set '+k+' '+atom(v)+'\n' for k,v in dict(d4_design=design,d4_sample=sample,d4_selected=selected).items()]
    life.check(pins);out.mkdir();(out/'selection.tcl').write_text(''.join(lines))
    pins[str(out/'selection.tcl')]=life.digest(out/'selection.tcl')
    life.save(out/'config.json',dict(schema='EXACT_SLDU2_NATIVE763',output=str(out),pins=pins,
        plan=plan,expected_records=expected,queue_owner=owner,proof_seal=AUDIT_SHA,
        independent_review_seal=REVIEW_SHA,identity=raw['tool_identity'],input_membership=membership,
        sample_inputs=[str(design),str(sample)],selected=selected,baseline=763,sample_population=1,
        population_application=False,timeout_seconds=900,automatic_retry=False,
        states_explicitly_excluded=False,all34_protected=True,annotation=native.ANNOTATION))
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins))),flush=True)


def verify(out,seal,prepared=False):
    c=life.read_bound(out/'config.json',seal);a,owner,_=bound()
    require(c['schema']=='EXACT_SLDU2_NATIVE763' and c['output']==str(out) and
            c['plan']['groups']==a['groups'] and c['queue_owner']==json.loads(json.dumps(owner)) and
            c['plan']['targets']==2 and c['plan']['protected']==34 and
            c['all34_protected'] and not c['population_application'],'Source/scope/owner contract differs')
    life.check(c['pins']);tools.revalidate(c['identity'])
    for root,members in c['input_membership'].items():
        require(sorted(str(p.relative_to(root)) for p in Path(root).rglob('*') if p.is_file())==members,'VDB membership drift')
    if prepared:print('PREPARED_PINS_PASS');return
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and terminal['actual_dve'],'Terminal failed')
    require(not (out/'error.txt').exists() and not (out/'cleanup-error.txt').exists(),'Native error')
    log=(out/'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('DISPATCHER_FOUR_NATIVE_DONE')==1 and not
        re.search(r'DISPATCHER_FOUR_FAILED|UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:',log),'Native log failed')
    require("The design '%s' was loaded successfully."%c['sample_inputs'][0] in log,'Design not loaded')
    expected=[tuple(r) for r in c['expected_records']]
    for name in ('first.el','second.el'):
        require(native.native_records((out/name).read_text())==expected,'Exact two typed signatures differ')
    for name in ('initial.el','reset.el','final-empty.el','cleanup-empty.el'):
        require((out/name).read_bytes()==b'','Global exclusions not empty')
    native.audit_points(list(csv.reader((out/'exact-audit.tsv').open(),delimiter='\t')),c['plan'])
    output_pins={str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('capture-result.json','worker.log')}
    life.save(out/'capture-result.json',dict(status='EXACT_SLDU2_NATIVE_QUALIFIED_NOT_APPLIED',
        config_seal=seal,baseline=763,targets=2,protected=34,queue_owner=owner,
        source_proof_sha256=AUDIT_SHA,independent_review_sha256=REVIEW_SHA,native_records=expected,
        five_stages=True,semantic_reload=True,global_empty=True,states_explicitly_excluded=False,
        population_application=False,input_pins=c['pins'],output_pins=output_pins))
    print('QUALIFIED seal='+life.digest(out/'capture-result.json'),flush=True)


def run(out,seal):
    types.FunctionType(prior.runner.run.__code__,dict(prior.runner.run.__globals__,verify=verify,TCL=TCL))(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','run','verify'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal')
    a=p.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    else:
        require(a.seal,'Exact config seal required')
        if a.mode=='run':run(out,a.seal)
        else:verify(out,a.seal,a.mode=='check')
