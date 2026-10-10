"""Source-bound whole-object arithmetic candidates, never a module waiver."""
import argparse
import json
import re
import subprocess
from pathlib import Path
import review_srt_radix16_child_residual as r

# name: declaration line, full left bound, source type, defining source span
ALLOW = {
 'ct_vfdsu_pack': {
  'ex4_frac':(97,54,'3',153,153),
  'ex4_frac_52':(78,51,'0',371,379),
  'ex4_expnt_rst':(95,12,'3',156,167)},
 'ct_vfdsu_prepare': {
  'ex1_oper0_frac':(208,51,'3',419,422),
  'ex1_oper1_frac':(213,51,'3',423,426),
  'ex1_div_op0_expnt':(143,12,'3',429,432),
  'ex1_div_op1_expnt':(144,12,'3',436,439),
  'ex1_div_noid_nor_srt_op0':(138,52,'3',611,614),
  'ex1_div_noid_nor_srt_op1':(139,52,'3',615,618),
  'ex1_div_nor_srt_op0':(140,52,'3',619,620),
  'ex1_div_nor_srt_op1':(141,52,'3',622,623),
  'ex1_div_srt_op0':(148,52,'3',607,608),
  'ex1_div_srt_op1':(149,52,'3',609,610),
  'ex1_sqrt_srt_op0':(245,52,'3',629,630),
  'sqrt_remainder':(252,59,'3',625,627)}}
IDENTITY={'ct_vfdsu_pack':('370','3434235298','146603553'),
          'ct_vfdsu_prepare':('371','3815562254','980042783')}


def partition(module,nodes,requested=None):
    names=set(ALLOW[module]) if requested is None else set(requested)
    r.need(names == set(ALLOW[module]), 'Exact source-selected allowlist required, not hit-selected')
    r.need(len({n['name'] for n in nodes})==len(nodes),'Duplicate local native identity')
    r.need(names <= {n['name'] for n in nodes},'Missing whole target object')
    targets,protected=[],[]
    for n in nodes:
        if n['name'] not in names:
            reason=('PORT_INTERFACE' if n['portnode']!='0' else
                    'SCALAR_CONTROL_FLAGS_SPECIALCASE_CLOCK_RESET' if n['kind']=='node' else
                    'IEEE_PACKET_SPECIALCASE_ROUND_BOUNDARY_OR_NORMALIZER_INTERFACE')
            protected.append(dict(n,retention_reason=reason));continue
        line,left,typ,first,last=ALLOW[module][n['name']]
        r.need((n['kind'],n['file'],n['line_num'],n['left'],n['right'],n['type'],
                n['portnode'],n['excluded']) ==
               ('vectornode',IDENTITY[module][0],str(line),str(left),'0',typ,'0','0'),
               'Whole-object native/source identity differs')
        targets.append(dict(n,source_definition_lines=[first,last],
            rationale=('Numerical fraction alignment/exponent addition only; flags/result class/packet remain' if
                module=='ct_vfdsu_pack' else
                'Fraction/exponent numeric extraction or normalized significand/shifted remainder payload; mode, classification and normalizer children remain')))
    return targets,protected


def collect():
    pins={}
    def pin(path,expected=None):
        value=r.digest(path);r.need(expected is None or value==expected,'Pin drift: '+str(path))
        pins[str(path)]=value;return value
    ledger=r.BUILD/'build-source-pins.json'
    sourcepins=r.load(ledger,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b');pin(ledger)
    pin(r.BUILD/'sim/simv','2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3')
    evidence=r.load(r.REVIEW,r.REVIEW_SHA);pin(r.REVIEW,r.REVIEW_SHA)
    for item in evidence['compiled_pins']:pin(r.ROOT/item['path'],item['sha256'])
    sourceinfo=r.DB/'auxiliary/verilog.sourceinfo.xml';pin(sourceinfo)
    design=r.xml(r.DB/'design/verilog.design.xml')
    shape=r.xml(r.DB/'shape/tgl.verilog.shape.xml')
    info=r.xml(r.DB/'shape/tgl.verilog.info.xml')
    allinst={n.get('id'):n for n in design.iter('srcinst')}
    def scope(n):
        parent=allinst.get(n.get('pid'))
        return (scope(parent)+'.' if parent is not None else '')+n.get('name')
    scope_map={scope(n):n.attrib for n in allinst.values()}
    cache=r.load(r.CACHE,r.CACHE_SHA);pin(r.CACHE,r.CACHE_SHA)
    book=r.load(r.BASE/'admission-manifest.json',
        '6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5');pin(r.BASE/'admission-manifest.json')
    inputpath=r.BASE/'combined-inputs.txt';pin(inputpath,book['output_pins'][str(inputpath)])
    inputs=inputpath.read_text().splitlines()
    oldpath=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    pin(oldpath,cache['input_pins'][str(oldpath)])
    r.need(len(inputs)==763 and len(set(inputs))==763 and inputs[:742]==oldpath.read_text().splitlines()
           and cache['tests']==741,'741 exact prefix/762 baseline differs')
    # Reuse observed finite arithmetic evidence, without rerunning radix qualification.
    ev=[]
    for item in evidence['evidence']:
        for x in item['pins']:pin(r.ROOT/x['path'],x['sha256'])
        compare=r.load(r.ROOT/item['directory']/'vector-comparison.json')
        r.need(compare['status']=='PASS' and compare['first_mismatch'] is None and
               item['representative_exact_request'] in compare['instructions'], 'Arithmetic evidence missing')
        ev.append(item)
    halfpath=r.OUT/'fp16-c910-additional8-source-evidence742-agent-20261007-01.json'
    half=r.load(halfpath,'3eb5732cebd7dc3bed24c0bec2da09728b1f608cc192163c2284b4623e550cd2');pin(halfpath)
    for path,digest in half['pins'].items():pin(Path(path),digest)
    modules=[];unions={};widths={};checks={}
    for module in ALLOW:
        fileid,designsum,togglesum=IDENTITY[module]
        source=r.ROOT/('hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/'+module+'.v')
        pin(source,sourcepins[str(source)])
        upstream=subprocess.run(['git','-C',str(r.ROOT/'hardware/deps/fpnew'),'show',
            r.UPSTREAM+':vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/'+module+'.v'],
            cwd=r.ROOT,check=True,capture_output=True).stdout
        r.need(source.read_bytes()==upstream,'Not byte-identical upstream source')
        file=next(n for n in r.xml(sourceinfo).iter('fileinfo') if n.get('id')==fileid)
        r.need(file.get('name')==str(source),'Compiled file/source binding differs')
        defs=[n for n in design.iter('srcdef') if n.get('name')==module]
        tgldefs=[n for n in shape.iter('tgldef') if n.get('name')==module]
        r.need(len(defs)==len(tgldefs)==1 and defs[0].get('chksum')==designsum and
               tgldefs[0].get('chksum')==togglesum,'Compiled module checksum differs')
        scopes={scope(n):n.attrib for n in defs[0].findall('srcinst')}
        r.need(len(scopes)==17 and set(scopes)=={n.get('name') for n in info.iter('instance_data')
               if n.get('chksum')==togglesum},'Exact compiled instance universe differs')
        vector=[s for s in sorted(scopes) if '.i_ara.gen_lanes[' in s]
        scalar=set(scopes)-set(vector)
        r.need(len(vector)==16 and len(scalar)==1 and '.i_ariane.' in next(iter(scalar)),
               'Vector/scalar scope binding differs')
        lines=source.read_text().splitlines();nodes=[];offset=0
        for n in tgldefs[0].find('tglshape'):
            r.need(n.tag in ('node','vectornode') and n.get('file')==fileid,'Unknown shape kind/source')
            w=abs(int(n.get('left'))-int(n.get('right')))+1 if n.tag=='vectornode' else 1
            row=dict(kind=n.tag,**n.attrib,width=w,raw_offset=offset,
                declaration=lines[int(n.get('line_num'))-1])
            r.need(re.search(r'\b'+re.escape(n.get('name'))+r'\s*;',row['declaration']), 'Declaration binding differs')
            nodes.append(row);offset+=2*w
        targets,protect=partition(module,nodes)
        for t in targets:
            first,last=t['source_definition_lines']
            t['source_definition']='\n'.join(lines[first-1:last])
            r.need(t['name'] in t['source_definition'],'Numerical dataflow anchor differs')
        for s in scopes:
            c=cache['instances'][s]
            r.need(c['width']==offset and c['checksum']==togglesum,'Cached local shape differs')
            unions[s]=int(c['bits'],16);widths[s]=offset;checks[s]=togglesum
        children=[dict(scope=s,compiled_instance=n,protection='ALL_CHILD_OBJECTS_ALL_METRICS')
                  for s,n in scope_map.items() if any(s.startswith(parent+'.') for parent in vector)]
        modules.append(dict(module=module,source=str(source),source_sha256=pins[str(source)],
            upstream_commit=r.UPSTREAM,upstream_bytes_equal=True,file_id=fileid,
            design_checksum=designsum,toggle_checksum=togglesum,local_raw_width=offset,
            local_native_objects=len(nodes),targets=targets,protected_native_shape_objects=protect,
            compiled_scopes=scopes,vector_scopes=vector,protected_scalar_scopes=sorted(scalar),
            protected_descendants=children,scalar_protected_native_shape=nodes))
    for vdb in inputs[742:]:
        paths=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        r.need(len(paths)==1,'Ambiguous suffix');path=paths[0];pin(path,book['input_pins'][str(path)])
        found=set()
        for n in r.xml(path).iter('instance_data'):
            s=n.get('name')
            if s not in unions:continue
            value=n.get('value')
            r.need(s not in found and n.get('chksum')==checks[s] and len(value)==widths[s]
                   and set(value)<={'0','1'},'Native suffix exact scope/shape differs')
            found.add(s);unions[s]|=int(value,2)
        r.need(found==set(unions),'Missing compiled suffix scope')
    for m in modules:
        records=[]
        for s in sorted(m['compiled_scopes']):
            candidate=s in m['vector_scopes'];allfields=m['targets']+m['protected_native_shape_objects']
            fields=[dict(n,missing_directions=r.direction_missing(unions[s],widths[s],n),
                candidate=candidate and n['name'] in ALLOW[m['module']]) for n in allfields]
            records.append(dict(scope=s,fields=fields,raw_bits=hex(unions[s]),
                candidate_missing=sum(n['missing_directions']['total'] for n in fields if n['candidate']),
                retained_missing=sum(n['missing_directions']['total'] for n in fields if not n['candidate'])))
        m['instances']=records
        m['candidate_objects']=16*len(m['targets'])
        m['candidate_logical_bits']=16*sum(n['width'] for n in m['targets'])
        m['candidate_missing_directions']=sum(n['candidate_missing'] for n in records)
        m['retained_missing_directions']=sum(n['retained_missing'] for n in records)
    pin(Path(__file__).resolve());pin(Path(__file__).with_name('test_review_c910_prepare_pack_numeric.py'))
    for path,digest in pins.items():r.need(r.digest(path)==digest,'Evidence changed during review')
    return dict(status='STATIC_SOURCE_BOUND_CANDIDATES_NATIVE_QUALIFICATION_PENDING',baseline=762,
        modules=modules,evidence=ev,FP16_evidence=str(halfpath),FP16_scope_limit=half['scope_limit'],
        source_reliability='Exact unchanged upstream bytes plus observed finite DIV/SQRT architectural evidence; not module-name trust or full IEEE certification',
        missing_method='Sealed741 cached OR with exact ledger prefix + rehashed21 native suffix. Local two serialized pair slots; not DVE denominator or direction labels.',
        protects=['All ports','All scalar controls/reset/clock','Round/flags','NaN/Inf/zero/special/denorm packet logic',
                  'Scalar CVA6 instance','Every child object and other module'],
        conservative_omissions=['pack denorm fraction tables include tiny-result special cases; retain',
            'prepare NaN payload/exponent selection/normalizer output aliases retained',
            'Normal packed IEEE result words retained as format/interface boundary'],
        native_qualified=False,exclusions_applied=False,EDA_launched=False,RTL_modified=False,pins=pins)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();r.need(args.output.parent.resolve()==r.OUT and not args.output.exists(),'Fresh output required')
    result=collect()
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],seal=r.digest(args.output),modules=[
        {k:m[k] for k in ('module','candidate_objects','candidate_logical_bits','candidate_missing_directions',
                          'retained_missing_directions')} for m in result['modules']])))
