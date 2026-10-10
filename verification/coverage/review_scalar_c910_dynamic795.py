"""Small read-only typed residual inventory; partial EL and MDA stay HOLD."""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
import report_population795_pmp816 as report
import rank_cva6_scalar_data767 as typed
import targeted_toggle_evidence_v2 as native


def evidence():
    life=report.life;pins={}
    def read(p,h):
        value=life.read_bound(p,h);pins[str(p)]=h;return value
    manifest=read(report.BASE,report.BASE_SHA)
    p=report.BASE.parent/'combined-toggle-bits.json';rows=read(p,manifest['output_pins'][str(p)])
    h=read(report.HANDOFF,report.HANDOFF_SHA)
    elpath=report.HANDOFF.parent/'candidate-union.el';sha=h['output_pins'][str(elpath)]
    report.need(life.digest(elpath)==sha,'Exact sealed complete qualified EL');pins[str(elpath)]=sha
    other,masks=report.stable.semantic(elpath.read_text())
    ledger=report.BASE.parent/'combined-inputs.txt';report.need(life.digest(ledger)==manifest['output_pins'][str(ledger)],'Exact795 ledger')
    pins[str(ledger)]=manifest['output_pins'][str(ledger)]
    shape=Path(ledger.read_text().splitlines()[0])/'snps/coverage/db/shape/tgl.verilog.shape.xml'
    report.need(life.digest(shape)==manifest['input_pins'][str(shape)],'Frozen shape');pins[str(shape)]=manifest['input_pins'][str(shape)]
    defs={}
    for d in native.xml(shape).findall('tgldef'):defs.setdefault(d.get('chksum'),[]).append(d)
    groups=[]
    for scope,row in rows.items():
        if '.i_ariane.' not in scope or '.x_ct_vfdsu_' not in scope:continue
        if any(scope==s or scope.startswith(s+'.') for s,cs,machine,line in other if line=='WHOLE_SCOPE'):continue
        report.need(len(defs[row['checksum']])==1,'Unique typed definition')
        nodes,arrays=typed.typed_nodes(ET.tostring(defs[row['checksum']][0],encoding='unicode'),row)
        objects=[];partial=[]
        for n in nodes:
            if not n['missing_slots']:continue
            low=min(int(n.get('left',0)),int(n.get('right',0)));full=((1<<n['logical_width'])-1)<<low
            cover=[]
            for direction in ('0to1','1to0'):
                mask=0
                for (s,cs,name,kind,decl,prefix,dr),bits in masks.items():
                    if s==scope and name==n['name'] and not prefix and dr==direction:
                        report.need(cs.split()[-1]==row['checksum'],'Native checksum identity');mask|=bits
                cover.append(mask)
            if all(m&full==full for m in cover):continue
            obj=dict(name=n['name'],logical_width=n['logical_width'],decl_line=n.get('line_num'),
                missing_positions=n['missing_coordinates'],missing_count=n['missing_slots'])
            (partial if any(m&full for m in cover) else objects).append(obj)
        groups.append(dict(scope=scope,checksum=row['checksum'],serialized_width=row['width'],
            exact_unexcluded_missing=sum(o['missing_count'] for o in objects),
            objects=sorted(objects,key=lambda o:-o['missing_count']),partial_EL_HOLD=partial,MDA_HOLD=arrays))
    bookpath=report.life.ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    from build_scalar_div_subnormal794 import old,REL
    book=read(old.BUILD/'build-source-pins.json',old.SOURCE_SHA)
    for name in ('ct_vfdsu_prepare.v','ct_vfdsu_srt.v','ct_vfdsu_double.v','ct_vfdsu_round.v','ct_vfdsu_pack.v'):
        p=life.ROOT/REL/name;report.need(life.digest(p)==book[str(p)],'Frozen arithmetic source');pins[str(p)]=book[str(p)]
    pins[str(Path(__file__).resolve())]=life.digest(Path(__file__).resolve());life.check(pins)
    return dict(status='FORMAL795_TYPED_SCALAR_C910_RESIDUAL_NOT_REACHABILITY_PROOF',baseline=795,
        baseline_seal=report.BASE_SHA,EL_handoff_seal=report.HANDOFF_SHA,
        groups=sorted(groups,key=lambda g:-g['exact_unexcluded_missing']),input_pins=pins,
        direction_order_not_assumed=True,MDA_not_flattened=True,EDA_started=False,RTL_changed=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    d=evidence();report.life.save(a.output,d)
    print('RESIDUAL795',report.life.digest(a.output))
    for g in d['groups']:
        print(g['scope'].rsplit('.',1)[-1],g['checksum'],g['exact_unexcluded_missing'])
        print([(o['name'],o['missing_count']) for o in g['objects'][:12]])
