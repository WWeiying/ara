"""Exact724 + qualified GAP105 = historical725; explicit admission only, no EDA."""
import argparse
import hashlib
import json
from pathlib import Path

import qualify_gap105_native_v5 as qualifier
import coverage_bitmap_delta as bitmap
import closure_point_inventory as inventory

life,require = qualifier.life,qualifier.require
OUT = life.OUT
BASE = OUT/'akv-lifecycle-offline-admitted-724-parent-20261006-01'
BASE_SEAL = 'c7070c02860d4a6f5e12f405f926cd19fc6e6498d1905298e5e32826ee3a8ae0'
PRIOR = OUT/'narrow-reject-r1-cached-offline-admitted-723-20261006-01'
PRIOR_SEAL = '2f68f64b880b95164f8db6aa2b569d305bd831ad4a05056563b2ab42eade45a4'
QUAL = OUT/'gap105-native-qualifier-v5-ready-20261006-01'
QUAL_SEAL = '77a1291e96d477d56744100af93a0d0b4a4c97da4fbaccd523a7827d3f0000f5'
CONFIG = QUAL.with_name(QUAL.name+'.prepared.json')
CONFIG_SEAL = 'b4c17874fcc2ac13e39c78c68a5edd842dd6f28fc378b392a69ac0b298f28968'
RUN = OUT/'gap105-m8-phase8-old-image-parent-20261006-01'
RUN_SEAL = '85aff7d4b148a4eba850d48728fccda2c5c97d67df81e285c473bcfc19fa29d2'
RAW = OUT/'gap105-raw-diagnostic-parent-724-20261006-01'
RAW_PINS = {
    'single-bits.json':'a5f2cf4ab435a719693042898073c9139d40ab5086d3d97c355f75e202a65f56',
    'inputs.txt':'30e8f29525a97110b021d579489947576c319bdef6deba7ef679640931737576',
    'diagnostic-summary.json':'aea56b284fa3bf1e097b359ba8f157dd46679c3e67432c6f561a34cdcdf4f63f'}
DESIGN = OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'
SYSTEM = 'ara_tb.dut.i_ara_soc.i_system'
COMPUTE = SYSTEM+'.i_ara.i_vlsu.i_qbs_engine.i_compute_engine'
GAINS = {COMPUTE+'.i_block_adapter_bank0.i_payload_buffer':9,
         COMPUTE+'.i_block_adapter_bank1':44,
         COMPUTE+'.i_block_adapter_bank1.i_payload_buffer':138}
TARGET_SCOPE = COMPUTE+'.i_block_adapter_bank1.i_payload_buffer'
EXPECTED_DELTA = dict(line=0,cond=191,branch=0,fsm=0)


def bound(path, seal):
    path = Path(path)
    require(path.is_absolute() and path.resolve()==path and not path.is_symlink(),'Aliased evidence: '+str(path))
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==seal,'Expected evidence differs: '+str(path))
    return raw


def qualification_contract(record, audit):
    qualifier.frozen.runner.exact(record,dict(status='GAP105_SOFTWARE_NATIVE_V5_QUALIFIED_NOT_ADMITTED',
        full_scalar_isa_verified=False,coverage_admitted=False,coverage_increment_measured=False,
        gain_requires_latest_formal_baseline=True,simulation_rerun=False,rtl_changed=False),
        'Exact parent qualification differs')
    qualifier.frozen.runner.exact(audit,dict(status='COMPLETE_SOFTWARE_NATIVE_QUALIFIER_V5_PASS_NOT_FULL_SCALAR_ISA',
        custom_write_bytes=64,full_vrf_bytes=8192,initial_vrf_bytes=8192,csr_values=24,
        source_guard_bytes=6880,checks=41,full_scalar_isa_verified=False,
        spike_custom_isa_pass=False,coverage_admitted=False),'Software/native scope differs')
    require([(b['phase'],b['pc'],b['backend_vl'],b['software_vl'],b['native_active_write_bytes'])
             for b in audit['bindings']]==[(4,0x8000017a,256,1,32),(8,0x80000252,256,1,32)],
            'Exact two qualified commands differ')
    require(audit['contract']['requests']==audit['contract']['responses']==51 and
            all(audit['contract'][k]==0 for k in ('exceptions','protocol_errors','outstanding','req_stalled','resp_stalled')),
            'Qualified lifecycle differs')


def baseline_contract(manifest, status, before, prior):
    require(manifest['schema']=='AKV_LIFECYCLE_HISTORICAL724_ADMISSION_V1' and
            manifest['output']==str(BASE) and manifest['baseline']==str(PRIOR) and
            manifest['baseline_seal']==PRIOR_SEAL,'Not authoritative724 manifest')
    require(status['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and status['coverage_admitted'] is True and
            status['baseline']==723 and status['aggregate_passed']==724 and status['new_passed']==1,
            'Not formally admitted724')
    require(len(prior['tests'])==len(set(prior['tests']))==723 and
            len(before['tests'])==len(set(before['tests']))==724 and
            before['tests'][:-1]==prior['tests'],'Not exact sealed723 prefix in724')


def population(before, single):
    new = str(RUN/'code.vdb')
    require(len(before['tests'])==len(set(before['tests']))==724 and single['tests']==[new] and
            new not in before['tests'],'Wrong exact724/unique singleton population')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    combined = bitmap.combine(before,single)
    require(combined['tests']==before['tests']+[new] and len(set(combined['tests']))==725,
            'Not exact724 prefix plus one unique VDB')
    change = bitmap.delta(before,combined)
    require(change['metrics']==EXPECTED_DELTA,'Not exact fresh191 condition-only increment')
    require({r['instance']:r['new_bits'] for r in change['instances'] if r['metric']=='cond'}==GAINS and
            all(r['metric']=='cond' for r in change['instances']),'Unexpected gained product scope')
    return combined,change


def bit(row, raw):
    require(type(raw) is int and 0<=raw<row['width'],'Out-of-range raw coordinate')
    value = int(row['bits'],16)
    require(value>=0 and value.bit_length()<=row['width'],'Bitmap width overflow')
    return bool(value & (1<<(row['width']-1-raw)))


def condition_definition(shape, module, scope, row, info_checksum):
    if row['checksum'] is not None:
        require(str(row['checksum'])==info_checksum,'Native instance checksum mismatch')
        return inventory.definition(shape,module,row['checksum']),'exact_instance_checksum'
    # Only this actual adapter lacks per-instance checksum. Do not invent one.
    require(scope==COMPUTE+'.i_block_adapter_bank1' and info_checksum is None and row['width']==5914 and
            dict(module.attrib)==dict(id='-68',name='qbs_block_adapter',type='module',chksum='585070731'),
            'Unreviewed missing native instance checksum')
    candidates = [n for n in shape if n.get('id')==module.get('id')]
    require(len(candidates)==1 and candidates[0].get('chksum')=='2250470448',
            'Ambiguous/mismatched exact compiled adapter definition')
    return candidates[0],'unique_compiled_module_id_exact_width_instance_checksum_absent'


def compiled_gains(before, combined, pre, input_bytes):
    db = DESIGN/'snps/coverage/db'
    # Structured native hierarchy and actual per-instance condition checksums.
    design = inventory.read_xml(db/'design/verilog.design.xml')
    nodes = {n.get('id'):(n,d) for d in design.findall('srcdef') for n in d.findall('srcinst')}
    require(len(nodes)==sum(len(d.findall('srcinst')) for d in design.findall('srcdef')),'Duplicate hierarchy IDs')
    def path(key, visiting=()):
        require(key not in visiting,'Cyclic compiled hierarchy')
        node,_ = nodes[key]; parent = node.get('pid')
        return (path(parent,visiting+(key,))+'.' if parent in nodes else '')+node.get('name')
    hierarchy = {path(k):module for k,(_,module) in nodes.items()}
    require(len(hierarchy)==len(nodes),'Duplicate compiled scope')
    shape = inventory.read_xml(db/'shape/cond.verilog.shape.xml')
    info_path = db/'shape/cond.verilog.info.xml'; input_bytes(info_path)
    info = {n.get('name'):n.get('chksum') for n in inventory.read_xml(info_path).iter('instance_data')}
    source_path = db/'auxiliary/verilog.sourceinfo.xml'; input_bytes(source_path)
    files = {n.get('id'):n.get('name') for n in inventory.read_xml(source_path).iter('fileinfo')}
    result = []; target_hits = []
    for scope,count in GAINS.items():
        old,new = before['metrics']['cond'][scope],combined['metrics']['cond'][scope]
        definition,binding = condition_definition(shape,hierarchy[scope],scope,old,info.get(scope))
        mapped = {p['raw_index']:p for p in inventory.points('cond',definition,old['width'])}
        changed = [i for i in range(old['width']) if not bit(old,i) and bit(new,i)]
        require(len(changed)==count,'Gained condition count differs')
        for raw in changed:
            point = mapped[raw]
            source = Path(files[point['file_id']])
            input_bytes(source)
            require(source==life.ROOT/('hardware/src/vlsu/qbs/qbs_payload_buffer.sv' if
                    scope.endswith('i_payload_buffer') else 'hardware/src/vlsu/qbs/qbs_block_adapter.sv'),
                    'Unexpected gained source ownership')
            result.append(dict(scope=scope,metric='cond',checksum=old['checksum'],width=old['width'],
                               compiled_definition_checksum=definition.get('chksum'),binding=binding,
                               source=str(source),point=point,before_hit=False,after_hit=True))
        if scope==TARGET_SCOPE:
            require(old['width']==21503 and str(old['checksum'])=='2947893042' and
                    pre['scope']==scope and len(pre['targets'])==12,'Target shape differs')
            require(len({p['raw_index'] for p in pre['targets']})==12,'Duplicate target')
            for point in pre['targets']:
                raw = point['raw_index']
                require(mapped[raw]==point and raw in changed,'Complete target native identity/gain differs')
                target_hits.append(dict(scope=scope,point=point,before_hit=False,single_hit=True,after_hit=True))
    require(len(result)==191 and len(target_hits)==12,'Incomplete gained/target inventory')
    return result,target_hits


def evaluate(base_seal, qualification_seal):
    require(base_seal==BASE_SEAL and qualification_seal==QUAL_SEAL,'Only reviewed724/v5 qualification allowed')
    pins = {}
    def expected(path, seal):
        nonlocal pins
        pins = life.merge_pins(pins,{str(path):seal})
        return bound(path,seal)
    def read(path):
        require(str(path) in pins,'Missing expected evidence pin: '+str(path))
        return bound(path,pins[str(path)])
    record = json.loads(expected(QUAL/'qualification.json',QUAL_SEAL))
    audit = json.loads(expected(QUAL/'runtime-audit.json',record['audit_sha256']))
    qualification_contract(record,audit)
    pins = life.merge_pins(pins,json.loads(expected(QUAL/'evidence-pins.json',record['pins_sha256'])))
    config = json.loads(expected(CONFIG,CONFIG_SEAL))
    require(config['status']=='GAP105_NATIVE_QUALIFIER_V5_PREPARED_NOT_EXECUTED' and
            config['run']==str(RUN) and config['run_prepared_seal']==RUN_SEAL,'Qualification/run binding differs')
    require(life.merge_pins(pins,config['pins'])==pins,'Qualification did not preserve every prepared pin')
    manifest = json.loads(expected(BASE/'admission-manifest.json',BASE_SEAL))
    require(all(Path(p).parent==BASE for p in manifest['output_pins']),'Foreign baseline product')
    pins = life.merge_pins(pins,manifest['output_pins'])
    pins = life.merge_pins(pins,json.loads(read(BASE/'evidence-pins.json')))
    prior_manifest = json.loads(expected(PRIOR/'admission-manifest.json',PRIOR_SEAL))
    pins = life.merge_pins(pins,{str(PRIOR/'combined-bits.json'):prior_manifest['output_pins'][str(PRIOR/'combined-bits.json')]})
    before = json.loads(read(BASE/'combined-bits.json')); prior = json.loads(read(PRIOR/'combined-bits.json'))
    baseline_contract(manifest,json.loads(read(BASE/'status.json')),before,prior)
    require(read(BASE/'combined-inputs.txt').decode().splitlines()==[str(DESIGN),*before['tests']],
            'Exact724 input order/design differs')
    raw_data = {n:expected(RAW/n,h) for n,h in RAW_PINS.items()}
    single = json.loads(raw_data['single-bits.json'])
    require(raw_data['inputs.txt'].decode().splitlines()==[str(DESIGN),str(RUN/'code.vdb')],
            'Singleton input/design identity differs')
    summary = json.loads(raw_data['diagnostic-summary.json'])
    require(summary['single_bitmap_sha256']==RAW_PINS['single-bits.json'] and
            summary['baseline_seal']==BASE_SEAL and summary['raw_delta']==EXPECTED_DELTA and
            summary['coverage_admitted'] is False,'Diagnostic provenance differs')
    pins = life.merge_pins(pins,single['input_hashes'])
    pins = life.merge_pins(pins,before['input_hashes'])
    pins = life.merge_pins(pins,{str(DESIGN/'snps/coverage/db'/p):h for p,h in before['design'].items()})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_gap105_offline.py'),
                 Path(bitmap.__file__).resolve(),Path(inventory.__file__).resolve(),
                 Path(inventory.score.__file__).resolve()):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    # All expected maps are merged before any native replay; no dictionary overwrite.
    life.check(pins)
    prepared = json.loads(expected(RUN.with_name(RUN.name+'.prepared.json'),RUN_SEAL))
    require(json.loads(read(RUN/'manifest.json'))==prepared and prepared['command']==qualifier.frozen.runner.command(RUN)
            and prepared['old_image_files_checked']==66,'Unique fixed ELF/image runtime differs')
    pre = prepared['preflight']; qualifier.frozen.runner.validate(pre)
    terminal = json.loads(read(RUN/'simulation-status.json'))
    require(terminal['status']=='SIMULATION_EXITED_NOT_ADMITTED' and terminal['returncode']==0 and
            terminal['coverage_admitted'] is False,'Not successful terminal runtime')
    symbols,data,sites = qualifier.frozen.elf_view()
    actual = qualifier.runtime(RUN,symbols,data,sites,qualifier.frozen.independent_native())
    require(actual==audit,'Actual complete software/native replay differs from parent qualification')
    combined,change = population(before,single)
    gained,targets = compiled_gains(before,combined,pre,read)
    life.check(pins)
    outputs = {'combined-bits.json':combined,'raw-delta.json':change,
        'gained-compiled-points.json':gained,'target-hits.json':targets,'native-runtime-audit.json':actual,
        'evidence-pins.json':pins,'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',
            baseline=724,aggregate_passed=725,new_passed=1,coverage_admitted=True,
            exact724_prefix=True,qualification_seal=QUAL_SEAL,raw_delta=change['metrics'],
            raw_delta_scope=SYSTEM,targets_hit=12,gained_compiled_conditions=191,
            full_scalar_isa_verified=False,native_Spike_comparison=False,
            complete_software_native_qualified=True,whole_VRF_CSR_source_guards_qualified=True,
            checks=41,exceptions=0,custom_commands=2,custom_active_write_bytes=64,
            historical_old_image_only=True,inherited724_replayed=False,inherited724_pins_rechecked=True,
            singleton_bitmap_recollected=False,official_DVE_report=False,
            rtl_changed=False,new_RTL_signoff=False,simulations_started=False)}
    return outputs,'\n'.join([str(DESIGN),*combined['tests']])+'\n'


def fingerprints(output, outputs, text):
    pins = {str(output/name):hashlib.sha256((json.dumps(value,indent=2)+'\n').encode()).hexdigest()
            for name,value in outputs.items()}
    pins[str(output/'combined-inputs.txt')] = hashlib.sha256(text.encode()).hexdigest()
    return pins


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','admit','verify'))
    parser.add_argument('--base-seal',required=True); parser.add_argument('--qualification-seal',required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--seal')
    args = parser.parse_args(argv); output = args.output.absolute()
    require(output.parent==OUT and output.resolve()==output,'Direct independent output required')
    require((args.mode!='prepare')==bool(args.seal),'Admit/verify require external seal')
    record = output.with_name(output.name+'.prepared.json')
    if args.mode=='verify':
        manifest = json.loads(bound(output/'admission-manifest.json',args.seal))
        require(manifest['schema']=='GAP105_HISTORICAL725_SOFTWARE_NATIVE_ADMISSION_V1' and
                manifest['output']==str(output) and manifest['baseline_seal']==args.base_seal and
                manifest['qualification_seal']==args.qualification_seal,'Formal admission identity differs')
        for p,h in manifest['output_pins'].items():
            require(Path(p).parent==output,'Foreign formal product'); bound(p,h)
    else:
        require(not output.exists(),'Fresh725 output required')
        if args.mode=='prepare': require(not record.exists(),'Fresh prepared record required')
    outputs,text = evaluate(args.base_seal,args.qualification_seal)
    hashes = fingerprints(output,outputs,text)
    if args.mode=='verify':
        require(manifest['output_pins']==hashes,'Formal outputs differ from independent reconstruction')
        print('GAP105_HISTORICAL725_SOFTWARE_NATIVE_OFFLINE_REVERIFIED '+args.seal); return
    proposal = dict(schema='GAP105_HISTORICAL725_PREPARED_V1',output=str(output),
        baseline=str(BASE),baseline_seal=args.base_seal,qualification=str(QUAL),
        qualification_seal=args.qualification_seal,raw_singleton=str(RAW/'single-bits.json'),
        raw_singleton_seal=RAW_PINS['single-bits.json'],input_pins=outputs['evidence-pins.json'],
        output_pins=hashes,raw_delta=EXPECTED_DELTA,full_scalar_isa_verified=False)
    if args.mode=='prepare':
        life.save(record,proposal)
        print(json.dumps(dict(prepared=str(record),seal=life.digest(record)))); return
    require(json.loads(bound(record,args.seal))==proposal,'Reviewed725 proposal differs')
    require(not output.exists(),'Output appeared during audit')
    output.mkdir()
    for name,value in outputs.items(): life.save(output/name,value)
    with (output/'combined-inputs.txt').open('x') as stream: stream.write(text)
    life.check(outputs['evidence-pins.json'])
    for p,h in hashes.items(): bound(p,h)
    life.save(output/'admission-manifest.json',dict(schema='GAP105_HISTORICAL725_SOFTWARE_NATIVE_ADMISSION_V1',
        output=str(output),baseline=str(BASE),baseline_seal=args.base_seal,qualification=str(QUAL),
        qualification_seal=args.qualification_seal,prepared=str(record),prepared_seal=args.seal,output_pins=hashes))
    print(json.dumps(dict(output=str(output),seal=life.digest(output/'admission-manifest.json'),aggregate_passed=725)))


if __name__=='__main__': main()
