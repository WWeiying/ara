"""Read-only source/shape library eligibility; not native qualification or exclusion."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from inventory_operand_debug import Design,ROOT
import review_fma_arithmetic_scope as typed
import lzc_padding_proof as padding

OUT=ROOT/'verification/out'
BUILD=OUT/'repaired-aligned-build-20260930-01'
SOURCE=ROOT/'hardware/deps/common_cells/src/lzc.sv'
CACHE=OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
CALIBRATION=OUT/'lzc_selector_native_measurement-705-20261006-02/native-summary.json'
FORMAL=OUT/'qbs-payload-residual4-offline-admitted-767-agent-20261007-01/admission-manifest.json'
FORMAL_SHA='a4dac6fb073fc665cb8f274557d04c8d2bf3ad9291a70bda03bcfdce3542b405'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review():
    require=typed.require
    book=json.loads((BUILD/'build-source-pins.json').read_bytes())
    require(book[str(SOURCE)]==sha(SOURCE)==padding.SOURCE_SHA256,'Frozen LZC source differs')
    upstream=subprocess.run(['git','-C',str(SOURCE.parent.parent),'show','HEAD:src/lzc.sv'],
        check=True,capture_output=True).stdout
    require(hashlib.sha256(upstream).hexdigest()==padding.SOURCE_SHA256,'Local upstream baseline source differs')
    commit=subprocess.run(['git','-C',str(SOURCE.parent.parent),'rev-parse','HEAD'],
        check=True,capture_output=True,text=True).stdout.strip()
    require(sha(FORMAL)==FORMAL_SHA,'Formal767 manifest differs')
    cache=json.loads(CACHE.read_bytes())
    calibration=json.loads(CALIBRATION.read_bytes())
    calibrated=sorted({r['width'] for r in calibration['rows']})
    require(calibrated==[10,23] and calibration['independent_calibration_cases']==8,
        'Historical independent calibration changed')
    design=Design(BUILD/'sim/simv.vdb')
    scopes=sorted(s for s in design.hierarchy if s.endswith('.i_lzc') and '.i_fma.' in s)
    require(len(scopes)==32,'FMA LZC child count differs')
    candidates=[];groups={};ports=[]
    for scope in scopes:
        source=design.source(scope);definition=design.definition(scope,'tgl')
        require(source['resolved_path']==str(SOURCE) and source['definition_checksum']=='3250293308',
            'Exact compiled source owner differs')
        name=definition.get('name');params=name.split('parameter ',1)[1].rsplit(')',1)[0]
        values={k.strip():int(v) for k,v in (p.strip().split('=') for p in params.split(','))}
        require(values['WIDTH'] in (25,51,109) and values['MODE']==1 and
            values['CNT_WIDTH']==(values['WIDTH']-1).bit_length(),'Compiled WIDTH/MODE differs')
        internal=[];protected=[]
        for n in definition.find('tglshape'):
            row=dict(name=n.get('name'),shape_kind=n.tag,attributes=dict(n.attrib),
                dimensions=typed.dimensions(n),logical_bits=typed.width(n),typed_native_label_candidate=typed.native_name(n))
            (internal if n.get('portnode')=='0' else protected).append(row)
        require({p['name'] for p in internal}=={'gen_lzc.index_lut','gen_lzc.sel_nodes',
            'gen_lzc.index_nodes','gen_lzc.in_tmp'} and
            {p['name'] for p in protected}=={'in_i','cnt_o','empty_o'},'Exact whole internal/port boundary differs')
        row=cache['instances'][scope]
        require(row['checksum']==definition.get('chksum'),'Historical binary checksum differs')
        binary_width=2*sum(typed.width(n) for n in definition.find('tglshape') if n.tag in ('node','vectornode'))
        require(binary_width==row['width'],'Binary-only serialization width differs')
        g=groups.setdefault(str(values['WIDTH']),dict(instances=0,internal_bits=0,port_bits=0,
            historical741_all_binary_directions=0,historical741_all_binary_missing=0))
        g['instances']+=1;g['internal_bits']+=sum(p['logical_bits'] for p in internal)
        g['port_bits']+=sum(p['logical_bits'] for p in protected)
        g['historical741_all_binary_directions']+=row['width']
        g['historical741_all_binary_missing']+=row['width']-bin(int(row['bits'],16)).count('1')
        candidates.append(dict(scope=scope,parameters=values,module_checksum=source['definition_checksum'],
            toggle_checksum=definition.get('chksum'),compiled_definition=name,internal_candidates=internal,
            protected_full_complement=protected))
    pins={str(p):sha(p) for p in (SOURCE,BUILD/'build-source-pins.json',CACHE,CALIBRATION,FORMAL,
        Path(__file__).resolve(),Path(typed.__file__).resolve(),
        BUILD/'sim/simv.vdb/snps/coverage/db/design/verilog.design.xml',
        BUILD/'sim/simv.vdb/snps/coverage/db/shape/tgl.verilog.shape.xml',
        BUILD/'sim/simv.vdb/snps/coverage/db/auxiliary/verilog.sourceinfo.xml')}
    return dict(status='FMA_LZC_TYPED_INTERNAL_LIBRARY_CANDIDATE_HOLD_MATCHED_WIDTH_VALIDATION',
        formal_context_population=767,formal_manifest_seal=FORMAL_SHA,source_sha256=padding.SOURCE_SHA256,
        upstream_local_commit=commit,source_equals_local_upstream_and_frozen_build=True,
        child_instances=32,internal_objects=128,protected_port_objects=96,groups=groups,instances=candidates,
        existing_FMA612_policy='All descendants retained; no existing LZC internal Toggle qualification inherited.',
        independent_actual_VCS_calibrated_widths=calibrated,matched_width_actual_unit_evidence=False,
        formal_functional_property_evidence=False,
        zero_contract='Existing calibration checks empty for zero and count only for nonzero; no new zero-count promise.',
        missing_evidence='No matching WIDTH25/51/109 standalone VCS/unit/formal result located in examined local evidence. Typed labels are compiled candidates, not DVE-observed identities.',
        capacity_limits='Historical741 binary missing is all fields including protected ports, not native official denominator. Packed array missing unbound; no claimed current767 exact missing or contribution.',
        EDA_launched=False,native_qualified=False,exclusions_applied=False,official_denominator=None,
        selection_policy='All four complete internal fields regardless hit; all input/output/empty ports retained. No classify/round/controller or parent scope exclusion.',pins=pins)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    typed.require(a.output.resolve().parent==OUT and not a.output.exists(),'Fresh independent audit file only')
    result=review()
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(status=result['status'],seal=sha(a.output),groups=result['groups'])))
