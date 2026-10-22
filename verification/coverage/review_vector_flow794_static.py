"""Frozen794 vector-flow Branch/FSM gaps, diagnostic only; no EL generation."""
import argparse
import json
from pathlib import Path
import re

from inventory_operand_debug import Design
from closure_point_inventory import points
from branch720_next_report_contract import native_inventory
import targeted_toggle_evidence_v2 as t
import report_population794_soc61 as authority

ROOT,OUT = authority.life.ROOT,authority.life.OUT
REPORT = OUT/'current-population794-soc61-parent-20261008-01'
QUAL_SHA = 'fce23ff83487b83e51c069863710f4fad0c11716070ed3d4327aa57470972007'
CONFIG_SHA = '81526ba2020842417df95403931ca06441716ecf7b98ebf88ba0a67daca9434f'


def collect():
    pins = {}
    def read(path,sha):
        t.require(t.digest(path) == sha,'Frozen pin: '+str(path)); pins[str(path)] = sha
        return path.read_bytes()
    manifest = json.loads(read(authority.BASE,authority.BASE_SHA))
    p = authority.BASE.parent/'combined-bits.json'
    bitmap = json.loads(read(p,manifest['output_pins'][str(p)]))
    q = json.loads(read(REPORT/'qualification.json',QUAL_SHA))
    c = json.loads(read(REPORT/'config.json',CONFIG_SHA))
    t.require(q['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
              q['config_seal'] == CONFIG_SHA and q['population'] == q['actual_selected_tests'] == 794 and
              c['input_ledger'] == [c['input_ledger'][0],*bitmap['tests']], 'Qualified794 exact membership')
    inventory,branches = native_inventory(read(REPORT/'combined.el',c['pins'][str(REPORT/'combined.el')]))
    excluded_branch = set(); unknown_branch = []
    for scope,checks,line in branches:
        match = re.match(r'^Branch (\d+) "(\d+)" "[^"\n]*" \((\d+)\) ',line)
        if match: excluded_branch.add((scope,match[1],match[2],match[3]))
        else: unknown_branch.append(dict(scope=scope,checks=checks,line=line))
    excluded_fsm = set()
    for scope,checks,machine,line in inventory:
        if line.startswith(('State ','Transition ')):
            m = re.fullmatch(r'Fsm (\S+) "(\d+)"',machine)
            n = re.fullmatch(r'(State|Transition) (\S+) "([^"]+)"',line)
            t.require(m is not None and n is not None,'Exact FSM directive grammar')
            excluded_fsm.add((scope,m[1],m[2],n[1],n[2]))
    book_path = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book = json.loads(read(book_path,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'))
    design = Design(Path(c['input_ledger'][0]))
    for relative,sha in bitmap['design'].items(): read(design.db/relative,sha)
    read(design.db/'auxiliary/verilog.sourceinfo.xml',c['pins'][str(design.db/'auxiliary/verilog.sourceinfo.xml')])
    fsm_shape = t.xml(design.db/'shape/fsm.verilog.shape.xml')
    gaps,held = [],[]
    def selected(scope):
        return scope.endswith(('.i_dispatcher','.i_lane.i_operand_requester','.i_lane.i_lane_sequencer')) or bool(
            re.search(r'\.i_operand_queues\.i_operand_queue_[^.]+$',scope))
    for metric in ('branch','fsm'):
        for scope,row in bitmap['metrics'][metric].items():
            if not selected(scope) or not row['width']: continue
            try:
                if metric == 'fsm':
                    candidates = [n for n in fsm_shape.findall('fsmdef') if n.get('chksum') == row['checksum'] and
                                  n.get('name') == design.hierarchy[scope].get('name')]
                    t.require(len(candidates) == 1,'Exact FSM compiled module/checksum definition')
                    definition = candidates[0]
                else: definition = design.definition(scope,metric)
            except ValueError as error:
                held.append(dict(scope=scope,metric=metric,reason=str(error))); continue
            t.require(row['checksum'] in (None,definition.get('chksum')),'Compiled data checksum mismatch')
            source = Path(design.source(scope)['resolved_path'])
            actual = source
            if t.digest(source) != book[str(source)]: actual = OUT/'old-image-source-evidence-20261006-01'/source.name
            lines = read(actual,book[str(source)]).decode().splitlines()
            raw = format(int(row['bits'],16),'0%db'%row['width'])
            t.require(len(raw) == row['width'],'Raw bitmap overflow')
            if metric == 'branch':
                if any(r['scope'] == scope for r in unknown_branch):
                    held.append(dict(scope=scope,metric=metric,reason='Opaque native Branch selector: no ownership guess')); continue
                for point in points(metric,definition,row['width']):
                    key = (scope,point['native_id'],point['attributes']['chksum'],point['vector'])
                    if raw[point['raw_index']] != '0' or key in excluded_branch: continue
                    numbers = [int(e['id']) for e in point['expressions'] if e['id'].isdigit()]
                    excerpt = '\n'.join('%d: %s'%(n,lines[n-1]) for n in sorted(set(numbers)) if 0 < n <= len(lines))
                    gaps.append(dict(scope=scope,metric=metric,checksum=definition.get('chksum'),point=point,
                        source=str(actual),source_sha256=book[str(source)],excerpt=excerpt,
                        already_EL_owned=False,native_GUI_selector_not_invented=True))
            else:
                offset = 0
                for machine in definition.iter('fsmfsm'):
                    states = machine.findall('state'); names = {n.get('id'):n.get('name') for n in states}
                    for kind,nodes in (('State',states),('Transition',machine.findall('transition'))):
                        for node in nodes:
                            name = node.get('name') if kind == 'State' else names[node.get('fromid')]+'->'+names[node.get('toid')]
                            signature = node.get('id') if kind == 'State' else node.get('fromid')+'->'+node.get('toid')
                            # Native display signatures are not compiled XML
                            # state IDs. Match source names in the exact machine.
                            key = (scope,machine.get('name'),machine.get('chksum'),kind,name)
                            t.require(offset < len(raw),'FSM shape overflow')
                            if raw[offset] == '0' and key not in excluded_fsm:
                                gaps.append(dict(scope=scope,metric=metric,checksum=definition.get('chksum'),
                                    machine=machine.get('name'),machine_checksum=machine.get('chksum'),kind=kind,
                                    name=name,signature=signature,raw_index=offset,source=str(actual),source_sha256=book[str(source)],
                                    source_attributes=dict(node.attrib),already_EL_owned=False))
                            offset += 1
                t.require(offset == row['width'],'Full FSM serializer partition')
    pins[str(Path(__file__).resolve())] = t.digest(Path(__file__).resolve())
    for path,sha in pins.items(): t.require(t.digest(Path(path)) == sha,'Read-end drift')
    return dict(status='VECTOR_FLOW794_UNOWNED_BRANCH_FSM_DIAGNOSTIC',population=794,input_pins=pins,
                gaps=gaps,holds=held,raw_branch_vector_order='Existing reversed-per-spec diagnostic serializer',
                EDA_started=False,RTL_changed=False,EL_created=False,official_percentage=None)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True)
    a = p.parse_args(); t.require(a.output.parent.resolve() == OUT and not a.output.exists(),'Fresh independent output')
    result = collect()
    with a.output.open('x') as stream: json.dump(result,stream,indent=2,sort_keys=True); stream.write('\n')
    print(json.dumps(dict(output=str(a.output),sha256=t.digest(a.output),gaps=len(result['gaps']),holds=result['holds'])))
