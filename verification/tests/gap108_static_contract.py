"""Exact729 zeros and old-source identity for GAP108; predictions, not coverage."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'verification/coverage'))
import prepare_gap107_raw_gain_v2 as mapping

BASE = ROOT/'verification/out/gap107-offline-admitted-729-parent-20261006-01'
BASE_SEAL = 'e5bd9eeb19acc452d25db12f342c3c12532614a0c773c43355a33e34d8dd1912'
ACC = mapping.pre_scope()
FMA = ACC+'.i_fpnew.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[0].active_format.i_fmt_slice.gen_num_lanes[0].active_lane.lane_instance.i_fma'
CLASS = FMA+'.i_class_inputs'
TARGETS = {FMA:[37],CLASS:[13,18,62,67,111,116]}
SOURCE_NAMES = ['hardware/include/qbs_pkg.sv','hardware/src/ara.sv','hardware/src/ara_sequencer.sv',
    'hardware/src/vlsu/vlsu.sv','hardware/deps/fpnew/src/fpnew_fma.sv',
    'hardware/deps/fpnew/src/fpnew_classifier.sv','hardware/deps/fpnew/src/fpnew_rounding.sv',*['hardware/src/vlsu/qbs/'+n+'.sv' for n in
    ('qbs_engine','qbs_descriptor_decoder','qbs_profile_decoder','qbs_profile_engine_int',
     'qbs_compute_engine','qbs_fp_accumulator','qbs_commit','qbs_read_engine','qbs_block_adapter')]]


def contract():
    life,require = mapping.life,mapping.require
    manifest = life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    require(manifest['schema']=='GAP107_HISTORICAL729_SOFTWARE_NATIVE_ADMISSION_V1' and
            manifest['output']==str(BASE), 'Not authoritative729')
    pins = {str(BASE/'admission-manifest.json'):BASE_SEAL}
    for name in ('combined-bits.json','evidence-pins.json','status.json'):
        pins[str(BASE/name)] = manifest['output_pins'][str(BASE/name)]
    book = life.read_bound(BASE/'evidence-pins.json',pins[str(BASE/'evidence-pins.json')])
    bits = life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    status = life.read_bound(BASE/'status.json',pins[str(BASE/'status.json')])
    require(status['coverage_admitted'] is True and status['aggregate_passed']==729 and
            len(bits['tests'])==len(set(bits['tests']))==729, 'Not admitted exact729')
    build = life.read_bound(mapping.qualifier.BUILD,mapping.qualifier.BUILD_SHA)
    pins = life.merge_pins(pins,{str(mapping.qualifier.BUILD):mapping.qualifier.BUILD_SHA})
    for relative in SOURCE_NAMES:
        path=ROOT/relative
        require((relative=='hardware/deps/fpnew/src/fpnew_rounding.sv' or
                 book[str(path)]==build[str(path)]), 'Old source expected pin conflict')
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
            require(not mapping.bit(row,raw), 'Already covered in729: '+scope+' raw'+str(raw))
            point=points[raw];source=files[point['file_id']]
            require(source in pins, 'Unbound target source ownership')
            result.append(dict(scope=scope,metric='cond',width=row['width'],instance_checksum=row['checksum'],
                compiled_definition_checksum=definition.get('chksum'),binding=binding,point=point,
                source=source,before_hit=False,predicted_hit=True,measured_hit=None))
    for path in (ROOT/'apps/qbs_gap108_subnormal').iterdir():
        if path.is_file():pins[str(path)]=life.digest(path)
    pins[str(Path(__file__).resolve())]=life.digest(Path(__file__).resolve())
    pins[str(Path(__file__).with_name('test_gap108_static_contract.py'))]=life.digest(
        Path(__file__).with_name('test_gap108_static_contract.py'))
    life.check(pins)
    return dict(status='GAP108_STATIC_PREDICTION_NOT_SIMULATED',baseline=str(BASE),baseline_seal=BASE_SEAL,
        targets=result,pins=pins,shape=dict(m=1,n=1,k_blocks=1,weight='Q5_K',activation='Q8_K',
        layout='ROW_MAJOR',access='DIRECT',ap_mod16=0,software_vl=1,backend_vl=32,vd=8),
        words=[0x00b5045b,0x00b5045b],expected_bits=[0x100,0x200],
        expected_fflags=[0,3],expected_csr_fflags=[8,11],budget_s=600,
        custom_spike_pass=False,full_scalar_isa_verified=False,coverage_admitted=False,
        coverage_increment_measured=False,simulations_started=False,rtl_changed=False)


if __name__=='__main__':print(json.dumps(contract(),indent=2))
