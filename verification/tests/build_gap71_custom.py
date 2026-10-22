#!/usr/bin/env python3
"""New gap71 apps: LLVM builds, independent host oracle, software Spike, no EDA."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
SCRIPT=Path(__file__).resolve()
LEGACY=ROOT/'verification/tests/build_gap38_i8_f16_lane3.py'
spec=importlib.util.spec_from_file_location('gap71_build_helper',LEGACY)
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
sha,save,read,pins,verify,require=(getattr(helpers,n) for n in ('sha','save','read','pins','verify','require'))
sys.path.insert(0,str(ROOT/'verification/coverage'))
sys.path.insert(0,str(ROOT/'verification'))
import audit_gap71_custom as audit
import coverage_evidence as evidence
import run_gap71_custom_checked_extension as adapter
from reviewed_20261004 import audit_readonly as native
BASE=ROOT/'verification/out/closure90-current-20261005-01'
INV=ROOT/'verification/out/closure90-zero-inventory-654-20261005-01/inventory.json'
UNIT=ROOT/'verification/tests/test_gap71_custom.py'
HOST=ROOT/'verification/tests/gap71_host_reference.c'

def baseline_audit():
    p=evidence.Evidence();plan=p.plan(BASE);cp=p.read(BASE/'checkpoint.json');collection=p.read(BASE/'collection.json')
    require(cp['coverage_status']=='COMPLETE' and cp['aggregate_passed']==654 and collection['status']=='PASS' and collection['passed']==654,'completed654 required')
    for rel in ('all-passed-outcomes.json','combined-bits.json','combined-dve/inputs.txt','combined-dve/summary.csv'):
        p.pin(BASE/rel,collection['reports'][str(BASE/rel)])
    bits=read(BASE/'combined-bits.json');rows=read(BASE/'all-passed-outcomes.json')
    inputs=(BASE/'combined-dve/inputs.txt').read_text().splitlines()
    require(len(rows)==654 and bits['tests']==inputs[1:]==[r['vdb'] for r in rows] and inputs[0]==plan['design_vdb'],'654 membership differs')
    require(all(r['status']=='PASS' and r['passed_only'] and r['vdb_valid'] for r in rows),'failed outcome admitted')
    require(not any(r['name'] in audit.CASE_NAMES for r in rows),'candidate already exists')
    inv=p.read(INV);require(inv['passed']==654 and inv['baseline']==str(BASE) and inv['status']=='DIAGNOSTIC_NOT_SIGNOFF','wrong diagnostic')
    frozen=p.read(ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json')
    cfg=p.read(ROOT/'verification/out/gap52-system-preflight-20261004-01/config-audit.json')
    sources=dict(cfg['frozen_rtl']);source=str(ROOT/'hardware/src/vlsu/qbs/qbs_read_engine.sv');sources[source]=frozen[source]
    require(all(frozen[k]==v for k,v in sources.items()),'freeze manifest drift');p.hashes(sources)
    d=native.Design(plan['design_vdb']);shape=native.xml(d.db/'shape/cond.verilog.shape.xml')
    info=native.xml(d.db/'shape/cond.verilog.info.xml')
    for path in (d.db/'design/verilog.design.xml',d.db/'auxiliary/verilog.sourceinfo.xml',d.db/'shape/cond.verilog.shape.xml',d.db/'shape/cond.verilog.info.xml'):
        p.pin(path,bits['design'].get(str(path.relative_to(d.db))))
    defs=[x for x in shape.findall('conddef') if x.get('id')=='-59'];require(len(defs)==1,'ambiguous reader definition')
    definition=defs[0];require(definition.get('chksum')=='1540454284','condition checksum differs')
    exprs=sorted(definition.iter('expr_monitored'),key=lambda n:int(n.get('condregid')))
    targets=[];offset=0
    for expr in exprs:
        t=expr.find('truth_table');n=int(t.get('nrows'));cols=int(t.get('ncols'));cid=int(expr.get('condregid'))
        if cid in audit.TARGETS:
            for raw,vec in audit.TARGETS[cid]:
                row=offset+n-1-raw
                require(0<=row<n and t.get('vecs')[row*cols:(row+1)*cols]==vec,'native row reversal differs')
                template=next(x for x in inv['source_points'] if x['metric']=='cond' and x['scope']==audit.SCOPES[0] and x['raw_index']==raw)
                require(template['native_id']==str(cid) and template['vector']==vec and template['source_sha256']==sources[source] and template['attributes']==dict(expr.attrib),'diagnostic/native/source identity differs')
                for scope in audit.SCOPES:
                    module=d.hierarchy[scope];r=bits['metrics']['cond'][scope]
                    require(module.get('id')=='-59' and module.get('name')=='qbs_read_engine' and r['width']==290,'shared module identity differs')
                    require(r['checksum']==('1540454284' if scope==audit.SCOPES[0] else None),'raw checksum semantics differ')
                    require(format(int(r['bits'],16),'0290b')[raw]=='0','target no longer zero')
                    targets.append(dict(scope=scope,raw_index=raw,condregid=cid,vector=vec,expression=expr.get('exprstr'),
                        source=source,source_sha256=sources[source],native_module_id='-59',native_cond_checksum='1540454284',
                        native_dve_qualified=False,measured_gain=None))
        offset+=n
    require(offset==290 and len(targets)==22,'target total/shape differs')
    require('cfg.NrPMPEntries          = 0;' in (ROOT/'hardware/src/ara_soc.sv').read_text(),'PMP0 missing')
    return dict(status='PASS_LIGHTWEIGHT_PREPARATION_ONLY',baseline=str(BASE),passed=654,
        coverage_status='COMPLETE',design_vdb=plan['design_vdb'],targets=targets,checked_files=p.files,
        native_dve_qualified=False,image_bytes_rehashed=False,historical_raw_rehashed=False,full_admission_deferred=True)

def metadata(b,elf,label,name,software):
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],label+'.disassembly')
    r=b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols','--program-headers',elf],label+'.metadata')
    return dict(elf=str(elf),elf_sha256=sha(elf),metadata=audit.metadata(json.loads(r.stdout)[0],elf.read_bytes(),name,software))

def host_oracle(b,names):
    objs=[b.compile(HOST,'host-test',host=True),b.compile(ROOT/'verification/qbs/qbs_ref.c','host-ref',host=True)]
    exe=b.out/'host-reference';b.link([b.host,*objs,'-lm','-o',exe],'host-reference.link')
    r=b.run([exe],'host-reference',timeout=30);log=r.stdout.decode();actual=[]
    for line in log.splitlines():
        if line.startswith('P '):
            _,a,f,p,i,v=line.split();actual.append((int(a),int(f),int(p),int(i),int(v,16)))
    expected=[(a,f,p,i,v) for a in range(2) for f in range(2) for p,page in enumerate(audit.pages(0x80040000,a,f)) for i,v in enumerate(page)]
    require(actual==expected,'independent complete pages differ')
    q=[line for line in log.splitlines() if line.startswith('Q ')]
    require(q==['Q %d %d %08x'%(f,i,0xc0c00000 if i==0 else 0) for f in range(2) for i in range(32)],'independent QBS reference result differs')
    for name in names:
        line='PASSED: %s checks=%d errors=0'%(name,192 if 'akv' in name else 36)
        require(log.splitlines().count(line)==1,'missing host result');(b.out/(name+'.host.log')).write_text(line+'\n')
    save(b.out/'oracle-check.json',dict(status='PASS',complete_page_words=12288,numeric_fp32_words=64,
         oracle='Python sparse PPN/flags/byte construction vs C constructor, frozen QBS numerical reference; AKV byte copies',
         custom_instruction_execution_prechecked=False,host_binary=str(exe),host_binary_sha256=sha(exe)))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases',nargs='+',choices=audit.CASE_NAMES,default=list(audit.CASE_NAMES))
    parser.add_argument('--vcs-timeout',type=int,choices=(300,1800),default=300)
    args=parser.parse_args();out=args.output.resolve();names=args.cases
    require(ROOT==Path('/home/wangwy/openproject/ara_dsa_signoff_integration'),'wrong worktree')
    require(len(set(names))==len(names) and out.parent==ROOT/'verification/out' and out.name.startswith('gap71-custom-preflight-') and not out.exists(),'fresh gap71 output required')
    baseline=baseline_audit();planpath=ROOT/'verification/out/repaired-aligned-600-20260930-01/plan.json'
    old=next(c for c in read(planpath)['cases'] if c.get('spike'));spike=Path(old['spike']);require(sha(spike)==old['spike_sha256'],'Spike drift')
    protected=dict(baseline['checked_files']);protected.update(pins([LEGACY,planpath]))
    out.mkdir();save(out/'baseline-targets.json',baseline);save(out/'protected-inputs.json',protected)
    b=helpers.Build(out);b.sources=pins([SCRIPT,HOST,UNIT,Path(audit.__file__),adapter.SCRIPT,LEGACY,ROOT/'apps/common/gap71_data.h',ROOT/'apps/common/gap71_sv39_custom.h',*[ROOT/'apps'/n/'main.c' for n in names]])
    b.tools.update(pins([spike,ROOT/'verification/tools/soc-venv/bin/python']))
    b.run([sys.executable,'-B',UNIT,'-v'],'unit-tests');host_oracle(b,names)
    common=[b.compile(b.common/n,'dut-'+n) for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    runtime=ROOT/'apps/riscv-tests/benchmarks/common'
    extra=['-D__SPIKE__=1','-DGAP71_SOFTWARE_REFERENCE=1','-DPREALLOCATE=1','-I'+str(runtime),'-I'+str(ROOT/'apps/riscv-tests/env'),'-fno-function-sections','-fno-data-sections']
    spikecommon=[b.compile(s,n,extra) for s,n in ((runtime/'crt.S','spike-crt'),(runtime/'syscalls.c','spike-syscalls'))]
    executions={}
    for name in names:
        src=ROOT/'apps'/name/'main.c';(out/(name+'.source.snapshot')).write_bytes(src.read_bytes())
        elf=out/(name+'.elf');obj=b.compile(src,name+'.dut')
        b.bind_sources([b.common/'link.ld']);b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections','-T'+str(b.common/'link.ld'),obj,*common,'-lm','-L'+str(b.llvm/'lib/generic'),'-lclang_rt.builtins-riscv64','-o',elf],name+'.dut.link')
        fit=ROOT/'verification/coverage/check_elf_fit.py';b.bind_sources([fit]);b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',elf,'--ram-bytes','0x200000','--output',out/(name+'.fit.json')],name+'.fit')
        dut=metadata(b,elf,name+'.dut',name,False)
        soft=out/(name+'.software-reference.spike');obj=b.compile(src,name+'.spike',extra)
        b.bind_sources([runtime/'test.ld']);b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostdlib','-T'+str(runtime/'test.ld'),obj,*spikecommon,'-o',soft],name+'.spike.link')
        spi=metadata(b,soft,name+'.spike',name,True)
        command=[str(spike),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(soft)]
        r=b.run(command,name+'.spike-run',timeout=30)
        uart=audit.validate_log(r.stdout.decode(),name,'software-reference');trace=audit.spike_trace(r.stderr.decode(),name,spi['metadata'])
        executions[name]=dict(status='PASS',dut=dut,spike=spi,command=command,uart=uart,trace=trace,
            stdout=str(out/(name+'.spike-run.log')),trace_log=str(out/(name+'.spike-run.stderr.log')),
            custom_instruction_execution_prechecked=False,vcs_launched=False,vcs_timeout_s=args.vcs_timeout)
    save(out/'execution-proof.json',executions)
    b.run([sys.executable,'-B',UNIT,'--preflight',out,'-v'],'real-trace-unit-tests')
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values()) if getattr(m,'__file__',None) and str(Path(m.__file__).resolve()).startswith(str(ROOT/'verification'))])
    for h in (b.sources,b.tools,b.link_inputs,protected):verify(h)
    save(out/'source_hashes.json',b.sources);save(out/'tool_hashes.json',b.tools);save(out/'link-inputs.json',b.link_inputs)
    items=[]
    for name in names:
        run=executions[name];hostlog=out/(name+'.host.log');record=out/(name+'.precheck.json')
        save(record,dict(name=name,binary=run['dut']['elf'],binary_sha256=run['dut']['elf_sha256'],source_hashes=b.sources,
            sources=sorted(b.sources),host_reference=str(HOST),host_log=str(hostlog),host_result=hostlog.read_text().strip(),
            custom_instruction_execution_prechecked=False,vcs_launched=False))
        items.append(dict(name='app:'+name,binary=run['dut']['elf'],binary_sha256=run['dut']['elf_sha256'],
            sources=sorted(b.sources),source_hashes=b.sources,timeout_s=args.vcs_timeout,targets=[audit.SCOPES[int('akv' in name)]],
            source_audit='Actual S/Sv39 nonidentity R/A leaves; complete PTE/data/guards/VRF/CSR checks. '
              'Frozen host numerical QBS reference or independent AKV byte copies; actual Spike software reference ONLY; custom RTL untested.',
            rationale='COMPLETE654 still-zero shared reader raw rows; prospective, not measured internal signals.',
            precheck=dict(format='accel-host-v1',record=str(record),log=str(hostlog))))
    artifacts=pins(p for p in out.iterdir() if p.is_file());save(out/'artifact_hashes.json',artifacts)
    for item in items:item['evidence']=sorted([*artifacts,str(out/'artifact_hashes.json')])
    draft=out/'selection.checked-draft.json';save(draft,dict(status='CHECKED_DRAFT_HOST_AND_SOFTWARE_SPIKE_ONLY',
        baseline=str(BASE),baseline_bits=str(BASE/'combined-bits.json'),cases=items,vcs_launched=False,
        full_admission_deferred=True,waivers_applied=False,measured_gain=None))
    checked={}
    for item in items:
        p=evidence.Evidence();p.pin(draft)
        for h in (b.tools,b.link_inputs,protected,artifacts):p.hashes(h)
        result=evidence.precheck(item,p);checked[item['name']]=dict(status='PASS',result=result,checked_files=p.files)
    save(out/'checked-precheck.json',checked);save(out/'draft.sha256.json',pins([draft,out/'checked-precheck.json',out/'artifact_hashes.json']))
    adapter.install_hooks();sealed={}
    for item in items:
        p=evidence.Evidence();result=evidence.precheck(item,p)
        require(result==checked[item['name']]['result'],'sealed result differs');sealed[item['name']]=dict(status='PASS',result=result,checked_files=p.files)
    save(out/'sealed-replay.json',sealed);verify(protected)
    for name,run in executions.items():print('PASS: %s software Spike checks=%d retired=%d; custom NOT executed'%(name,run['uart']['checks'],run['trace']['retired']))
    print(draft)

if __name__=='__main__':main()
