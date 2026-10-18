#!/usr/bin/env python3
"""Validate full functional suites and report every cycle delta for production RTL changes."""
import argparse,hashlib,json,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root',type=Path)
p.add_argument('--min-performance-apps',type=int,default=5,help='Use 0 explicitly for a function-only suite')
a=p.parse_args()
reports=[json.loads((a.root/m/'regression/manifest.json').read_text()) for m in ['baseline','scalar']]
byapp=[{t['app']:t for t in r['tests']} for r in reports]
assert byapp[0].keys()==byapp[1].keys() and byapp[0]
for mode, report, tests in zip(['baseline','scalar'], reports, byapp):
 assert report['state']=='COMPLETE',f'{mode}: regression is not terminal'
 inputs=a.root/mode/'regression/inputs'
 expected={p.name for p in inputs.iterdir() if p.is_file()}
 assert expected and len(report['tests'])==len(tests) and set(tests)==expected, f'{mode}: suite incomplete or duplicate tests'
 if 'expected_apps' in report:
  assert expected==set(report['expected_apps']), f'{mode}: input set differs from requested suite'
 config=a.root/'configuration.json'
 if config.exists():
  assert expected==set(json.loads(config.read_text())['apps']), f'{mode}: suite differs from configuration'
 assert hashlib.sha256(Path(report['simulator']).read_bytes()).hexdigest()==report['simulator_sha256'],f'{mode}: simulator changed'
 for name,test in tests.items():
  assert hashlib.sha256((inputs/name).read_bytes()).hexdigest()==test['elf_sha256'],f'{mode}: frozen ELF changed: {name}'
rows=[]
for name,t in byapp[0].items():
 u=byapp[1][name]
 assert t['pass'] and u['pass'],name
 assert t['elf_sha256']==u['elf_sha256'],name
 windows=[]
 finishes=[]
 for mode in ['baseline','scalar']:
  s=(a.root/mode/'regression'/name/'stdout.log').read_text()
  assert 'Core Test *** SUCCESS *** (tohost = 0)' in s,name
  assert not re.search(r'^.*(?:Fatal:|Error:|FAILED|\bFAIL\b|started at .*failed at|watchdog_timeout: 1).*$',s,re.M),name
  windows.append([int(value) for match in re.findall(r'\[PERF\] total_cycles\s*:\s*(\d+)|(?<![\w])cycles=(\d+)',s) for value in match if value])
  finishes.append(int(re.search(r'\$finish at simulation time\s+(\d+)',s)[1]))
 assert len(windows[0])==len(windows[1]),name
 rows.append({'app':name,'elf_sha256':t['elf_sha256'],'baseline_cycles':windows[0],
              'scalar_cycles':windows[1],'cycle_measurement_available':bool(windows[0]),'finish_time_ticks':finishes,
              'cycle_deltas':[candidate-baseline for baseline,candidate in zip(*windows)],
              'finish_time_delta_ticks':finishes[1]-finishes[0],
              'no_cycle_regression':all(y<=x for x,y in zip(*windows)) and finishes[1]<=finishes[0]})
assert sum(t['cycle_measurement_available'] for t in rows)>=a.min_performance_apps
r={'tests':rows,'all_pass':True,'functional_all_pass':True,
   'all_no_cycle_regression':all(t['no_cycle_regression'] for t in rows),
   'comparison_policy':'functional success required; cycle changes reported without a performance pass criterion',
   'complete_suite':True,'expected_test_count':len(byapp[0]),
   'scope':'matched full-SoC simulation windows; frequency and area require synthesis evidence'}
(a.root/'comparison.json').write_text(json.dumps(r,indent=2)+'\n')
for t in rows:print(t['app'],t['baseline_cycles'],'->',t['scalar_cycles'], 'delta=',t['cycle_deltas'], 'finish_delta_ticks=',t['finish_time_delta_ticks'])
raise SystemExit(0)
