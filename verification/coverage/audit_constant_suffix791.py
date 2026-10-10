"""Readonly789..791 supplement to the frozen785 constant-family suffix audit."""
import argparse
import json
from pathlib import Path

import audit_constant_suffix788 as old

life, need = old.life, old.need
BASE = life.OUT/'akv-canonical-kfault-offline-admitted791-agent-20261008-01'
BASE_SHA = '8b732015035c1f716940598f05d8a8063e4b4829eb5cd67cfebcbb2728ee2b30'


def append_gate(previous,current,population):
    need(type(population) is int and 789<=population<=791 and
         len(current)==len(set(current))==population+1 and
         len(previous)==len(set(previous))==population and current[:-1]==previous,
         'Exact consecutive admitted suffix, no duplicate/reorder/lost member')


def evidence():
    inherited=old.evidence()
    need(inherited['formal_population']==788 and
         inherited['status']=='FORMAL788_INHERITED_THREE_CONSTANT_FAMILIES_SUFFIX_ZERO_VERIFIED_NOT_REPORT',
         'Complete frozen788 source/native zero audit')
    pins=dict(inherited['input_pins'])
    def read(path,sha,structured=True):
        need(str(path) not in pins or pins[str(path)]==sha,'Conflicting sealed ownership')
        value=life.read_bound(path,sha) if structured else path.read_bytes()
        if not structured:need(life.digest(path)==sha,'Bound text drift')
        pins[str(path)]=sha
        return value
    families=[]
    p=old.prior
    sources=((p.native,p.LOCAL,p.LOCAL_SHA,'RR190','missing_coordinates'),
        (p.previous.native,p.previous.LOCAL,p.previous.LOCAL_CONFIG_SHA,'CLASS_PADDING','raw_coordinates'),
        (p.previous.previous.native,p.previous.previous.LOCAL,p.previous.previous.LOCAL_CONFIG_SHA,'FPNEW90','coordinates'))
    for module,directory,seal,name,coordinate in sources:
        config=read(directory/'config.json',seal)
        proof=read(module.SOURCE,module.SOURCE_SHA)
        families.append((name,p.target_groups(proof,config,coordinate)))
    scopes={s for _,groups in families for s in groups}
    records=[];directory,seal=BASE,BASE_SHA
    for population in (791,790,789):
        manifest_path=directory/'admission-manifest.json'
        manifest=read(manifest_path,seal)
        status=read(directory/'status.json',manifest['output_pins'][str(directory/'status.json')])
        need(manifest['coverage_admitted'] is True and manifest['output']==str(directory) and
             status['coverage_admitted'] is True and type(status['aggregate_passed']) is int and
             status['aggregate_passed']==population,'Exact formal suffix authority')
        ledger_path=directory/'combined-inputs.txt'
        ledger=read(ledger_path,manifest['output_pins'][str(ledger_path)],False).decode().splitlines()
        need(len(ledger)==len(set(ledger))==population+1,'Exact formal ledger size')
        paths=list((Path(ledger[-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(paths)==1,'One native suffix Toggle test')
        path=paths[0];sha=manifest['input_pins'][str(path)]
        read(path,sha,False)
        rows,measured=p.native.source.rank.t.rows(path,scopes)
        need(measured==sha,'Exact native Toggle bytes')
        records.append(dict(population=population,manifest=str(manifest_path),manifest_sha256=seal,
            ledger=ledger,new_vdb=ledger[-1],toggle_data=str(path),toggle_sha256=sha,
            families=old.audit_rows(rows,families)))
        directory,seal=Path(manifest['baseline']),manifest['baseline_seal']
    need(directory==old.BASE and seal==old.BASE_SHA,'Exact approved788 ancestor')
    inherited_manifest=read(directory/'admission-manifest.json',seal)
    previous=read(directory/'combined-inputs.txt',inherited_manifest['output_pins'][str(directory/'combined-inputs.txt')],False).decode().splitlines()
    records.reverse()
    for record in records:
        append_gate(previous,record['ledger'],record['population']);previous=record.pop('ledger')
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_audit_constant_suffix791.py'),Path(old.__file__).resolve()):
        read(path,life.digest(path),False)
    # Recheck only these bounded evidence files; never scan all historical admission pins.
    life.check(pins)
    return dict(status='FORMAL791_INHERITED785_CONSTANT_SUFFIX_ZERO_SUPPLEMENT_NOT_REPORT',
        formal_population=791,formal_manifest=str(BASE/'admission-manifest.json'),formal_seal=BASE_SHA,
        qualified_predecessor=inherited['qualified_predecessor'],
        inherited_suffixes=inherited['suffixes'],suffixes=records,
        target_family_totals=inherited['target_family_totals'],input_pins=pins,
        policy='Only RR190/class-padding/FPNEW90 constants; all other inherited EL gates remain mandatory in global report',
        blanket_all_EL_inactive_claim=False,native_MDA_mapping_inferred=False,exclusions_added=False,
        EDA_started=False,official_percentage_claimed=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    path=p.parse_args().output.resolve()
    need(path.parent==life.OUT and not path.exists(),'Fresh supplement only')
    result=evidence();life.save(path,result)
    print(json.dumps(dict(output=str(path),sha256=life.digest(path),status=result['status'],totals=result['target_family_totals'],suffix_populations=[r['population'] for r in result['suffixes']])),flush=True)
