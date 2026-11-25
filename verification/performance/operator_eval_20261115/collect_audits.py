#!/usr/bin/env python3
"""Collect explicitly corrected, checked evidence without relabeling old FAILs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from monitor_metrics import parse as monitors


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def flatten(value,prefix=''):
    if isinstance(value,dict):
        for key,item in value.items():
            yield from flatten(item,prefix+'.'+key if prefix else key)
    elif isinstance(value,list):
        for key,item in enumerate(value):
            yield from flatten(item,prefix+'['+str(key)+']')
    else:
        yield prefix,value


def csvfile(path,fields,rows):
    with path.open('x') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        raise ValueError('Never overwrite summaries')
    rows,projections,pins,seen=[],[],{},set()
    for directory in a.audit:
        result=json.loads((directory/'result.json').read_text())
        if result['state']!='PASS' or not result['independent_protocol_checked'] or \
                not result['post_source_image_pins_match'] or result['original_worker_relabelled']:
            raise ValueError('Audit is not an independently accepted correction')
        for name,expected in json.loads((directory/'source-pins.json').read_text()).items():
            if sha(name)!=expected:
                raise ValueError('Audit input drift '+name)
            if name in pins and pins[name]!=expected:
                raise ValueError('Conflicting audit identity '+name)
            pins[name]=expected
        numeric=json.loads((directory/'numerical.json').read_text())
        protocol=json.loads((directory/'protocol.json').read_text())
        work=Path(result['evidence_run'])
        if numeric!=result['measured'] or numeric['state']!='PASS' or protocol['status']!='PASS' or \
                protocol['issues'] or protocol['log_sha256']!=sha(work/'run.vcs.log') or \
                protocol['vector_trace_sha256']!=sha(work/'vector.csv') or \
                any(protocol['contract_counts'][k] for k in ('exceptions','protocol_errors','outstanding')):
            raise ValueError('Corrected numerical/protocol evidence mismatch')
        key=str(work.resolve())
        if key in seen:
            raise ValueError('Same simulator run counted more than once')
        seen.add(key)
        for name in ('result.json','numerical.json','protocol.json','source-pins.json'):
            file=directory/name; pins[str(file)]=sha(file)
        measured=numeric['metrics']
        for metric,value in flatten(dict(measured=measured,monitor=monitors(work))):
            rows.append(dict(audit=directory.name,case=result['original_case'],metric=metric,value=value))
        build=Path(numeric['build']).parent
        identity={name:sha(build/'data'/name) for name in ('input_f32.bin','weights_row.bin')}
        for trial in measured['trials']:
            projections.append(dict(audit=directory.name,case=result['original_case'],
                backend=measured['backend'],baseline=measured['baseline_kind'],
                m=measured['m'],n=measured['n'],k=measured['k'],trial=trial['trial'],
                label=trial['label'],total_cycles=trial['total_cycles'],
                **{k+'_cycles':v for k,v in trial['software_cycles'].items()},
                engine_busy_cycles=trial['native_busy_cycles'],
                input_sha256=identity['input_f32.bin'],weights_sha256=identity['weights_row.bin']))
    pairs=[]
    for native in projections:
        if native['backend']!='native':
            continue
        matches=[r for r in projections if r['backend']=='rvv_x32' and
            all(r[k]==native[k] for k in ('m','n','k','trial','input_sha256','weights_sha256'))]
        if len(matches)>1:
            raise ValueError('Ambiguous paired baseline')
        if matches:
            rvv=matches[0]
            pairs.append(dict(case=native['case'],trial=native['trial'],
                rvv_cycles=rvv['total_cycles'],qbs_cycles=native['total_cycles'],
                full_call_speedup=rvv['total_cycles']/native['total_cycles'],
                matrix_speedup=rvv['execute_cycles']/native['execute_cycles'],
                scope='Calibration two-run first/repeat, not balanced main-figure acceptance'))
    a.output.mkdir()
    csvfile(a.output/'metrics_long.csv',('audit','case','metric','value'),rows)
    csvfile(a.output/'projection_calls.csv',tuple(projections[0]) if projections else ('case',),projections)
    csvfile(a.output/'paired_calibration.csv',tuple(pairs[0]) if pairs else ('case',),pairs)
    (a.output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    text=['# 校准投影：独立修正审计结果','',
        '原始 worker 保持 FAIL；此处仅收录另行数值、CSR 编码、协议和身份检查通过的证据。',
        '不修改 RTL，不重跑仿真。首次/重复分列，不混成稳态均值。','',
        '| 算子 | 路径 | 次数 | 完整调用周期 | 量化 | 打包 | 准入 | 执行 | 排空 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in projections:
        text.append('| '+' | '.join(str(r[k]) for k in ('case','baseline','trial','total_cycles',
            'quant_cycles','pack_cycles','admit_cycles','execute_cycles','drain_cycles'))+' |')
    text+=['','配对只在原始激活、行权重、M/N/K和调用序号全部一致时形成。',
           '本表属于校准；多输出强基线、形状和顺序偏置验收后再形成正式图。']
    (a.output/'RESULTS.md').write_text('\n'.join(text)+'\n')
    (a.output/'summary.json').write_text(json.dumps(dict(state='CHECKED_CORRECTED_AUDITS_COLLECTED',
        audits=len(a.audit),raw_simulator_runs=len(seen),calls=len(projections),paired_calls=len(pairs),
        original_failures_relabelled=False,whole_model=False),indent=2)+'\n')
    print((a.output/'summary.json').read_text())


if __name__=='__main__':
    main()
