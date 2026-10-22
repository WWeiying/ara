"""Closed source-only handoff. No guessed native aliases, receipt or EDA launch."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import review_masku_vl_constant770 as source
import queue_fp312_first_full_family as precedent

life, require = precedent.life, precedent.require
REVIEW_SHA = '8b2496d8a38f297658cbc91187d0961c3bbfc048f29518af2c35c50de02c66a5'
KEY = 'masku_vl_zero2'
FIRST = frozenset((KEY,))
ROLE = 'SOURCE_PROVEN_FIRST_FULL_SESSION'
OUT = life.OUT/'masku-vl-zero2-sourcefirst770-candidate-agent-20261007-01'
CONFIG = OUT/'config.json'


def contract(c):
    require(c['key'] in FIRST and c['key']==KEY and c['qualification_origin']==ROLE,
            'Closed exact source-role registry, no generic promotion')
    require(c['source_review_seal']==REVIEW_SHA and c['population']==770 and
            c['binding_state']=='FRESH_COMPLETE_BEFORE_REQUIRED', 'Exact reviewed source candidate')
    require(c['local_qualified'] is False and c['qualification_seal'] is None and
            c['population_application'] is False and c['launch_authorized'] is False and
            c['ready_for_union'] is False and c['native_reference'] is None and
            c['native_targets'] is None and c['el'] is None and not c['reference_pins'],
            'No source-to-native qualification shortcut or fabricated reference')
    require(len(c['instances'])==1,'Only one reviewed masku_operands instance')
    i=c['instances'][0]
    require(i['scope']==source.SCOPE and i['toggle_checksum']=='1400516067' and
            i['design_module_checksum']=='4132557224' and
            i['compiled_parameters']['NrLanes']=='4' and i['compiled_parameters']['DATAPATH_WIDTH']=='256',
            'Exact fullscope/compiled specialization')
    require(len(i['targets'])==2 and {n['name'] for n in i['targets']}==set(source.TARGETS),
            'Exactly two reviewed internal fields, never output port')
    for n in i['targets']:
        a=n['attributes']
        require(a['portnode']=='0' and a['left']=='255' and a['right']=='0' and a['file']=='558' and
                n['source_declaration_line']==(71 if n['name']==source.TARGETS[0] else 72) and
                n['native_label'] is None and n['logical_bits']==256 and n['missing_slots']==512,
                'Exact source-bound internal vector; native label remains unknown')
    require(len(i['protected'])==92 and sum(n['kind']=='arrays' for n in i['protected'])==8 and
            any(n['name']=='bit_enable_mask_o' and n['portnode']=='3' for n in i['protected']) and
            len(c['protected_children'])==16 and all(n['all_fields_protected'] for n in c['protected_children']),
            'Full 92 local/8 array/16 child complement and interface retention')
    require(c['candidate_bits']==512 and c['missing_serialized_positions']==1024 and
            c['prepared_overlap_positions']==0,'Exact reviewed residual, not a denominator')
    return c


def historical_search():
    # Search only native table files; bitmap JSON/hierarchy browser entries are not evidence.
    command=['rg','--files',str(life.OUT),'-g','*.tsv','-g','*before*.csv','-g','*inventory*.csv']
    listing=subprocess.run(command,cwd=life.ROOT,capture_output=True,text=True,check=True).stdout.splitlines()
    matches=[]
    for name in sorted(listing):
        path=Path(name)
        raw=path.read_bytes()
        if any(n.encode() in raw for n in source.TARGETS):matches.append(str(path))
    require(not matches,'Potential historical reference discovered: independently validate full scope/schema/pins before using it')
    return dict(status='NO_COMPLETE_HISTORICAL_NATIVE_REFERENCE_FOUND',
        searched_file_patterns=['*.tsv','*before*.csv','*inventory*.csv'],files_searched=len(listing),
        sorted_filename_ledger_sha256=hashlib.sha256(('\n'.join(sorted(listing))+'\n').encode()).hexdigest(),
        matching_files=[],limits='Search evidence only, not qualification. DVE session hierarchy/browser paths and compiled shape labels are not a native reference.')


def build():
    require(not OUT.exists(),'Fresh independent source candidate only')
    r=life.read_bound(source.REPORT,REVIEW_SHA);life.check(r['pins'])
    history=historical_search()
    pins=life.merge_pins(r['pins'],{str(source.REPORT):REVIEW_SHA})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_masku_vl_zero2_sourcefirst770.py'),
                 Path(precedent.__file__),Path(precedent.native.__file__)):
        pins[str(path)]=life.digest(path)
    instance=dict(scope=source.SCOPE,toggle_checksum=r['candidates'][0]['checksum'],
        design_module_checksum=r['candidates'][0]['module_checksum'],compiled_parameters=r['compiled_parameters'],
        targets=[dict(n,native_label=None) for n in r['candidates']],protected=r['local_protected'],
        expected_compiled_typed_objects=94,expected_compiled_arrays=8,
        native_row_count=None,native_row_count_authority='Fresh actual native scope traversal; do not assume compiled array container/leaf serialization equals native row count')
    integration=dict(owner='Hooke; no existing unified helper or registry edited',
        existing_V3_registry_accepts_this_key=False,role_registry_successor_required=[KEY],
        two_step_source_role=[
            'Explicitly allow only masku_vl_zero2 with this config/source-review seal in a new full770 successor registry; do not broaden existing qualified-family gates.',
            'Before exclusions, fresh-select exact fullscope and save complete actual rows plus scope token/checksum metadata. Bind all94 compiled typed objects including8 arrays through a bijection with exact packed/unpacked dimensions; forbid missing, duplicate, unmapped native containers or labels. Capture all16 child complements and parent/output alias guards.',
            'Resolve the two target native labels from that complete actual table only. Pin fresh before tables and binding metadata; native label/path/type/ranges/fullscope/checksums must uniquely match the source declarations. Do not guess foo[255:0], do not inherit a historical/local PASS.',
            'Only then emit the exact two-member typed source EL and apply within the same full session. Whole vector or exact 0to1+1to0 normalized members are allowed; reject scalar, partial, duplicate, mixed whole/split, direction loss, port or child members.',
            'Capture initial/apply/reset/reload/final full inventories and actual native saved EL. Check target-only transitions; zero target flags initial/reset/final, exact target flags apply/reload. All non-target flags stay zero in isolated qualification; child/interface/parent-alias guards remain unchanged. If union is already applied, require an isolated reset baseline and canonical baseline-difference check; never call union exclusions new target membership.',
            'Require terminal0 without timeout, cleanup verified, all five stages and complete typed EL/complement checks PASS before marking first-full qualification. Only afterward join the established qualified union and compute measured official full-report results; source candidate capacity is not a score.'],
        scope_inventory_authority='Fresh exact traversal plus pinned compiled typed inventory, not a fabricated TSV/model receipt',
        array_binding_failure_policy='HOLD exact target qualification and family integration; no omitted arrays, relaxed row counts or output-port exception',
        terminal_failure_policy='Preserve capture/reject inputs; no local retry or admission implied by this handoff')
    config=dict(schema='MASKU_INTERNAL_ZERO2_SOURCEFIRST770_CANDIDATE_V1',key=KEY,population=770,
        qualification_origin=ROLE,source_review=str(source.REPORT),source_review_seal=REVIEW_SHA,
        binding_state='FRESH_COMPLETE_BEFORE_REQUIRED',instances=[instance],protected_children=r['protected_children'],
        source_proof=r['source_proof'],candidate_bits=512,missing_serialized_positions=1024,
        prepared_overlap_positions=0,historical_search=history,native_reference=None,native_targets=None,
        reference_pins={},el=None,local_qualified=False,qualification_seal=None,ready_for_union=False,
        population_application=False,launch_authorized=False,automatic_retry=False,
        official_percentage=None,EDA_launched=False,RTL_modified=False,integration=integration,pins=pins)
    contract(config);life.check(pins)
    OUT.mkdir();life.save(CONFIG,config)
    print(json.dumps(dict(config=str(CONFIG),seal=life.digest(CONFIG),native_binding='FRESH_BEFORE_REQUIRED',
                         history_files_searched=history['files_searched'],pins=len(pins),EDA_launched=False)))


def family(seal):
    c=life.read_bound(CONFIG,seal);contract(c);life.check(c['pins'])
    r=life.read_bound(source.REPORT,REVIEW_SHA)
    require(c['instances'][0]['targets']==[dict(n,native_label=None) for n in r['candidates']] and
            c['instances'][0]['protected']==r['local_protected'] and c['protected_children']==r['protected_children'],
            'Complete target and protected source-config equality')
    return dict(config=c,qualification_origin=ROLE,local_qualified=False,ready_for_union=False,
        reference=None,native_targets=None,el=None,source_pins=c['pins'],reference_pins={},
        signals={source.SCOPE:list(source.TARGETS)},qualification_seal=None,population_application=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify'));p.add_argument('--seal');a=p.parse_args()
    if a.mode=='prepare':build()
    else:require(a.seal,'Pinned source-config seal');family(a.seal);print('SOURCE_CANDIDATE_VERIFY_PASS_NATIVE_BEFORE_STILL_REQUIRED')
