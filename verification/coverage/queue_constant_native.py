"""Frozen744 queue constants: native bit-select roundtrip, never a population report."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import fma_product_native as common
from inventory_operand_debug import Design
import targeted_toggle_evidence_v2 as toggle

life,require,tools=common.life,common.require,common.tools
HERE=Path(__file__).resolve().parent
BASE=life.OUT/'rvv-lmul8-payload-walk-offline-admitted-744-agent-20261007-01'
BASE_SHA='06bc169ca882a44b382bea694b2dfc4ffcdb23a353b73fb117d6b29cbc70168a'
PRODUCT=life.OUT/'fma-product-native-fp32-agent-20261007-01'
PRODUCT_SHA='95dc2b72c37a22df8d245906e5cf3b24434efa4d1ebbb17272983a05d77dcbd8'

def bitset(c):
    return {(i['scope'],s['name'],bit,direction) for i in c['instances'] for s in i['signals']
            for bit in s['bits'] for direction in ('0to1','1to0')}

def candidate(c):
    lines=[]
    for i in c['instances']:
        lines += ['CHECKSUM: "'+i['design_module_checksum']+' '+i['toggle_checksum']+'"',
                  'INSTANCE: '+i['scope'],'ANNOTATION: "Frozen post-reset source invariant; no X, pressure, or module waiver"']
        for s in i['signals']:
            for bit in s['bits']:
                for direction in ('0to1','1to0'):
                    selector='' if s['scalar'] else ' ['+str(bit)+']'
                    lines.append('Toggle '+direction+' '+s['name']+selector)
    return '\n'.join(lines)+'\n'

def parse_el(text,c):
    instances={i['scope']:i for i in c['instances']};found=set();scope=None;checksum=None
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith(('//','ANNOTATION:')):continue
        if line.startswith('CHECKSUM:'):
            checksum=line.split(':',1)[1].strip().strip('"').split();scope=None;continue
        if line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip()
            require(scope in instances and checksum==[instances[scope]['design_module_checksum'],
                instances[scope]['toggle_checksum']],'Unexpected native scope/checksum')
            continue
        match=re.fullmatch(r'Toggle(?:\s+(0to1|1to0))?\s+([\w.]+)\s*(?:\[([0-9]+)(?::([0-9]+))?\])?(?:\s+"([^"\n]+)")?',line)
        require(scope is not None and match is not None,'Unexpected metric/EL grammar: '+line)
        direction,name,left,right,signature=match.groups()
        s=next((x for x in instances[scope]['signals'] if x['name']==name),None)
        require(s is not None,'Protected signal exclusion')
        if left is None:
            bits=[0] if s['scalar'] else list(range(min(s['left'],s['right']),max(s['left'],s['right'])+1))
        else:
            lo,hi=sorted((int(left),int(right) if right is not None else int(left)));bits=list(range(lo,hi+1))
        require(set(bits)<=set(s['bits']),'Protected bit exclusion')
        if signature:
            # DVE supplies the declaration signature; bind full signal range as well as selected bits.
            declaration=name if s['scalar'] else name+'['+str(s['left'])+':'+str(s['right'])+']'
            require(signature.endswith(declaration),'Native declaration signature differs')
        for bit in bits:
            for d in (direction,) if direction else ('0to1','1to0'):
                key=(scope,name,bit,d);require(key not in found,'Duplicate direction');found.add(key)
    require(found==bitset(c),'Incomplete/extra native bit-direction set')
    return sorted(found)

def source_proof():
    book=life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    old=json.loads(book.read_bytes());pins={str(book):life.digest(book)};texts={}
    paths=('hardware/src/lane/operand_queue.sv','hardware/src/lane/operand_requester.sv',
        'hardware/src/lane/operand_queues_stage.sv','hardware/include/ara_pkg.sv','hardware/src/ara_sequencer.sv',
        'hardware/deps/common_cells/src/fifo_v3.sv','hardware/src/ara_dispatcher.sv','hardware/src/lane/lane_sequencer.sv')
    for rel in paths:
        p=life.ROOT/rel
        if rel.endswith(('ara_dispatcher.sv','lane_sequencer.sv')):
            p=life.OUT/'old-image-source-evidence-20261006-01'/p.name
        pins[str(p)]=old[str(life.ROOT/rel)];texts[Path(rel).name]=p.read_text()
    life.check(pins)
    q=texts['operand_queue.sv'];stage=texts['operand_queues_stage.sv'];fifo=texts['fifo_v3.sv']
    require("assign cmd_pop_o = 1'b0;" in q and "select_q <= '0;" in q and "select_d = select_q;" in q,
            'Queue invariant anchors drift')
    require(all(x in q for x in ('if (SupportIntExt2) select_d = select_q + 4;',
        'if (SupportIntExt4) select_d = select_q + 2;', 'if (SupportIntExt8) select_d = select_q + 1;')),
        'Select update domain drift')
    require("write_pointer_q == FifoDepth[ADDR_DEPTH-1:0] - 1" in fifo and
        "read_pointer_n == FifoDepth[ADDR_DEPTH-1:0] - 1" in fifo and
        "read_pointer_q  <= '0;" in fifo and "write_pointer_q <= '0;" in fifo,'Depth1 proof anchors drift')
    pkg=texts['ara_pkg.sv'];seq=texts['ara_sequencer.sv'];lane=texts['lane_sequencer.sv']
    require('localparam int unsigned MaskuInsnQueueDepth = 1;' in pkg and
        '[VADD:VWREDSUM]      : vfu = VFU_Alu;' in seq and "operand_request    = '0;" in lane,
        'Routing/reset proof anchors drift')
    vals=sorted(set(re.findall(r'ara_req\.conversion_vs1\s*=\s*(\w+)\s*;',texts['ara_dispatcher.sv'])))
    require(vals==['OpQueueConversionSExt2','OpQueueConversionWideFP2','OpQueueConversionZExt2','OpQueueReductionZExt'],
        'Unhandled dispatcher vs1 conversion producer')
    return pins,dict(status='NARROW_FROZEN_SOURCE_INVARIANTS',
        depth1='q reset/flush zero; n holds q or wraps to zero when q equals DEPTH-1=0; induction for every push/pop combination',
        no_IntExt_select='q reset zero; d holds q, disabled increments, or assigns zero on completion/flush',
        tied_zero='Exact source instance flush_i=0, or AccessCmdPop=false constant output; not internal cmd_pop',
        alu_A_conv_bit2='ALU vs1 domain None=0/ZExt2=1/SExt2=2/ReductionZExt=8. WideFP2=7 belongs to FP op/VFU_MFpu, not AluA routing.',
        dispatcher_vs1_assignments=vals,allowed_ALU_vs1_values=[0,1,2,8],
        excluded_initial_X=False,contract='Fixed legal product routing after reset/comb settling; never waive X transitions or corrupted state',
        usage_d_included=False,unknown_modules_included=False)

def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh native output only')
    a=life.read_bound(BASE/'admission-manifest.json',BASE_SHA);life.check(a['output_pins'])
    before=life.read_bound(BASE/'combined-bits.json',a['output_pins'][str(BASE/'combined-bits.json')])
    require(len(before['tests'])==len(set(before['tests']))==744,'Formal744 required')
    pins,proof=source_proof();pins=life.merge_pins(pins,a['output_pins']);pins[str(BASE/'admission-manifest.json')]=BASE_SHA
    product=life.read_bound(PRODUCT/'capture-result.json',PRODUCT_SHA);life.check(product['pins'])
    require(product['status']=='ONE_FP32_PRODUCT_NATIVE_FORMAT_ROUNDTRIP_PASS','Native predecessor not qualified')
    pins=life.merge_pins(pins,product['pins']);pins[str(PRODUCT/'capture-result.json')]=PRODUCT_SHA
    identity=json.loads((PRODUCT/'config.json').read_bytes())['identity'];tools.revalidate(identity)
    db=Path(str(life.IMAGE)+'.vdb');d=Design(db);base=db/'snps/coverage/db'
    info=toggle.xml(base/'shape/tgl.verilog.info.xml');shape=toggle.xml(base/'shape/tgl.verilog.shape.xml')
    checks={n.get('name'):n.get('chksum') for n in info.iter('instance_data')}
    stage=(life.ROOT/'hardware/src/lane/operand_queues_stage.sv').read_text();requests={}
    blocks={m.group(2):(m.group(1),m.group(3)) for m in re.finditer(
        r'operand_queue\s*#\((.*?)\)\s+(i_operand_queue_\w+)\s*\((.*?)\n\s*\);',stage,re.S)}
    def add(scope,name,bits=None):requests.setdefault(scope,[]).append((name,bits))
    for lane in range(4):
        prefix='ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_queues.'%lane
        for name in ('alu_a','alu_b','mfpu_a','mfpu_b','mfpu_c','st_mask_a','slide_addrgen_a','mask_m'):
            require('i_operand_queue_'+name in blocks,'Missing exact source child '+name)
            params,ports=blocks['i_operand_queue_'+name];scope=prefix+'i_operand_queue_'+name
            access='AccessCmdPop' in params and re.search(r"\.AccessCmdPop\s*\(1'b1",params)
            if not access:add(scope,'cmd_pop_o')
            if name in ('alu_a','alu_b','mfpu_a','mfpu_b','mfpu_c'):
                require(re.search(r"\.flush_i\s*\(1'b0\s*\)",ports),'Flush port not tied zero')
                add(scope,'flush_i')
            if name in ('st_mask_a','slide_addrgen_a','mask_m'):
                require('SupportIntExt' not in params,'Unexpected enabled conversion')
                add(scope,'select_q');add(scope,'select_d')
            if name=='alu_a':add(scope,'operand_queue_cmd_i.conv',[2])
            if name=='mask_m':
                require(re.search(r'\.DataBufDepth\s*\(1\s*\)',params),'Not exact depth1 input FIFO')
                for child in ('i_input_buffer','i_cmd_buffer'):
                    for signalname in ('read_pointer_n','read_pointer_q','write_pointer_n','write_pointer_q'):
                        add(scope+'.'+child,signalname)
    instances=[]
    for scope,wanted in sorted(requests.items()):
        require(scope in d.hierarchy and scope in checks,'Missing compiled exact child')
        defs=[x for x in shape.findall('tgldef') if x.get('chksum')==checks[scope]]
        require(len(defs)==1,'Ambiguous native Toggle shape')
        nodes={n.get('name'):n for n in defs[0].iter() if n.tag in ('node','vectornode')}
        signals=[]
        for name,select in wanted:
            require(name in nodes,'Missing compiled signal '+name);n=nodes[name]
            scalar=n.tag=='node';left=int(n.get('left','0'));right=int(n.get('right','0'))
            bits=select if select is not None else list(range(min(left,right),max(left,right)+1))
            require(set(bits)<=set(range(min(left,right),max(left,right)+1)),'Bit outside compiled shape')
            signals.append(dict(name=name,bits=bits,scalar=scalar,left=left,right=right,
                                native_label=name if scalar else name+'['+str(left)+':'+str(right)+']',shape=dict(n.attrib)))
        protected=[dict(n.attrib) for name,n in nodes.items() if name not in {s['name'] for s in signals}]
        instances.append(dict(scope=scope,design_module_checksum=d.hierarchy[scope].get('chksum'),
            toggle_checksum=checks[scope],signals=signals,protected=protected,
            retained_target_signal_bits={s['name']:sorted(set(range(min(s['left'],s['right']),max(s['left'],s['right'])+1))-set(s['bits'])) for s in signals}))
    for rel in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml'):
        p=base/rel;expected=before['design'].get(rel,pins.get(str(p)))
        require(expected is not None and toggle.digest(p)==expected,'Formal/native predecessor design hash differs')
        pins[str(p)]=expected
    vdb=Path(before['tests'][-1]);tests=list((vdb/'snps/coverage/db/testdata').iterdir());require(len(tests)==1,'One admitted test required')
    for p in tests[0].iterdir():
        if p.is_file():pins[str(p)]=life.digest(p)
    for p in (Path(__file__).resolve(),HERE/'queue_constant_native.tcl',HERE/'test_queue_constant_native.py'):
        pins[str(p)]=life.digest(p)
    c=dict(output=str(out),pins=pins,identity=identity,instances=instances,source_proof=proof,
        timeout_seconds=1800,population_application=False,automatic_retry=False,baseline=744,
        input_VDB_count=1,design=str(db),vdb=str(vdb),test=str(vdb.with_suffix('')/tests[0].name))
    text=candidate(c);parse_el(text,c);life.check(pins);out.mkdir()
    common.common.save(out/'candidate.el',text);pins[str(out/'candidate.el')]=life.digest(out/'candidate.el')
    lines=['set qc_design {'+c['design']+'}\n','set qc_vdb {'+c['vdb']+'}\n','set qc_test {'+c['test']+'}\n',
           'set qc_python {'+shutil.which('python3')+'}\n','set qc_helper {'+str(Path(__file__).resolve())+'}\n',
           'set qc_instances {}\n']
    for i in instances:
        labels=' '.join('{'+s['native_label']+'}' for s in i['signals'])
        lines.append('lappend qc_instances [list {'+i['scope']+'} [list '+labels+']]\n')
    common.common.save(out/'selection.tcl',''.join(lines));pins[str(out/'selection.tcl')]=life.digest(out/'selection.tcl')
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),scopes=len(instances),
                         bit_directions=len(bitset(c)),pins=len(pins))))

def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Native terminal identity failure')
    log=(out/'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('QUEUE_CONSTANT_NATIVE_DONE')==1 and 'QUEUE_CONSTANT_NATIVE_FAILED' not in log,
            'Native batch incomplete')
    require(parse_el((out/'first.el').read_text(),c)==parse_el((out/'second.el').read_text(),c),'Native roundtrip differs')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require((out/name).read_bytes()==b'','Global reset not empty')
    for index,i in enumerate(c['instances']):
        def rows(stage):return [line.split('\t')[1:4] for line in (out/('native_'+stage+'_'+str(index)+'.tsv')).read_text().splitlines()[1:]]
        before=rows('before');require(before and len(before)==len({tuple(x) for x in before}),'Ambiguous native rows')
        names=[row[2] for row in before]
        for s in i['signals']:require(names.count(s['native_label'])==1,'Exact source/native object missing')
        for stage in ('selected','reset','reloaded','final'):require(rows(stage)==before,'Protected native identity drift')
    result=dict(status='QUEUE_CONSTANT_EXACT_NATIVE_BIT_DIRECTION_ROUNDTRIP_PASS',baseline=744,
        objects=sum(len(i['signals']) for i in c['instances']),bit_directions=len(bitset(c)),
        both_directions_explicit=True,initial_X_excluded=False,usage_d_excluded=False,all_non_targets_protected=True,
        global_final_empty=True,semantic_reload=True,population_application=False,
        pins={**c['pins'],**{str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name!='capture-result.json'}})
    life.save(out/'capture-result.json',result);print(json.dumps(dict(status=result['status'],seal=life.digest(out/'capture-result.json'))))

def run(out,seal):
    c=life.read_bound(out/'config.json',seal);require(not (out/'execution.json').exists(),'One-shot already claimed')
    life.check(c['pins']);tools.revalidate(c['identity']);env=tools.controlled_environment(c['identity'],os.environ)
    env.pop('DVE',None);env['DVE_COVERAGE_OUTPUT']=str(out)
    cmd=[shutil.which('xvfb-run'),'-a','-e',str(out/'xvfb.log'),'-s','-screen 0 1280x1024x24',
         c['identity']['roles']['launcher'],'-full64','-cov','-script',str(HERE/'queue_constant_native.tcl')]
    with (out/'execution.json').open('x') as f:json.dump(dict(command=cmd,cwd=str(out),timeout_seconds=1800),f)
    with (out/'launcher.log').open('x') as log:
        process=subprocess.Popen(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        time.sleep(10);actual=[]
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                if (p/'exe').resolve()==Path(c['identity']['executable']) and (p/'cwd').resolve()==out:
                    actual.append(dict(pid=int(p.name),exe=str((p/'exe').resolve()),cwd=str(out)))
            except OSError:continue
        life.save(out/'live-identity.json',actual);timed=False
        try:process.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            timed=True;os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
    life.save(out/'terminal.json',dict(returncode=process.returncode,timeout=timed,actual_dve=actual));verify(out,seal)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=('prepare','run','verify','el'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seal');ap.add_argument('--file')
    a=ap.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    elif a.mode=='el':
        c=json.loads((out/'config.json').read_bytes());print(json.dumps(dict(bit_directions=len(parse_el((out/a.file).read_text(),c)))))
    else:(run if a.mode=='run' else verify)(out,a.seal)
