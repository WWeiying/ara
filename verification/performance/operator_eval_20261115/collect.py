#!/usr/bin/env python3
"""Collect only checked current-campaign results, retaining all unfinished cases."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from monitor_metrics import parse as parse_monitors


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def leaves(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, prefix+'.'+key if prefix else key)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from leaves(item, prefix+'['+str(i)+']')
    else:
        yield prefix, value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); a.output.mkdir()
    rows, pins, allcases = [], {}, []
    for path in a.campaign:
        report = json.loads((path/'result.json').read_text())
        if not report.get('post_source_image_pins_match'):
            raise ValueError('Source/image drift or unfinished identity audit: '+str(path))
        for name, expected in json.loads((path/'source-pins.json').read_text()).items():
            if sha(name) != expected:
                raise ValueError('Current input drift: '+name)
        for f in (path/'result.json',path/'source-pins.json',path/'plan.json'):
            pins[str(f)] = sha(f)
        for case in report['cases']:
            allcases.append(dict(campaign=str(path),**case))
            if case['state'] != 'PASS':
                continue
            work = path/'runs'/case['id']
            for name, expected in case.get('checked_artifact_hashes',{}).items():
                if sha(name) != expected:
                    raise ValueError('Checked artifact drift: '+name)
            numeric = json.loads((work/'numerical.json').read_text())
            proof = json.loads((work/'protocol.json').read_text())
            if numeric != case['measured'] or proof['status'] != 'PASS' or proof['issues'] or \
                proof['log_sha256'] != sha(work/'run.vcs.log') or \
                proof['vector_trace_sha256'] != sha(work/'vector.csv'):
                raise ValueError('Result/protocol evidence mismatch: '+case['id'])
            for name in ('result.json','numerical.json','protocol.json','run.vcs.log','vector.csv','commit.csv'):
                f = work/name; pins[str(f)] = sha(f)
            for key, value in leaves(case['measured']):
                rows.append(dict(campaign=path.name,case=case['id'],category=case['category'],
                                 metric=key,value=value))
            observations = parse_monitors(work)
            for f in work.glob('llm_perf_report_*.log'):
                pins[str(f)] = sha(f)
            for key,value in leaves(observations):
                rows.append(dict(campaign=path.name,case=case['id'],category=case['category'],
                                 metric='monitor.'+key,value=value))
    (a.output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    with (a.output/'metrics_long.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=('campaign','case','category','metric','value'))
        w.writeheader();w.writerows(rows)
    report=dict(state='CHECKED_CASES_COLLECTED',whole_model=False,cases=allcases,
                pass_count=sum(x['state']=='PASS' for x in allcases),total=len(allcases))
    (a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    text=['# 当前硬件算子实验结果','',
          '仅收录数值、独立协议及输入身份检查通过的本轮运行。完整七组计划的完成状态另行核对。','',
          '| 运行批次 | 测试项 | 类别 | 状态 | 墙钟秒 |','|---|---|---|---|---:|']
    for x in allcases:
        text.append('| '+Path(x['campaign']).name+' | '+x['id']+' | '+x.get('category','')+
                    ' | '+x['state']+' | '+str(round(x.get('wall_seconds',0),2))+' |')
    text += ['', '逐项原始指标见 `metrics_long.csv`。没有将软件路由、引擎周期或小切片外推为整模型性能。',
             '墙钟耗时仅用于仿真调度，不是目标硬件的执行时间。']
    (a.output/'RESULTS.md').write_text('\n'.join(text)+'\n')
    print(json.dumps(dict(state=report['state'],pass_count=report['pass_count'],total=report['total'])))


if __name__ == '__main__':
    main()
