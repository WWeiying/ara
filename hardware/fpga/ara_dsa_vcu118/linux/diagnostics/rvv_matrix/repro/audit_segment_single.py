"""Match preparation alignment traps; matching traps do not imply an RTL defect."""
import argparse
import json
from pathlib import Path
import subprocess
from audit_segment_setup import inspect
from audit_slide import require
from trace_masks import sha


def signature(row):
    return {k: row[k] for k in ('trap_opcode', 'trap_instruction', 'signal', 'cause',
            'misalignment_bytes', 'preparation_vl', 'target_vl_argument', 'later_target_instruction')}


def audit(root, report_path, cross):
    manifest = json.loads((root/'manifest.json').read_text())
    original_path = root/'original_report.json'
    require(sha(original_path) == manifest['original_report_sha256'], 'Original report changed')
    raw = json.loads(original_path.read_text()); original = raw.get('report', raw)
    raw = json.loads(report_path.read_text()); report = raw.get('report', raw)
    def index(rows):
        table = {c['name']: c for c in rows}
        require(len(table) == len(rows), 'Duplicate case identity')
        return table
    old_inputs, old_results = index(original['inputs']['cases']), index(original['results'])
    inputs, results = index(report['inputs']['cases']), index(report['results'])
    require(manifest['cases'], 'Empty candidate manifest')
    index(manifest['cases'])
    rows = []
    for c in manifest['cases']:
        name, parent = c['name'], c['original_name']
        require(c['scenario_role'] == 'single_preparation_call', 'Wrong candidate role')
        directory = root/name
        require(sha(directory/'original.elf') == c['original_elf_sha256'] == old_inputs[parent]['sha256'],
                'Original ELF changed')
        for file,digest in c['scenario_sources'].items():
            require(sha(directory/file) == digest, 'Candidate source changed')
        binary = root/'binaries'/name
        require(sha(binary) == c['sha256'], 'Candidate ELF changed')
        dis = subprocess.check_output([cross+'objdump','-d',str(directory/'original.elf')],text=True)
        parent_case = dict(c,name=parent,sha256=c['original_elf_sha256'])
        old = inspect(parent_case,old_results[parent],dis)
        require(old == c['measured_original'], 'Stored original trap differs')
        r = results.get(name)
        if name in inputs:require(inputs[name]['sha256'] == c['sha256'], 'Deployed candidate differs')
        require(r is None or name in inputs, 'Result without deployed identity')
        row = dict(name=name,status=r['status'] if r else 'not_started',confirmed=False,
                   expected_signature=signature(old))
        if r:
            dis = subprocess.check_output([cross+'objdump','-d',str(binary)],text=True)
            try:
                observed = inspect(c,r,dis)
                row['observed_signature'] = signature(observed)
                row['confirmed'] = row['observed_signature'] == row['expected_signature']
            except ValueError as exc:
                row['reason'] = str(exc)
        rows.append(row)
    return dict(cases=rows,confirmed=sum(r['confirmed'] for r in rows),
                pending=sum(not r['confirmed'] for r in rows),
                scope='Same preparation alignment exception, not a segment-target or RTL defect claim',
                architectural_bug_proven=False, original_c_source_equivalence_proven=False,
                manifest_sha256=sha(root/'manifest.json'), report_sha256=sha(report_path))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('root','report','out'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--cross',required=True)
    a=p.parse_args();result=audit(a.root,a.report,a.cross)
    a.out.mkdir(exist_ok=False)
    (a.out/'sampled_report.json').write_bytes(a.report.read_bytes())
    (a.out/'symptoms.json').write_text(json.dumps(result,indent=2)+'\n')
    print('CONFIRMED',result['confirmed'],'PENDING',result['pending'])


if __name__=='__main__':main()
