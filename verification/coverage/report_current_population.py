"""Explicit admitted population, unchanged777 native policy, one five-stage report.

No mutation of frozen helpers. Coverage-only observer/trusted-IP policies are
not unreachable claims; zero-activity contracts remain separately identified.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
from types import FunctionType
import xml.etree.ElementTree as ET
import report_global777_compact as stable

life, need, OUT = stable.life, stable.need, stable.OUT
SCHEMA = 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_STAGE_V1'
METRIC_COUNTS = dict(line=1892, cond=2023, branch=2155, fsm=92)
ANCHOR_MANIFEST = stable.inherited.BASE / 'admission-manifest.json'
ANCHOR_SHA = stable.inherited.BASE_SHA


def population_gate(previous, current, single, ledger, new_ledger):
    count = len(current['tests'])
    stable.inherited.chain_gate(previous,current,single,count,ledger,new_ledger)
    need(set(current['metrics']) == set(METRIC_COUNTS), 'Four exact metric families')
    for metric, expected in METRIC_COUNTS.items():
        need(len(current['metrics'][metric]) == expected, 'Exact per-metric instance count')
        for dataset in (previous,current,single):
            for row in dataset['metrics'][metric].values():
                bits, width = int(row['bits'],16), row['width']
                need(type(width) is int and width >= 0 and bits >= 0 and bits.bit_length() <= width,
                     'Raw bitmap outside compiled width')


def genealogy(reader, manifest, seal, anchor_bits, anchor_ledger):
    stack, seen = [], set()
    path, sha = manifest, seal
    while path != ANCHOR_MANIFEST:
        need(path.name == 'admission-manifest.json' and path.is_absolute() and OUT in path.parents and path not in seen,
             'Missing/cyclic explicit admission chain')
        seen.add(path)
        item = reader.read(path,sha,True)
        need(item['coverage_admitted'] is True and item['output'] == str(path.parent), 'Formal admission required')
        parent = Path(item['baseline'])/'admission-manifest.json'
        need(parent.is_absolute() and parent != path, 'Explicit prior manifest required')
        stack.append((path,sha,item)); path,sha = parent,item['baseline_seal']
    need(sha == ANCHOR_SHA, 'Wrong777 ancestor seal')
    previous, ledger, pins, records = anchor_bits,anchor_ledger,{},[]
    for path,sha,item in reversed(stack):
        pins = stable.merge(pins,item['input_pins'],item['output_pins'],{str(path):sha})
        def document(name, parse=True):
            target=path.parent/name
            return reader.read(target,item['output_pins'][str(target)],parse)
        current,single,status = document('combined-bits.json'),document('single-bits.json'),document('status.json')
        new_ledger=document('combined-inputs.txt',False).decode().splitlines()
        population_gate(previous,current,single,ledger,new_ledger)
        count=len(current['tests'])
        need(status['coverage_admitted'] is True and status['aggregate_passed'] == count
             and status['full_OR_metric_instances'] == 6162, 'Complete admitted population status')
        for name,data_sha in current['design'].items():
            target=Path(new_ledger[0])/'snps/coverage/db'/name
            need(pins.get(str(target)) == data_sha, 'Compiled design/shape ownership')
        need(bool(single['input_hashes']) and all(pins.get(p)==h for p,h in single['input_hashes'].items()), 'Admitted single raw-data ownership')
        records.append(dict(manifest=str(path),seal=sha,population=count,new_vdb=single['tests'][0]))
        previous,ledger=current,new_ledger
    need(len(previous['tests'])>=777 and ledger[:778]==anchor_ledger, 'Exact777 population prefix')
    return previous,ledger,pins,records


def selected_tests(ledger):
    selected=[]
    for db in ledger:
        directory=Path(db)/'snps/coverage/db/testdata'
        if not directory.exists(): continue
        for entry in sorted(directory.iterdir()):
            need(entry.is_dir() and not entry.is_symlink(), 'Unknown/aliased testdata member')
            selected.append(str(Path(db).with_suffix('')/entry.name))
    stable.membership(ledger,selected,len(ledger)-1)
    return selected


def zero_row(row, width, checksum, positions):
    need((row['width'],row['checksum'])==(width,checksum) and len(positions)==len(set(positions)),
         'Exact source-bound raw shape/positions')
    bits=int(row['bits'],16)
    need(bits>=0 and bits.bit_length()<=width and all(type(i) is int and 0<=i<width for i in positions),
         'Explicit bounded raw coordinates')
    need(all(not(bits>>(width-1-i)&1) for i in positions), 'Source-zero target activated by admitted suffix')


def suffix_activity(reader,source,pins,records,bitmap):
    # These physical raw mappings are already explicitly source/native bound.
    # Never derive an MDA bit ordering or call active trusted-IP fields constant.
    proof=reader.read(stable.PROOF,stable.PROOF_SHA,True)
    typed=stable.cvx.base.proof.typed
    db=Path(source['input_ledger'][0])/'snps/coverage/db'
    trees=[]
    for relative in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml'):
        path=db/relative; raw=reader.read(path,pins[str(path)])
        trees.append(ET.fromstring(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw))
    checks,defs=typed.definitions(*trees,stable.cvx.base.proof.SCOPES)
    shapes={}
    for scope in stable.cvx.base.proof.SCOPES:
        _,_,width=stable.cvx.base.proof.bind_scope(scope,ET.fromstring(defs[scope]['shape']),checks[scope],defs[scope]['module']['chksum'])
        shapes[scope]=(width,checks[scope])
    mask_scope=stable.inherited.predecessor.strict.qualification.source.SCOPE
    mask=source['masku_raw776']; branch=source['branch720']
    branches=[r for r in branch['branch_inventory'] if r['target']]
    need(len(branches)==720 and len(mask['positions'])==512,'Closed source-zero native contract')
    audits=[]
    for record in records:
        folder=Path(record['new_vdb'])/'snps/coverage/db/testdata'
        folders=sorted(folder.iterdir())
        need(len(folders)==1 and folders[0].is_dir(),'Exactly one new admitted coverage test')
        path=folders[0]/'tgl.verilog.data.xml'
        rows,sha=typed.rows(path,[*shapes,mask_scope])
        need(pins.get(str(path))==sha,'Suffix Toggle admission identity')
        for target in proof['targets']:
            zero_row(rows[target['scope']],*shapes[target['scope']],target['raw_positions'])
        zero_row(rows[mask_scope],mask['union']['width'],mask['union']['checksum'],mask['positions'])
        # Branch native selector binding is reused; raw index is not guessed GUI ID.
        single_path=Path(record['manifest']).parent/'single-bits.json'
        single=reader.read(single_path,pins[str(single_path)],True)
        for target in branches:
            row=single['metrics']['branch'][target['scope']]
            anchor=bitmap['metrics']['branch'][target['scope']]
            zero_row(row,anchor['width'],anchor['checksum'],[target['raw_index']])
        audits.append(dict(population=record['population'],vdb=record['new_vdb'],tgl_sha256=sha,
            CVXIF_zero_directions=18516,MASKU_zero_directions=512,parameter_false_branches=720))
    return dict(suffixes=audits,policy='Same approved EL; source-zero contracts checked, active integration policies not reclassified unreachable',
        blanket_all_EL_inactive_claim=False)


def approved(reader,manifest,seal):
    source,pins,text,anchor=stable.approved(reader)
    current,ledger,extra,chain=genealogy(reader,manifest,seal,anchor,source['input_ledger'])
    pins=stable.merge(pins,extra)
    # Preserve777 source/native books and every module root; replace population only.
    activity=suffix_activity(reader,source,pins,chain,anchor)
    source=dict(source,input_ledger=ledger,expected_selected=selected_tests(ledger))
    return source,stable.merge(pins,reader.pins),text,current,chain,activity


def dependencies():
    files=(Path(__file__).resolve(),Path(__file__).with_name('test_report_current_population.py'),
        stable.HERE/'test_report_global777_compact.py',
        Path(stable.__file__).resolve(),stable.TCL,stable.EXPORT,stable.ROOT_HELPER,
        Path(stable.inventory.__file__).resolve(),Path(stable.tools.__file__).resolve(),stable.HERE/'report_scope_ancestors.py')
    return {str(p):life.digest(p) for p in files}


def prepare(out,manifest,seal,unit):
    need(out.parent==OUT and not out.exists(),'Fresh report output')
    need(re.fullmatch(r'ara-[a-zA-Z0-9-]+\.service',unit),'Explicit owning service')
    reader=stable.Reader(); source,pins,text,bits,chain,activity=approved(reader,manifest,seal)
    pins=stable.merge(pins,dependencies()); reader.finish(pins); stable.tools.revalidate(source['tool_identity'])
    population=len(bits['tests'])
    config=dict(schema=SCHEMA,output=str(out),successor_entry=str(Path(__file__).resolve()),population=population,
        admission=dict(path=str(manifest),sha256=seal),reference=dict(path=str(stable.REFERENCE/'config.json'),sha256=stable.REFERENCE_SHA),
        input_ledger=source['input_ledger'],expected_selected=source['expected_selected'],hierarchy_roots=source['hierarchy_roots'],
        tool_identity=source['tool_identity'],pins=pins,expected_EL_semantic_sha256=stable.semantic_seal(stable.semantic(text)),
        genealogy=chain,suffix_activity=activity,timeout_seconds=3600,owner_uid=os.getuid(),owning_service_unit=unit,
        expected_cgroup='/user.slice/user-%d.slice/user@%d.service/app.slice/%s'%(os.getuid(),os.getuid(),unit),
        full_OR_metric_instances=6162,raw_hierarchy_rows=2989,official_denominator_verified=False,
        new_exclusions_added=False,GUI_singleton_inventory_hooks=False,parent_launch_approval_required=True)
    out.mkdir()
    for name,data in [('combined.el',text),('inputs.txt','\n'.join(source['input_ledger'])+'\n'),('root-selection.tcl',stable.selection(source['hierarchy_roots']))]:
        (out/name).write_text(data); pins[str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',config); config_seal=life.digest(out/'config.json')
    life.save(out/'prepare-receipt.json',dict(status='CURRENT_POPULATION_PREPARED_NOT_LAUNCHED',population=population,
        config_seal=config_seal,manifest_seal=seal,source_native_pins=len(pins),module_roots=72,
        EDA_launched=False,official_percentage=None,suffix_activity=activity))
    print(json.dumps(dict(output=str(out),population=population,seal=config_seal,pins=len(pins))),flush=True)


def check(out,seal):
    config=stable.Reader().read(out/'config.json',seal,True)
    need(config['schema']==SCHEMA and config['output']==str(out) and config['successor_entry']==str(Path(__file__).resolve()),'Exact consumer identity')
    reader=stable.Reader(); source,pins,text,bits,chain,activity=approved(reader,Path(config['admission']['path']),config['admission']['sha256'])
    need(config['population']==len(bits['tests']) and config['input_ledger']==source['input_ledger']
        and config['expected_selected']==source['expected_selected'] and config['hierarchy_roots']==source['hierarchy_roots']
        and config['tool_identity']==source['tool_identity'] and config['genealogy']==chain and config['suffix_activity']==activity,
        'Population/source/native/module contract drift')
    need(all(config['pins'].get(p)==h for p,h in stable.merge(pins,dependencies()).items()),'Omitted dependency obligation')
    need(config['timeout_seconds']==3600 and config['official_denominator_verified'] is False
        and config['new_exclusions_added'] is False and config['GUI_singleton_inventory_hooks'] is False
        and config['full_OR_metric_instances']==6162 and config['raw_hierarchy_rows']==2989
        and config['owner_uid']==os.getuid() and type(config['owner_uid']) is int
        and re.fullmatch(r'ara-[a-zA-Z0-9-]+\.service',config['owning_service_unit'])
        and config['expected_cgroup']=='/user.slice/user-%d.slice/user@%d.service/app.slice/%s'%
            (os.getuid(),os.getuid(),config['owning_service_unit']), 'No scope/gate/lifecycle expansion')
    need((out/'inputs.txt').read_text().splitlines()==source['input_ledger'] and
        (out/'root-selection.tcl').read_text()==stable.selection(source['hierarchy_roots']) and
        (out/'combined.el').read_text()==text and config['expected_EL_semantic_sha256']==stable.semantic_seal(stable.semantic(text)),
        'Exact generated input/root/native union')
    reader.finish(config['pins']); stable.tools.revalidate(config['tool_identity'])
    need(life.digest(out/'config.json')==seal,'Config changed during check')
    return config


def verify(out,seal):
    config=check(out,seal)
    terminal=json.loads((out/'terminal.json').read_bytes()); stable.terminal_gate(terminal,config)
    need(terminal['config_seal']==seal,'Executed seal')
    stable.membership(config['input_ledger'],(out/'selected_tests.txt').read_text().splitlines(),config['population'])
    paths=[out/name for name in ('terminal.json','execution.json','selected_tests.txt','raw.csv')]; reports={}
    for stage in stable.STAGES:
        ep,sp=out/stable.EL_FILES[stage],out/('modules_'+stage+'.csv')
        stable.el_gate(ep.read_bytes(),stage,config['expected_EL_semantic_sha256'])
        reports[stage]=stable.summary(sp.read_bytes(),stage,config['hierarchy_roots']); paths.extend((ep,sp))
    stable.summaries_gate(reports); stable.raw_summary_gate((out/'raw.csv').read_bytes(),config['hierarchy_roots'],reports['raw'])
    gui=out/'DVEfiles/dve_gui.log'
    for path in (out/'launcher.log',gui): stable.diagnostics(path.read_text())
    lines=gui.read_text().splitlines()
    need(lines.count('COMPACT777_FIVE_PHASE_DONE')==lines.count('DVE_COVERAGE_EXPORT_DONE')==1,'Frozen protocol completed exactly once')
    need((out/'cleanup-empty.el').read_bytes()==b'','Final cleanup exact empty'); paths.append(out/'cleanup-empty.el')
    snapshots=out/'terminal-evidence'; snapshots.mkdir(exist_ok=True)
    for source in (out/'launcher.log',gui):
        dest=snapshots/source.name
        if dest.exists(): need(dest.read_bytes()==source.read_bytes(),'Immutable terminal snapshot drift')
        else: dest.write_bytes(source.read_bytes())
        paths.append(dest)
    result=dict(status='CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED',population=config['population'],
        config_seal=seal,admission_seal=config['admission']['sha256'],actual_selected_tests=config['population'],
        source_design_native_pins=config['pins'],output_pins={str(p):life.digest(p) for p in paths},
        complete_approved_EL_bitmask_union=True,all_other_bits_protected=True,raw_reset_final_equal=True,
        applied_reloaded_equal=True,module_reports=reports,suffix_activity=config['suffix_activity'],
        raw_hierarchy_vs_rooted_six_metrics_equal=True,supported_roots_all_six_metrics_present=True,
        official_denominator_verified=False,historical_PASS_only_no_new_RTL_signoff=True)
    target=out/'qualification.json'
    if target.exists(): need(json.loads(target.read_bytes())==result,'Existing qualification differs')
    else: life.save(target,result)
    print(json.dumps(dict(output=str(out),population=config['population'],seal=life.digest(target))),flush=True)
    return result


def run(out,seal,reviewed):
    # One direct private namespace for the unchanged reviewed lifecycle; no exec/shim chain.
    return FunctionType(stable.run.__code__,dict(stable.run.__globals__,check=check,verify=verify))(out,seal,reviewed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('mode',choices=('prepare','check','verify','run-reviewed'))
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--manifest',type=Path); parser.add_argument('--seal',required=True)
    parser.add_argument('--service-unit'); parser.add_argument('--parent-reviewed-seal'); args=parser.parse_args(); out=args.output.resolve()
    if args.mode=='prepare':
        need(args.manifest is not None and args.service_unit is not None,'Explicit admitted manifest/unit required')
        prepare(out,args.manifest.resolve(),args.seal,args.service_unit)
    else:
        need(args.manifest is None and args.service_unit is None,'Runtime uses sealed config, not mutable admission arguments')
        if args.mode=='check': check(out,args.seal); print('CURRENT_POPULATION_CHECK_PASS_NO_EDA',flush=True)
        elif args.mode=='verify': verify(out,args.seal)
        else: run(out,args.seal,args.parent_reviewed_seal)
