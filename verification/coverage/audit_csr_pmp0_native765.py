"""Independent terminal audit of the frozen PMP capture, without EDA or overwrites."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import qualify_csr_pmp0_native765 as old

life,require=old.life,old.require
ORIGIN=life.OUT/'csr-pmp0-internal770-native765-agent-20261007-01'
CONFIG_SHA='0dfff6f1406393445d5fff71b6e041ebfe600b429856e609e1b827de15889ef6'
CAPTURE_SHA='b3e8898b50035449d861c4f41e283485df5f5e2bd6bf95cc481d3f1559191954'
ANNOTATION='PMP0 internal q/next constant after valid reset and settled evaluation; no initial-X waiver'


def rows(path,c):
    with path.open(newline='') as stream:table=list(csv.reader(stream,delimiter='\t'))
    require(table[0]==['handle','path','meta','name'] and len(table)==2078 and
            all(len(r)==4 and all(r) for r in table[1:]),'Exactly2077 legal native rows required')
    native=table[1:];used=set();bound=[];aliases=[]
    require(len({r[0] for r in native})==len({r[1] for r in native})==2077,'Unique native handle/path population')
    byname={r[3]:r for r in native}
    require(len(byname)==2077,'No duplicate native labels')
    for n in c['instances'][0]['targets']+c['instances'][0]['protected']:
        matches=[byname[a] for a in old.aliases(n) if a in byname]
        require(len(matches)==1,'Exact compiled/native identity '+n['name'])
        r=matches[0];require(r[0] not in used,'No native identity alias collapse');used.add(r[0])
        require(r[1]==r[2]==r[3],'Actual bare native path/meta/name schema differs')
        canonical=n['name']+old.bounds(n)
        if r[3]!=canonical:
            # This capture has precisely one previously source-approved protected alias.
            require(n['name']=='pmpaddr_o' and n['packedrange'].split()==['0','0','53','0'] and
                    r[3]=='pmpaddr_o[0][53:0]' and n in c['instances'][0]['protected'],
                    'Unreviewed native singleton rendering')
            aliases.append(dict(compiled=canonical,native=r[3],protected=True))
        bound.append((n['name'],r[1],r[2],r[3]))
    require(used=={r[0] for r in native} and len(bound)==2077,'Extra native object/container is not silently ignored')
    require(len(aliases)==1,'Exact actual protected singleton normalization')
    return sorted(bound),aliases


def records(text,c):
    old.parse_el(text,c)
    check=scope=annotation=None;records=[]
    targets={n['name']:n for n in c['instances'][0]['targets']}
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('//'):continue
        if line.startswith('CHECKSUM:'):
            check=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line).groups();scope=annotation=None
        elif line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip();annotation=None
        elif line.startswith('ANNOTATION:'):
            annotation=re.fullmatch(r'ANNOTATION: "([^"\r\n]*)"',line).group(1)
            require(annotation==ANNOTATION,'Exact reset/settled source annotation required')
        else:
            require(annotation==ANNOTATION,'Missing annotation owner')
            direction,name,_=re.fullmatch(r'Toggle (?:(0to1|1to0) )?([^\s"]+) "logic ([^"\r\n]+)"',line).groups()
            records.append((scope,*check,'Toggle',name,old.bounds(targets[name]),direction or 'whole',annotation))
    require(len(records)==len(set(records))==1282,'Exact actual whole-array/vector plus paired-scalar records')
    return Counter(records)


def audit():
    c=life.read_bound(ORIGIN/'config.json',CONFIG_SHA);old.contract(c);life.check(c['pins'])
    capture=life.read_bound(ORIGIN/'capture-result.json',CAPTURE_SHA);life.check(capture['pins'])
    t=json.loads((ORIGIN/'terminal.json').read_bytes())
    require(t['returncode']==0 and not t['timeout'] and len(t['actual_dve'])==1,'Actual terminal required')
    require(t['actual_dve'][0]['exe']==c['identity']['executable'] and
            t['actual_dve'][0]['cwd']==str(ORIGIN),'Terminal actual image/output binding')
    evidence=[];reference=None
    for stage in old.STAGES:
        binding,normalization=rows(ORIGIN/('native_%s_0.tsv'%stage),c)
        if reference is None:reference=binding
        require(binding==reference,'All five complete native inventories identical')
        evidence.append(dict(stage=stage,native_rows=2077,used_rows=2077,extra_rows=0,
            targets=770,protected=1307,protected_alias_normalization=normalization))
    first=records((ORIGIN/'first.el').read_text(),c);second=records((ORIGIN/'second.el').read_text(),c)
    require(first==second,'Full identity/type/direction/annotation multiset reload differs')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):old.check_file(ORIGIN,c,name)
    script=old.HERE/'queue_fp_temporaries_native.tcl';body=script.read_text()
    require(body.count('qfp_need [expr {[gui_cov_excl_review -isEmpty] == 1}]')==2 and
            'fma_save initial-empty.el; fma_check initial-empty.el' in body and
            'fma_save reset-empty.el; fma_check reset-empty.el' in body and
            'fma_save final-empty.el; fma_check final-empty.el' in body,'Frozen protection/empty guards differ')
    gui=(ORIGIN/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('PMP0_NATIVE_DONE')==1 and 'FAILED' not in gui and
            'All exclusions successfully imported and applied.' in gui and not (ORIGIN/'error.txt').exists(),
            'Guarded five-stage successful execution required')
    pins=life.merge_pins(capture['pins'],{str(p):life.digest(p) for p in ORIGIN.rglob('*') if p.is_file()})
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_audit_csr_pmp0_native765.py')):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    return dict(status='PMP0_INTERNAL770_STRICT_OFFLINE_NATIVE_AUDIT_QUALIFIED_NOT_APPLIED',
        origin=str(ORIGIN),origin_capture_seal=CAPTURE_SHA,config_seal=CONFIG_SHA,scope=old.source.SCOPE,
        checksums=dict(module='1371260681',toggle='1176918775'),five_stages=evidence,
        objects=770,logical_bits=7936,protected_objects=1307,protected_output_aliases=7,
        EL_records=1282,annotation=ANNOTATION,full_annotation_identity_multiset_equal=True,
        all_extra_rows_classified=True,extra_rows=0,d_and_other_CSR_ports_protected=True,
        initial_reset_final_empty=True,native_review_empty_assertions_executed=2,
        per_row_included_flags_captured=False,
        future_union_required='full766.audit_observers must read actual EXCLUDED status for all2077 '
                              'objects in all five stages, including all1307 protected objects and seven output aliases.',
        protection_evidence='Exact global EL contains only approved770 whole internal objects, no d/port/other metric; '
                            'empty EL initially/reset/final, complete2077 identities unchanged; no claim of per-row flag samples.',
        valid_reset_settled_only=True,initial_X_waiver=False,population_application=False,
        DVE_restarted=False,official_percentage=None,pins=pins)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=audit();life.save(a.output.resolve(),value)
    print(json.dumps(dict(status=value['status'],seal=life.digest(a.output.resolve()),pins=len(value['pins']))))
