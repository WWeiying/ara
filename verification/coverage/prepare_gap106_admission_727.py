"""Qualified GAP106 singleton + authoritative726; candidate only, no admission/EDA."""
import argparse
import json
from pathlib import Path

import qualify_gap106_native as qualifier
import coverage_bitmap_delta as bitmap
import closure_point_inventory as inventory

life, require = qualifier.life, qualifier.require
BASE = life.OUT/'vnclipu-offline-admitted-726-parent-20261006-01'
BASE_SEAL = '3ce8d24ffa5bfee7f4b363878b348af4e4b4de67995bc71db7b2bb6931121517'
PRIOR = life.OUT/'gap105-offline-admitted-725-parent-20261006-01'
PRIOR_SEAL = '0f49638e8cea36b28b5832e7eaeea39ee9b5249a162de3f3732c0fcd13a5a397'
QUAL = life.OUT/'gap106-native-qualification-ready-20261006-01'
CONFIG = QUAL.with_name(QUAL.name+'.prepared.json')
CONFIG_SEAL = '4d1b4cb99f82e03a6a3d5a60fdd0527b627e457f33f9e66374f27a85d4121532'
DESIGN = life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'


def qualification_contract(record, audit):
    qualifier.runner.exact(record, dict(status='GAP106_SOFTWARE_NATIVE_QUALIFIED_NOT_ADMITTED',
        full_scalar_isa_verified=False, spike_custom_isa_pass=False, coverage_admitted=False,
        coverage_increment_measured=False, gain_requires_latest_formal_baseline=True,
        simulation_rerun=False, rtl_changed=False), 'Qualification differs')
    qualifier.runner.exact(audit, dict(status='GAP106_COMPLETE_SOFTWARE_NATIVE_PASS_NOT_FULL_SCALAR_ISA',
        custom_write_bytes=256, custom_active_bytes=8, custom_zero_tail_bytes=248,
        full_vrf_bytes=8192, initial_vrf_bytes=8192, csr_values=24, source_guard_bytes=6880,
        checks=41, full_scalar_isa_verified=False, spike_custom_isa_pass=False,
        coverage_admitted=False), 'Native audit differs')
    require([(b['phase'],b['pc'],b['backend_vl'],b['software_vl'],b['native_total_write_bytes'])
             for b in audit['bindings']]==[(0,0x8000017a,32,1,128),(1,0x80000252,32,1,128)],
            'Exact native sites differ')
    c = audit['contract']
    require(c['requests']==c['responses']==51 and all(c[k]==0 for k in
        ('exceptions','protocol_errors','outstanding','req_stalled','resp_stalled')),
        'Terminal native conservation differs')


def population(before, prior, single):
    require(len(prior['tests'])==len(set(prior['tests']))==725 and
            len(before['tests'])==len(set(before['tests']))==726 and
            before['tests'][:-1]==prior['tests'], 'Not exact725 prefix in726')
    require(single['tests']==[str(qualifier.RUN/'code.vdb')] and
            single['tests'][0] not in before['tests'], 'Not unique original singleton')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    combined = bitmap.combine(before,single)
    require(combined['tests']==before['tests']+single['tests'] and
            len(set(combined['tests']))==727, 'Not exact726 plus one')
    change = bitmap.delta(before,combined)
    require(sum(change['metrics'].values())>0, 'No fresh726 product gain; do not admit')
    return combined,change


def bit(row, raw):
    require(type(raw) is int and 0<=raw<row['width'], 'Invalid raw coordinate')
    value = int(row['bits'],16)
    require(value>=0 and value.bit_length()<=row['width'], 'Bitmap overflow')
    return bool(value & (1<<(row['width']-1-raw)))


def compiled(before, single, combined, pre, read):
    db = DESIGN/'snps/coverage/db'
    design = inventory.read_xml(db/'design/verilog.design.xml')
    nodes = {n.get('id'):(n,d) for d in design.findall('srcdef') for n in d.findall('srcinst')}
    require(len(nodes)==sum(len(d.findall('srcinst')) for d in design.findall('srcdef')), 'Duplicate hierarchy')
    def path(key, seen=()):
        require(key not in seen, 'Hierarchy cycle')
        node,_ = nodes[key]; parent = node.get('pid')
        return (path(parent,seen+(key,))+'.' if parent in nodes else '')+node.get('name')
    hierarchy = {path(k):d for k,(_,d) in nodes.items()}
    require(len(hierarchy)==len(nodes), 'Duplicate scopes')
    files = {n.get('id'):n.get('name') for n in inventory.read_xml(
        db/'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
    shapes = {m:inventory.read_xml(db/('shape/'+m+'.verilog.shape.xml')) for m in before['metrics']}
    gained = []
    for metric, rows in before['metrics'].items():
        for scope,old in rows.items():
            new = combined['metrics'][metric][scope]
            changed = [r for r in range(old['width']) if not bit(old,r) and bit(new,r)]
            if not changed: continue
            require(old['checksum'] is not None, 'Missing gained instance checksum: '+scope)
            definition = inventory.definition(shapes[metric],hierarchy[scope],old['checksum'])
            points = {p['raw_index']:p for p in inventory.points(metric,definition,old['width'])}
            for raw in changed:
                p = points[raw]; source = Path(files[p['file_id']])
                read(source)
                gained.append(dict(scope=scope,metric=metric,width=old['width'],checksum=old['checksum'],
                    point=p,source=str(source),before_hit=False,single_hit=bit(single['metrics'][metric][scope],raw),
                    after_hit=True))
    scope = pre['scope']; old = before['metrics']['cond'][scope]
    definition = inventory.definition(shapes['cond'],hierarchy[scope],old['checksum'])
    points = {p['raw_index']:p for p in inventory.points('cond',definition,old['width'])}
    require(old['width']==876 and str(old['checksum'])=='3394658800' and
            len(pre['targets'])==2, 'Exact target shape differs')
    targets = []
    for p in pre['targets']:
        raw = p['raw_index']
        require(points[raw]==p and bit(single['metrics']['cond'][scope],raw), 'Native target identity/hit differs')
        targets.append(dict(scope=scope,point=p,before_hit=bit(old,raw),single_hit=True,
                            after_hit=bit(combined['metrics']['cond'][scope],raw)))
    return gained,targets


def prepare(output, qualification_seal):
    output = Path(output).absolute()
    require(output.parent==life.OUT and output.resolve()==output and not output.exists(), 'Fresh output required')
    pins = {}
    def expected(path, seal):
        nonlocal pins
        pins = life.merge_pins(pins,{str(path):seal})
        return life.read_bound(path,seal)
    def read(path):
        require(str(path) in pins, 'Unbound input: '+str(path))
        life.check({str(path):pins[str(path)]})
        return Path(path).read_bytes()
    record = expected(QUAL/'qualification.json',qualification_seal)
    audit = expected(QUAL/'runtime-audit.json',record['audit_sha256'])
    qualification_contract(record,audit)
    pins = life.merge_pins(pins,expected(QUAL/'evidence-pins.json',record['pins_sha256']))
    config = expected(CONFIG,CONFIG_SEAL)
    require(config['run']==str(qualifier.RUN) and config['run_prepared_seal']==qualifier.RUN_SEAL and
            config['status']=='GAP106_NATIVE_PREPARED_NOT_COLLECTED', 'Original reviewed run differs')
    require(life.merge_pins(pins,config['pins'])==pins, 'Lost prepared pins')
    manifest = expected(BASE/'admission-manifest.json',BASE_SEAL)
    require(manifest['schema']=='VNCLIPU_HISTORICAL726_ADMISSION_V1' and manifest['output']==str(BASE) and
            manifest['baseline']==str(PRIOR) and manifest['baseline_seal']==PRIOR_SEAL and
            all(Path(p).parent==BASE for p in manifest['output_pins']), 'Not authoritative726')
    pins = life.merge_pins(pins,manifest['output_pins'])
    pins = life.merge_pins(pins,json.loads(read(BASE/'evidence-pins.json')))
    status = json.loads(read(BASE/'status.json'))
    require(status['aggregate_passed']==726 and status['new_passed']==1 and
            status['coverage_admitted'] is True and status['status']=='PASS_RAW_UNION_HISTORICAL_ONLY',
            'Not admitted726')
    previous = expected(PRIOR/'admission-manifest.json',PRIOR_SEAL)
    prior = expected(PRIOR/'combined-bits.json',previous['output_pins'][str(PRIOR/'combined-bits.json')])
    before = json.loads(read(BASE/'combined-bits.json'))
    require(read(BASE/'combined-inputs.txt').decode().splitlines()==[str(DESIGN),*before['tests']],
            'Exact726 design/input order differs')
    pins = life.merge_pins(pins,before['input_hashes'])
    pins = life.merge_pins(pins,{str(DESIGN/'snps/coverage/db'/p):h for p,h in before['design'].items()})
    # Shape/source information is already sealed by the preflight and qualification.
    pre = expected(qualifier.runner.PRE/'preflight-manifest.json',qualifier.runner.PRE_SEAL)
    for p in (Path(bitmap.__file__).resolve(),Path(inventory.__file__).resolve(),Path(inventory.score.__file__).resolve()):
        require(str(p) in pins, 'Unbound reused bitmap helper: '+str(p))
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_prepare_gap106_admission_727.py')):
        pins = life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    symbols,data,sites = qualifier.elf_view()
    require(qualifier.runtime(qualifier.RUN,symbols,data,sites,qualifier.independent_native())==audit,
            'Actual qualified runtime replay differs')
    # No directory/bitmap collection before the qualification gate and strict replay.
    output.mkdir()
    try:
        inputs = output/'single-inputs.txt'
        with inputs.open('x') as stream:stream.write(str(DESIGN)+'\n'+str(qualifier.RUN/'code.vdb')+'\n')
        single = bitmap.collect(inputs)
        pins = life.merge_pins(pins,single['input_hashes'])
        combined,change = population(before,prior,single)
        gained,targets = compiled(before,single,combined,pre,read)
        life.check(pins)
        products = dict(single_bits=single,combined_bits=combined,raw_delta=change,
                        gained_compiled_points=gained,target_hits=targets,evidence_pins=pins)
        for name,value in products.items():life.save(output/(name.replace('_','-')+'.json'),value)
        life.save(output/'candidate.json',dict(status='GAP106_EXACT726_PLUS_ONE_CANDIDATE_NOT_ADMITTED',
            baseline=str(BASE),baseline_seal=BASE_SEAL,qualification=str(QUAL),qualification_seal=qualification_seal,
            proposed_population=727,exact726_prefix=True,coverage_admitted=False,
            full_scalar_isa_verified=False,spike_custom_isa_pass=False,rtl_changed=False,simulations_started=False,
            raw_delta=change['metrics'],output_pins={str(p):life.digest(p) for p in output.iterdir() if p.is_file()}))
    except Exception as error:
        life.save(output/'failure.json',dict(status='REJECTED_NOT_ADMITTED',reason=type(error).__name__+': '+str(error)))
        raise
    return life.digest(output/'candidate.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification-seal',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(dict(output=str(args.output),seal=prepare(args.output,args.qualification_seal))))


if __name__=='__main__':main()
