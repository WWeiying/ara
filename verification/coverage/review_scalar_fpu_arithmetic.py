"""Local source/parameter review only; no EL, exclusion or population verification."""
import gzip
from pathlib import Path
import xml.etree.ElementTree as ET
import run_scalar_fpu_finite as run
import review_fma_arithmetic_scope as existing

life, require = run.life, run.require
QUAL_SHA = 'df01c882f68fe9035a4563421c76d19cfe17cd7e07f7037967c6f101472f5569'
OUT = life.OUT/'scalar-fpu-arithmetic-review-agent-20261007-01.json'
FIRST = {'product','product_shifted','addend_after_shift','addend_shifted'}
EXTENSION = {'operand_a.mantissa','operand_b.mantissa','operand_c.mantissa',
             'mantissa_a','mantissa_b','mantissa_c','sum'}


def review():
    q=life.read_bound(run.QUAL/'qualification.json',QUAL_SHA)
    require(q['status']=='EXACT20_SCALAR_FP_RATIONAL_SPIKE_DUT_QUALIFIED' and
        (q['operations'],q['result_flags_checks'],q['guard_checks'])==(20,40,35),'Actual scalar qualification required')
    life.check(q['input_pins']);life.check(q['output_pins'])
    pins=life.merge_pins(q['input_pins'],q['output_pins'])
    pins=life.merge_pins(pins,{str(run.QUAL/'qualification.json'):QUAL_SHA,
        str(Path(__file__).resolve()):life.digest(Path(__file__).resolve()),
        str(Path(existing.__file__).resolve()):life.digest(Path(existing.__file__).resolve())})
    shape=life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db/shape/tgl.verilog.shape.xml'
    require(str(shape) in pins,'Unbound compiled shape')
    life.check({str(shape):pins[str(shape)]})
    root=ET.fromstring(gzip.decompress(shape.read_bytes()));instances=[]
    for record in q['instances']:
        defs=[d for d in root.findall('tgldef') if d.get('chksum')==record['checksum'] and
              d.get('name')==record['compiled_parameters']]
        require(len(defs)==1,'Ambiguous/mismatched parameter specialization')
        arithmetic=[n for n in defs[0].find('tglshape') if existing.group(n)]
        require(len(arithmetic)==51 and len({n.get('name') for n in arithmetic})==51,
                'Earlier vector arithmetic-family51 inventory differs')
        groups={'initial_four':[],'extension_seven_source_candidates':[],'protected_from_family51':[]}
        for node in arithmetic:
            name=node.get('name')
            group='initial_four' if name in FIRST else 'extension_seven_source_candidates' if name in EXTENSION else 'protected_from_family51'
            require(node.get('file')=='381' and node.get('portnode')=='0' and node.get('excluded')=='0',
                'Foreign/port/preexcluded arithmetic member')
            item=dict(node.attrib,kind=node.tag,native_name=existing.native_name(node),
                logical_bits=existing.width(node))
            if group=='protected_from_family51':
                item['reason']='Pipeline or sign/carry/exponent/alignment/normalization/sticky/rounding-related boundary retained'
            groups[group].append(item)
        require([len(v) for v in groups.values()]==[4,7,40],'4/7/40 partition differs')
        instances.append(dict(record,field_partition=groups,
            other_protected=[dict(n.attrib,kind=n.tag) for n in defs[0].find('tglshape') if n not in arithmetic],
            native_qualified=False))
    first=sum(n['logical_bits'] for i in instances for n in i['field_partition']['initial_four'])
    expanded=sum(n['logical_bits'] for i in instances for key in ('initial_four','extension_seven_source_candidates')
        for n in i['field_partition'][key])
    require((first,expanded)==(871,1566),'Whole-object numeric widths differ')
    result=dict(status='SCALAR_FP32_FP64_BOUNDED_FUNCTIONAL_AND_SOURCE_REVIEW_NOT_NATIVE_APPROVAL',
        basis='Unchanged reused arithmetic IP integration scope; not an unreachability proof.',
        qualification=str(run.QUAL/'qualification.json'),qualification_seal=QUAL_SHA,instances=instances,
        initial_objects=8,initial_logical_bits=first,expanded_objects=22,expanded_logical_bits=expanded,
        expanded_nominal_direction_slots=2*expanded,official_denominator=False,
        initial_evidence='Actual scalar20 operations, rational+Spike+full DUT prefix, per-operation flags and boxing/frm/restoration.',
        evidence_limit='Finite F/D ADD/MUL/FMA RNE/RUP only; not all values or all rounding modes; no FP16 extension.',
        protection='All ports, ancestors, descendants, pipeline, controls, reset, tags, masks, classifiers, special cases, sticky summaries, flags/status, rounding and modified modules retained.',
        native_exclusion_approved=False,EL_generated=False,aggregate_applied=False,pins=pins)
    life.check(pins);life.save(OUT,result)
    print('SOURCE_REVIEW '+life.digest(OUT)+' initial8/871bits expanded22/1566bits protected40perinstance',flush=True)


if __name__=='__main__':review()
