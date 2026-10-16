"""Audit slide reductions against immutable original and board evidence."""
import argparse
import json
from pathlib import Path
from trace_masks import sha
from match_slide import compare


def require(value,message):
    if not value:
        raise ValueError(message)


def audit(root, original, report_path):
    m=json.loads((root/'manifest.json').read_text())
    require(sha(original)==m['original_report_sha256'],'Original report changed')
    parent=json.loads(original.read_text())
    parent=parent.get('report',parent)
    raw=json.loads(report_path.read_text())
    report=raw.get('report',raw)
    inputs={c['name']:c for c in report['inputs']['cases']}
    results={r['name']:r for r in report['results']}
    parent_inputs={c['name']:c for c in parent['inputs']['cases']}
    parent_results={r['name']:r for r in parent['results']}
    rows=[]
    for case in m['cases']:
        name,ancestor=case['name'],case['original_name']
        require(sha(root/'binaries'/name)==case['sha256'],'Local candidate ELF changed')
        rebuilt=(root/name/'original_rebuilt.elf' if name.startswith('rvv_small_gather_')
                 else root/(ancestor+'.original.elf'))
        require(parent_inputs[ancestor]['sha256']==case['original_elf_sha256']==
                sha(rebuilt),'Original ELF lineage mismatch')
        for file,digest in case['scenario_sources'].items():
            require(sha(root/name/file)==digest,'Candidate source changed')
        result=results.get(name)
        if name in inputs:
            require(inputs[name]['sha256']==case['sha256'],'Deployed ELF mismatch')
        require(result is None or name in inputs,'Result has no deployed identity')
        row=dict(name=name,original_name=ancestor,scenario_role=case['scenario_role'],
                 confirmed=False,status=result['status'] if result else 'not_started')
        if result:
            row.update(compare(parent_results[ancestor],result,case['original_failure_detail']))
        rows.append(row)
    return dict(scope='Exact recorded numerical discrepancy, not full RTL cause',cases=rows,
                manifest_sha256=sha(root/'manifest.json'),report_sha256=sha(report_path),
                original_report_sha256=sha(original),confirmed=sum(r['confirmed'] for r in rows),
                pending=sum(r['status'] in ('not_started','running') for r in rows))


def main():
    p=argparse.ArgumentParser()
    for key in ('root','original','report','out'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    result=audit(a.root,a.original,a.report)
    a.out.mkdir(exist_ok=False)
    (a.out/'sampled_report.json').write_bytes(a.report.read_bytes())
    (a.out/'symptoms.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('confirmed','pending')}))


if __name__=='__main__':
    main()
