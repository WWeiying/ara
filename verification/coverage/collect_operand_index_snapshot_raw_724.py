"""Single raw bitmap collect against formal724; diagnostic only, never admission."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import check_operand_index_snapshot_offline_v2 as qualified
import coverage_bitmap_delta as bitmap
import closure_point_inventory as shape
from inventory_operand_debug import Design

life,require = qualified.life,qualified.require
BASE = life.OUT/'akv-lifecycle-offline-admitted-724-parent-20261006-01'
BASE_SEAL = 'c7070c02860d4a6f5e12f405f926cd19fc6e6498d1905298e5e32826ee3a8ae0'
QUAL = life.OUT/'operand-index-snapshot-parent-architecture-v2-20261006-01'
QUAL_SEAL = '8074b4a620ae093e5812a0de0aa00321562143d45cb260dad9e9ce8e038cd2a6'
DESIGN = qualified.BUILD/'sim/simv.vdb'
RUN = qualified.RUN
PRODUCTS = {'single-raw-bits.json','proposed-combined-bits.json','raw-delta.json',
            'target-reconciliation724.json','gained-compiled-points.json','status.json',
            'single-inputs.txt','proposed-inputs.txt'}


def validate_bitmap(value):
    require(set(value['metrics']) == set(bitmap.METRICS),'Incomplete raw metrics')
    for rows in value['metrics'].values():
        require(rows,'Empty metric universe')
        for r in rows.values():
            require(type(r['width']) is int and r['width'] >= 0 and
                (r['checksum'] is None or (type(r['checksum']) is str and re.fullmatch(r'[0-9]+',r['checksum']))) and
                type(r['bits']) is str and re.fullmatch(r'0x[0-9a-f]+',r['bits']) and
                int(r['bits'],16) < (1 << r['width']),'Malformed bitmap')


def population(before,single):
    validate_bitmap(before)
    validate_bitmap(single)
    require(len(before['tests']) == len(set(before['tests'])) == 724 and
            single['tests'] == [str(RUN/'code.vdb')] and single['tests'][0] not in before['tests'],
            'Wrong/duplicate724 singleton population')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    proposed = bitmap.combine(before,single)
    require(proposed['tests'][:-1] == before['tests'] and len(set(proposed['tests'])) == 725,
            'Broken exact724 prefix')
    return proposed,bitmap.delta(before,proposed)


def hit(row,index):
    require(type(index) is int and 0 <= index < row['width'],'Invalid target index')
    return bool(int(row['bits'],16)&(1 << (row['width']-1-index)))


def reconcile(before,single,proposed,evidence):
    qualified.old.validate_targets(evidence)
    targets = []
    for t in evidence['targets']:
        metric,scope,raw = t['metric'],t['scope'],t['point']['raw_index']
        values = [v['metrics'][metric][scope] for v in (before,single,proposed)]
        require(all((r['width'],r['checksum']) == (t['width'],t['checksum']) for r in values),
                'Target exact shape drift')
        flags = [hit(r,raw) for r in values]
        require(flags[0] is False and flags[2] == flags[1],'Target zero/union mismatch')
        targets.append(dict(t,baseline724_hit=flags[0],sample_hit=flags[1],proposed_hit=flags[2],
                            new_vs724=flags[1],native_GUI_ID_qualification=False))
    return targets


def context():
    q = life.read_bound(QUAL/'qualification-seal.json',QUAL_SEAL)
    qualified.old.exact(q['result'],dict(status='FULL_SCALAR_RVC_VECTOR_CSR_SIGNATURE_QUALIFIED_NOT_ADMITTED',
        run=str(RUN),run_seal=qualified.RUN_SEAL,full_scalar_differential_qualified=True,
        all_scalar_memory_differential_qualified=True,scalar_uncompressed_memory_accesses=726,
        scalar_compressed_memory_accesses=645,total_scalar_memory_accesses=1371,
        skipped_scalar_memory=0,coverage_admitted=False),'Incomplete qualification')
    require(not (QUAL/'failure.json').exists(),'Rejected qualification')
    pins = life.merge_pins(q['input_pins'],q['output_pins'])
    pins = life.merge_pins(pins,{str(QUAL/'qualification-seal.json'):QUAL_SEAL})
    manifest = life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    qualified.old.exact(manifest,dict(schema='AKV_LIFECYCLE_HISTORICAL724_ADMISSION_V1',output=str(BASE),
        baseline=str(life.OUT/'narrow-reject-r1-cached-offline-admitted-723-20261006-01'),
        baseline_seal='2f68f64b880b95164f8db6aa2b569d305bd831ad4a05056563b2ab42eade45a4'),
        'Wrong formal724 ancestor')
    require(all(Path(p).parent == BASE for p in manifest['output_pins']),'Foreign baseline product')
    pins = life.merge_pins(pins,manifest['output_pins'])
    pins = life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SEAL})
    def read(path):
        require(str(path) in pins,'Unpinned input')
        return life.read_bound(path,pins[str(path)])
    inherited = read(BASE/'evidence-pins.json')
    pins = life.merge_pins(pins,inherited)
    status,before = read(BASE/'status.json'),read(BASE/'combined-bits.json')
    qualified.old.exact(status,dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=724,
        baseline=723,new_passed=1,coverage_admitted=True,rtl_changed=False),'Not formal PASS724')
    require((BASE/'combined-inputs.txt').read_text().splitlines() == [str(DESIGN),*before['tests']] and
            all(pins.get(p) == h for p,h in before['input_hashes'].items()),'Unbound full724 membership/metrics')
    ancestor_path = Path(manifest['baseline'])
    ancestor = life.read_bound(ancestor_path/'admission-manifest.json',manifest['baseline_seal'])
    pins = life.merge_pins(pins,ancestor['output_pins'])
    pins = life.merge_pins(pins,{str(ancestor_path/'admission-manifest.json'):manifest['baseline_seal']})
    parent = life.read_bound(ancestor_path/'combined-bits.json',ancestor['output_pins'][str(ancestor_path/'combined-bits.json')])
    prior = life.read_bound(Path(manifest['candidate'])/'candidate-seal.json',manifest['candidate_seal'])
    pins = life.merge_pins(pins,prior['output_pins'])
    pins = life.merge_pins(pins,{str(Path(manifest['candidate'])/'candidate-seal.json'):manifest['candidate_seal']})
    prior_single = life.read_bound(Path(manifest['candidate'])/'single-raw-bits.json',
        prior['output_pins'][str(Path(manifest['candidate'])/'single-raw-bits.json')])
    require(len(parent['tests']) == 723 and before == bitmap.combine(parent,prior_single),
            'Broken independent723->724 OR ancestry')
    run = read(RUN/'manifest.json')
    require(run['input_elf'] == str(qualified.old.ELF) and run['pins'][run['input_elf']] == qualified.old.ELF_SEAL and
            not any(p.endswith('.elf') and sha == qualified.old.ELF_SEAL for p,sha in inherited.items()),
            'Foreign/duplicate new ELF')
    vdb = RUN/'code.vdb'
    members = sorted(str(p) for p in vdb.rglob('*') if p.is_file())
    require(members == sorted(p for p in q['input_pins'] if Path(p).is_relative_to(vdb)) and
            not any(p.is_symlink() for p in vdb.rglob('*')),'Qualified VDB membership drift')
    files = [Path(__file__).resolve(),Path(__file__).with_name('test_collect_operand_index_snapshot_raw_724.py'),
             Path(bitmap.__file__).resolve(),Path(shape.__file__).resolve()]
    pins = life.merge_pins(pins,{str(p):life.digest(p) for p in files})
    life.check(pins)
    return pins,before,q


def gain_points(before,single,proposed,pins):
    design = Design(DESIGN)
    sourcebook = life.read_bound(qualified.BUILD/'build-source-pins.json',
                               pins[str(qualified.BUILD/'build-source-pins.json')])
    cond = shape.read_xml(design.db/'shape/cond.verilog.shape.xml')
    records = []
    for metric in bitmap.METRICS:
        for scope,old in before['metrics'][metric].items():
            gain = int(proposed['metrics'][metric][scope]['bits'],16)&~int(old['bits'],16)
            if not gain:
                continue
            require(metric != 'fsm','New FSM point mapping requires independent review; raw diagnostic retained')
            node = shape.definition(cond,design.hierarchy[scope],old['checksum']) if metric == 'cond' else \
                   design.definition(scope,metric)
            require(node.get('chksum') == old['checksum'],'Compiled gained shape differs')
            mapped = {p['raw_index']:p for p in shape.points(metric,node,old['width'])}
            source = design.source(scope)
            original = Path(source['resolved_path'])
            require(str(original) in sourcebook,'Unbound compiled gained source')
            path = original
            if life.digest(path) != sourcebook[str(original)]:
                path = life.OUT/'old-image-source-evidence-20261006-01'/original.name
            require(path.is_file() and life.digest(path) == sourcebook[str(original)],'Missing exact frozen gained source')
            pins = life.merge_pins(pins,{str(path):sourcebook[str(original)]})
            for raw in range(old['width']):
                if not gain&(1 << (old['width']-1-raw)):
                    continue
                require(raw in mapped and hit(single['metrics'][metric][scope],raw),'Unmapped/nonsingle gain')
                records.append(dict(metric=metric,scope=scope,point=mapped[raw],width=old['width'],
                    metric_checksum=old['checksum'],module_checksum=design.hierarchy[scope].get('chksum'),
                    source=source,source_evidence=str(path),source_sha256=sourcebook[str(original)],
                    baseline_hit=False,sample_hit=True,proposed_hit=True,native_GUI_ID_qualification=False))
    return pins,records


def evaluate(single,single_sha,pins,before,q):
    require(single['design'] == before['design'],'Foreign design')
    expected = {str(RUN/'code.vdb/snps/coverage/db/testdata'/qualified.old.NAME/(m+'.verilog.data.xml'))
                for m in bitmap.METRICS}
    require(set(single['input_hashes']) == expected and
            all(q['input_pins'].get(p) == h for p,h in single['input_hashes'].items()),
            'Foreign/incomplete qualified single metric pins')
    proposed,delta = population(before,single)
    evidence = life.read_bound(qualified.old.TARGETS,qualified.old.TARGET_SEAL)
    targets = reconcile(before,single,proposed,evidence)
    pins,records = gain_points(before,single,proposed,pins)
    counts = Counter(r['metric'] for r in records if r['scope'] == delta['scope'] or
                     r['scope'].startswith(delta['scope']+'.'))
    require(all(counts[m] == delta['metrics'][m] for m in bitmap.METRICS),'Compiled product gain count differs')
    state = dict(status='SNAPSHOT_RESTART_RAW724_DIAGNOSTIC_NOT_ADMITTED',baseline_tests=724,proposed_tests=725,
        new_admitted=0,coverage_admitted=False,raw_delta=delta['metrics'],baseline_seal=BASE_SEAL,
        qualification_seal=QUAL_SEAL,exact724_prefix=True,full_scalar_differential_qualified=True,
        all_scalar_memory_differential_qualified=True,whole_destination_CSR_neighbors_qualified=True,
        checks=457,exceptions=0,targets_hit=sum(t['sample_hit'] for t in targets),targets_total=16,
        inherited724_replayed=False,inherited724_pins_rechecked=True,official_DVE_report=False,
        new_RTL_signoff=False,rtl_changed=False,simulations_started=False,single_bitmap_sha=single_sha)
    return pins,{'proposed-combined-bits.json':proposed,'raw-delta.json':delta,
        'target-reconciliation724.json':targets,'gained-compiled-points.json':records,'status.json':state}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    output = parser.parse_args().output.absolute()
    require(output.parent == life.OUT and output.resolve() == output and not output.exists(),'Fresh direct output required')
    output.mkdir()
    try:
        pins,before,q = context()
        with (output/'single-inputs.txt').open('x') as stream:
            stream.write(str(DESIGN)+'\n'+str(RUN/'code.vdb')+'\n')
        # This is the sole native XML read/collect; subsequent gates use the sealed cache.
        single = bitmap.collect(output/'single-inputs.txt')
        life.save(output/'single-raw-bits.json',single)
        single_sha = life.digest(output/'single-raw-bits.json')
        proposed,delta = population(before,single)
        life.save(output/'raw-delta.json',delta)
        life.save(output/'proposed-combined-bits.json',proposed)
        life.save(output/'target-reconciliation724.json',reconcile(before,single,proposed,
            life.read_bound(qualified.old.TARGETS,qualified.old.TARGET_SEAL)))
        pins,artifacts = evaluate(single,single_sha,pins,before,q)
        for name,value in artifacts.items():
            if not (output/name).exists():
                life.save(output/name,value)
            else:
                require(json.loads((output/name).read_bytes()) == value,'Diagnostic intermediate drift')
        with (output/'proposed-inputs.txt').open('x') as stream:
            stream.write('\n'.join([str(DESIGN),*artifacts['proposed-combined-bits.json']['tests']])+'\n')
        life.check(pins)
        life.save(output/'diagnostic-seal.json',dict(input_pins=pins,
            output_pins={str(output/n):life.digest(output/n) for n in PRODUCTS},
            result=artifacts['status.json'],coverage_admitted=False,qualification_seal=QUAL_SEAL))
        print(json.dumps(dict(output=str(output),seal=life.digest(output/'diagnostic-seal.json'),result=artifacts['status.json'])))
    except Exception as error:
        life.save(output/'failure.json',dict(status='RAW_DIAGNOSTIC_REJECTED_NOT_ADMITTED',reason=str(error)))
        raise


if __name__ == '__main__':
    main()
