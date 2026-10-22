"""Exact arithmetic boundary/complement successor; no native execution."""
import argparse
import json
import re
from pathlib import Path
import review_c910_prepare_pack_numeric as first

r=first.r
REVIEW=r.OUT/'c910-prepare-pack-numeric-source-review762-agent-20261007-01.json'
SEAL='359d99c679a1f2fb0abd81793839d026114814e4775dd7dbe06c50f33c039c28'


def role(module,node):
    name=node['name']
    if node['portnode']!='0': return 'INTERFACE_ALL_BITS_RETAIN'
    if node['kind']=='node': return 'SCALAR_MODE_CLASSIFICATION_FLAGS_CLOCK_RESET_RETAIN'
    if module=='ct_vfdsu_pack':
        if name=='expnt_add_op1': return 'NORMALIZATION_CORRECTION_SELECTOR_RETAIN'
        if name.endswith('denorm_frac'):return 'DENORMAL_TINY_SPECIALCASE_TABLE_RETAIN'
        return 'IEEE_RESULT_PACKET_NAN_INF_ZERO_DENORMAL_OR_FORMAT_BOUNDARY_RETAIN'
    if name=='ex1_rm':return 'ROUNDING_MODE_RETAIN'
    if name in ('ex1_qnan_f','ex1_op0_f','ex1_op1_f'):return 'CANONICAL_OR_PROPAGATED_NAN_PAYLOAD_RETAIN'
    if name in ('ex1_oper0','ex1_oper1'):return 'IEEE_ENCODED_OPERAND_CLASSIFICATION_INPUT_RETAIN'
    if name.startswith(('ex1_oper0_id_','ex1_oper1_id_')):return 'NORMALIZER_CHILD_OUTPUT_BOUNDARY_RETAIN'
    return 'EXPONENT_MODE_OR_NORMALIZATION_SELECTION_BOUNDARY_RETAIN'


def exact_targets(review):
    targets=[];complement=[];scalar=[]
    for module in review['modules']:
        name=module['module']
        first.partition(name,module['targets']+module['protected_native_shape_objects'])
        scopes=module['vector_scopes']
        r.need(len(scopes)==len(set(scopes))==16,'Exact16 distinct vector scopes required')
        for scope in scopes:
            r.need(re.search(r'\.gen_lanes\[[0-3]\].*\.gen_num_lanes\[[0-3]\]',scope) and
                   scope.endswith('.x_'+name),'Exact vector lane/subslot/module required')
            for n in module['targets']:
                targets.append(dict(scope=scope,module=name,name=r.native_name(n),
                    toggle_checksum=module['toggle_checksum'],native_shape=n))
            for n in module['protected_native_shape_objects']:
                complement.append(dict(scope=scope,module=name,name=r.native_name(n),
                    toggle_checksum=module['toggle_checksum'],native_shape=n,reason=role(name,n)))
        r.need(len(module['protected_scalar_scopes'])==1,'Exact scalar instance must remain')
        for scope in module['protected_scalar_scopes']:
            r.need('.i_ariane.' in scope and scope not in scopes,'Scalar transfer forbidden')
            for n in module['scalar_protected_native_shape']:
                scalar.append(dict(scope=scope,module=name,name=r.native_name(n),native_shape=n,
                                   reason='SCALAR_CVA6_NO_EVIDENCE_TRANSFER'))
    identity=lambda n:(n['scope'],n['name'])
    r.need(len(targets)==240 and len(complement)==3280 and len(scalar)==220,
           'Exact240/3280/220 target/protection partition differs')
    r.need(len(set(map(identity,targets)))==240 and
           not(set(map(identity,targets)) & set(map(identity,complement+scalar))),
           'Duplicate/overlapping target and complement')
    return targets,complement,scalar


def collect():
    review=r.load(REVIEW,SEAL)
    pins=dict(review['pins']);pins[str(REVIEW)]=SEAL
    for path,digest in pins.items():r.need(r.digest(path)==digest,'Reviewed source pin drift: '+path)
    targets,complement,scalar=exact_targets(review)
    design=r.xml(r.DB/'design/verilog.design.xml')
    shapes=r.xml(r.DB/'shape/tgl.verilog.shape.xml')
    infos=r.xml(r.DB/'auxiliary/verilog.sourceinfo.xml')
    info=r.xml(r.DB/'shape/tgl.verilog.info.xml')
    srcpins=r.load(r.BUILD/'build-source-pins.json')
    files={n.get('id'):Path(n.get('name')) for n in infos.iter('fileinfo')}
    instances={n.get('id'):n for n in design.iter('srcinst')}
    owners={n.get('id'):d for d in design.iter('srcdef') for n in d.findall('srcinst')}
    def scope(n):
        parent=instances.get(n.get('pid'))
        return (scope(parent)+'.' if parent is not None else '')+n.get('name')
    compiled={scope(n):n for n in instances.values()}
    bymodule={d.get('name'):d for d in shapes.iter('tgldef')}
    native={n.get('name'):n.attrib for n in info.iter('instance_data')}
    # Bind sibling pack/prepare to the already observed physical lane/subslot paths.
    half=r.load(Path(review['FP16_evidence']))
    additional={n['scope'].split('.x_ct_vfdsu_srt.')[0] for n in half['instances']}
    capture=r.load(r.OUT/'c910-srt-native1264-recovery-agent-20261007-01/config.json')
    prior={n['scope'].split('.x_ct_vfdsu_srt.')[0] for n in capture['instances']}
    mapping=[]
    for m in review['modules']:
        for s in m['vector_scopes']:
            parent=s.rsplit('.',1)[0]
            r.need(parent in prior|additional,'Unproven peer integration coordinate')
            lane=int(re.search(r'gen_lanes\[(\d)\]',s).group(1))
            slot=int(re.search(r'gen_num_lanes\[(\d)\]',s).group(1))
            mapping.append(dict(scope=s,parent=parent,physical_lane=lane,subslot=slot,
                evidence=('FP16_FINITE_RTZ_DIV_ONLY_NOT_FP16_SQRT_OR_FLAGS' if parent in additional
                          else 'FP32_FP64_FINITE_DIV_SQRT_EXACT_WRITES'),
                no_scalar_transfer=True))
    pins[str(r.OUT/'c910-srt-native1264-recovery-agent-20261007-01/config.json')]=r.digest(
        r.OUT/'c910-srt-native1264-recovery-agent-20261007-01/config.json')
    children=[]
    parents={n['scope'] for n in targets}
    childscopes={s for s in compiled if any(s.startswith(p+'.') for p in parents)}
    r.need(len(childscopes)==48,'Exact48 descendant scopes changed')
    for s in sorted(childscopes):
        owner=owners[compiled[s].get('id')]
        definition=bymodule[owner.get('name')]
        r.need(s in native and native[s]['chksum']==definition.get('chksum'),
               'Child native info/definition binding differs')
        objects=[]
        for n in definition.find('tglshape'):
            source=files[n.get('file')]
            r.need(str(source) in srcpins and r.digest(source)==srcpins[str(source)],'Child source drift')
            pins[str(source)]=srcpins[str(source)]
            declaration=source.read_text().splitlines()[int(n.get('line_num'))-1]
            r.need(re.search(r'\b'+re.escape(n.get('name'))+r'\s*(?:;|=)',declaration),
                   'Child declaration identity differs')
            node=dict(kind=n.tag,**n.attrib)
            objects.append(dict(native_shape=node,name=r.native_name(node),
                source=str(source),declaration=declaration,protected=True))
        children.append(dict(scope=s,module=owner.get('name'),design_checksum=owner.get('chksum'),
            toggle_checksum=definition.get('chksum'),objects=objects,all_metrics_protected=True))
    for file in (Path(__file__).resolve(),Path(__file__).with_name('test_review_c910_prepare_pack_boundaries.py')):
        pins[str(file)]=r.digest(file)
    for path,digest in pins.items():r.need(r.digest(path)==digest,'Evidence changed during boundary review')
    summary=[{k:m[k] for k in ('module','candidate_objects','candidate_logical_bits',
        'candidate_missing_directions','retained_missing_directions')} for m in review['modules']]
    return dict(status='EXACT_SOURCE_BOUND_240_TARGETS_COMPLEMENT_PREPARED_NATIVE_PENDING',
        review_sha256=SEAL,baseline=762,summary=summary,targets=targets,
        protected_local_complement=complement,protected_scalar_objects=scalar,
        protected_children=children,integration_binding=mapping,pins=pins,
        numerical_boundary_facts=[
            'prepare extracted fraction bits feed ff1 arithmetic inputs, not NaN payload construction; ff1 scopes remain protected',
            'prepare exponent extracts are numeric values; NaN/max/zero classifiers use separate encoded-operand paths and remain protected',
            'prepare normalized mantissa mux data remain numeric; ex1_op0_id_nor/ex1_op1_id_nor selection controls are retained',
            'sqrt_remainder only shifts/pads the mantissa under retained exponent-parity selector',
            'pack frac alias and normal fraction alignment contain no NaN/Inf/zero packet generation; their downstream special handlers remain protected',
            'pack exponent result is an addition payload; expnt_add_op1 normalization selector and all flags remain protected'],
        conservative_pack_conclusion='Only16 actual missing candidate positions. Do not expand into54k retained local special/packet positions for gain.',
        native_requirements=dict(stages=['initial','apply','reset','reload','final'],
            targets=240,logical_target_bits=10896,local_non_targets=3280,scalar_non_targets=220,
            child_scopes=48,all_other_scopes_protected=True,
            before='Exact native whole-object name/type/checksum/source/bounds bijection; no guessed regex names',
            apply='Only240 explicit fields, whole bounds, both directions; no pre-existing exclusions',
            reset='All target and non-target native states equal initial',
            reload='Typed EL must equal exact240 targets; preserve source bindings and reject partial/single-direction/extra objects',
            final='Native reset return equals initial; all other scope states stable in every stage'),
        disabled_configuration_waiver=False,whole_module_waiver=False,
        hit_selected_fields=False,native_qualified=False,EDA_launched=False,exclusions_applied=False,
        scope_limit='Reliable unchanged arithmetic candidate review only. Not IEEE certification, exception correctness or native qualification.')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();r.need(args.output.parent.resolve()==r.OUT and not args.output.exists(),'Fresh independent output required')
    result=collect()
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],seal=r.digest(args.output),targets=len(result['targets']),
        complement=len(result['protected_local_complement']),children=len(result['protected_children']))))
