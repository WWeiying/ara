"""Hooke-owned next population adapter; source-first, never a local qualification."""
from pathlib import Path
import json
import qualify_queue_fp312_native as native

life,require=native.life,native.require
CONFIG=life.OUT/'queue-fp312-native768-prepare-agent-20261007-01/config.json'
CONFIG_SHA='2695e8b64ff86f16bfe3c21d697825430a531e066250ebc19a2610cb6b443a18'
ROLE='SOURCE_PROVEN_FIRST_FULL_SESSION'
contract=native.contract


def records(text,c):
    return json.loads(json.dumps(native.parse_el(text,c)))


def family():
    c=life.read_bound(CONFIG,CONFIG_SHA);contract(c);life.check(c['pins'])
    bindings,reference_pins=native.historical_binding()
    reference={};signals={};targets={};lines=['ANNOTATION: "'+native.ANNOTATION+'"']
    for i,binding in zip(c['instances'],bindings):
        scope=i['scope'];require(binding['scope']==scope,'Exact historical scope alignment')
        reference[scope]=sorted([row[1],row[2],row[3]] for row in binding['exact_full68_identity'])
        byname={row[0]:row[3] for row in binding['exact_full68_identity']}
        signals[scope]=sorted(n['name'] for n in i['targets'])
        targets[scope]=sorted(byname[n] for n in signals[scope])
        require(len(reference[scope])==68 and len(set(targets[scope]))==len(signals[scope]),'Full reference/target bijection')
        lines+=['CHECKSUM: "%s %s"'%(i['design_module_checksum'],i['toggle_checksum']),'INSTANCE: '+scope]
        lines+=['Toggle %s "logic %s%s"'%(n['name'],native.bounds(n),n['name']) for n in i['targets']]
    text='\n'.join(lines)+'\n';canonical=records(text,c)
    require(len(canonical)==312,'Exact source-declared complete fields')
    pins=life.merge_pins(life.merge_pins(c['pins'],reference_pins),
        {str(CONFIG):CONFIG_SHA,str(Path(__file__).resolve()):life.digest(__file__),
         str(Path(__file__).with_name('test_queue_fp312_first_full_family.py')):
             life.digest(Path(__file__).with_name('test_queue_fp312_first_full_family.py'))})
    return dict(config=c,output=str(CONFIG.parent),canonical=canonical,reference=reference,
        signals=signals,native_targets=targets,targets=targets,el=text,source_pins=pins,
        reference_pins=reference_pins,local_qualified=False,qualification_seal=None,
        qualification_origin=ROLE,population_application=False,EL_origin='SOURCE_TYPED_DECLARATION_NOT_NATIVE_CAPTURE',
        membership_authority='Exact source scope/whole typed fields, pinned historical full68 identity; fresh full-session all5stages/global EL/complement/main root/terminal0 required')
