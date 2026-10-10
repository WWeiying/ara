"""Exact731 zeros and old-source identity for GAP109; predictions, not coverage."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'verification/coverage'))
import prepare_gap107_raw_gain_v2 as mapping

BASE = ROOT/'verification/out/pure-war-offline-admitted-731-parent-20261006-01'
BASE_SEAL = '79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641'
PRIOR = ROOT/'verification/out/gap108-offline-admitted-730-parent-20261006-01'
PRIOR_SEAL = '8da19c3fba8b438851231dfc79c8006caeea2364f578c29f9afa3c6fbf91d3f5'
ACC = mapping.pre_scope()
FMA = ACC+'.i_fpnew.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[0].active_format.i_fmt_slice.gen_num_lanes[0].active_lane.lane_instance.i_fma'
CLASS = FMA+'.i_class_inputs'
TARGETS = {FMA:[77]}
SOURCE_NAMES = ['hardware/include/qbs_pkg.sv','hardware/src/ara.sv','hardware/src/ara_sequencer.sv',
    'hardware/src/vlsu/vlsu.sv','hardware/deps/fpnew/src/fpnew_fma.sv',
    'hardware/deps/fpnew/src/fpnew_classifier.sv','hardware/deps/fpnew/src/fpnew_rounding.sv','hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/common_cells/src/lzc.sv',*['hardware/src/vlsu/qbs/'+n+'.sv' for n in
    ('qbs_engine','qbs_descriptor_decoder','qbs_profile_decoder','qbs_profile_engine_int',
     'qbs_compute_engine','qbs_fp_accumulator','qbs_commit','qbs_read_engine','qbs_block_adapter')]]


def contract():
    life,require = mapping.life,mapping.require
    manifest = life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    require(manifest['schema']=='PURE_WAR_HISTORICAL731_FULL_ARCHITECTURAL_ADMISSION_V1' and
            manifest['output']==str(BASE), 'Not authoritative731')
    pins = {str(BASE/'admission-manifest.json'):BASE_SEAL}
    for name in ('combined-bits.json','evidence-pins.json','status.json'):
        pins[str(BASE/name)] = manifest['output_pins'][str(BASE/name)]
    book = life.read_bound(BASE/'evidence-pins.json',pins[str(BASE/'evidence-pins.json')])
    require(manifest['baseline']==str(PRIOR) and manifest['baseline_seal']==PRIOR_SEAL,
            'Exact731 predecessor differs')
    previous = life.read_bound(PRIOR/'admission-manifest.json',PRIOR_SEAL)
    previous_book_seal = previous['output_pins'][str(PRIOR/'evidence-pins.json')]
    previous_book = life.read_bound(PRIOR/'evidence-pins.json',previous_book_seal)
    book = life.merge_pins(previous_book,book)
    pins = life.merge_pins(pins,{str(PRIOR/'admission-manifest.json'):PRIOR_SEAL,
                               str(PRIOR/'evidence-pins.json'):previous_book_seal})
    bits = life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    status = life.read_bound(BASE/'status.json',pins[str(BASE/'status.json')])
    require(status['coverage_admitted'] is True and status['aggregate_passed']==731 and
            len(bits['tests'])==len(set(bits['tests']))==731, 'Not admitted exact731')
    build = life.read_bound(mapping.qualifier.BUILD,mapping.qualifier.BUILD_SHA)
    pins = life.merge_pins(pins,{str(mapping.qualifier.BUILD):mapping.qualifier.BUILD_SHA})
    for relative in SOURCE_NAMES:
        path=ROOT/relative
        require(str(path) in build and (str(path) not in book or book[str(path)]==build[str(path)]),
                'Old source expected pin conflict')
        require(path.resolve()==path and not path.is_symlink(), 'Aliased historical source')
        pins = life.merge_pins(pins,{str(path):build[str(path)]})
    dispatcher=life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    require(build[str(ROOT/'hardware/src/ara_dispatcher.sv')]==mapping.qualifier.DISPATCHER_SHA,
            'Historical dispatcher build differs')
    pins = life.merge_pins(pins,{str(dispatcher):mapping.qualifier.DISPATCHER_SHA})
    db = mapping.DESIGN/'snps/coverage/db'
    for path in [db/'design/verilog.design.xml',db/'shape/cond.verilog.shape.xml',
                 db/'shape/cond.verilog.info.xml',db/'shape/tgl.verilog.shape.xml',
                 db/'shape/tgl.verilog.info.xml',db/'auxiliary/verilog.sourceinfo.xml',
                 Path(mapping.__file__).resolve(),Path(mapping.inventory.__file__).resolve(),
                 Path(mapping.inventory.score.__file__).resolve()]:
        require(str(path) in book, 'Missing expected compiled/parser pin')
        pins = life.merge_pins(pins,{str(path):book[str(path)]})
    life.check(pins)
    design=mapping.inventory.read_xml(db/'design/verilog.design.xml')
    nodes={n.get('id'):(n,d) for d in design.findall('srcdef') for n in d.findall('srcinst')}
    require(len(nodes)==sum(len(d.findall('srcinst')) for d in design.findall('srcdef')), 'Duplicate hierarchy')
    def path(key,seen=()):
        require(key not in seen, 'Hierarchy cycle')
        n,_=nodes[key];p=n.get('pid')
        return (path(p,seen+(key,))+'.' if p in nodes else '')+n.get('name')
    hierarchy={path(k):d for k,(_,d) in nodes.items()}
    shape=mapping.inventory.read_xml(db/'shape/cond.verilog.shape.xml')
    tgl_shape=mapping.inventory.read_xml(db/'shape/tgl.verilog.shape.xml')
    def info(metric):
        return {n.get('name'):n.get('chksum') for n in mapping.inventory.read_xml(
            db/('shape/'+metric+'.verilog.info.xml')).iter('instance_data')}
    ci,ti=info('cond'),info('tgl')
    files={n.get('id'):n.get('name') for n in mapping.inventory.read_xml(
        db/'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
    result=[]
    for scope,indices in TARGETS.items():
        row=bits['metrics']['cond'][scope]
        tgl=mapping.inventory.definition(tgl_shape,hierarchy[scope],ti[scope]) if scope==FMA else None
        definition,binding=mapping.native_definition(shape,hierarchy[scope],scope,row,ci.get(scope),tgl)
        points={p['raw_index']:p for p in mapping.inventory.points('cond',definition,row['width'])}
        for raw in indices:
            require(not mapping.bit(row,raw), 'Already covered in731: '+scope+' raw'+str(raw))
            point=points[raw];source=files[point['file_id']]
            require(source in pins, 'Unbound target source ownership')
            result.append(dict(scope=scope,metric='cond',width=row['width'],instance_checksum=row['checksum'],
                compiled_definition_checksum=definition.get('chksum'),binding=binding,point=point,
                source=source,before_hit=False,predicted_hit=True,measured_hit=None))
    for path in (ROOT/'apps/qbs_gap109_k2_sticky').iterdir():
        if path.is_file():pins[str(path)]=life.digest(path)
    pins[str(Path(__file__).resolve())]=life.digest(Path(__file__).resolve())
    pins[str(Path(__file__).with_name('test_gap109_static_contract.py'))]=life.digest(
        Path(__file__).with_name('test_gap109_static_contract.py'))
    life.check(pins)
    return dict(status='GAP109_STATIC_PREDICTION_NOT_SIMULATED',baseline=str(BASE),baseline_seal=BASE_SEAL,
        targets=result,pins=pins,shape=dict(m=1,n=1,k_blocks=2,weight='Q5_K',activation='Q8_K',
        layout='ROW_MAJOR',access='DIRECT',ap_mod16=0,software_vl=1,backend_vl=32,vd=8),
        words=[0x00b5045b,0x00b5045b],expected_bits=[0x43800000,0x43800000],
        expected_fflags=[0,1],expected_csr_fflags=[8,9],budget_s=600,
        custom_spike_pass=False,full_scalar_isa_verified=False,coverage_admitted=False,
        coverage_increment_measured=False,simulations_started=False,rtl_changed=False)


if __name__=='__main__':print(json.dumps(contract(),indent=2))
