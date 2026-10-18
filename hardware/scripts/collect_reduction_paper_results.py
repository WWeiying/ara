#!/usr/bin/env python3
"""Verify and collect the matched paper experiment; reject partial/failed suites."""
import argparse,hashlib,json,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
apps=['paper_rce_sweep','paper_rce_kernels','perf_rce_mixed_probe','perf_rce_exact_mixed','perf_rce_fp64_mixed','perf_rce_integer_seed']
configs={'baseline':('baseline_matched','run_baseline_retry'),'rce_only':('rce_only','run_rce_only'),'mixed':('mixed','run_mixed'),'full':('full','run_full')}
result={'status':'verified','configurations':{},'scope':'4 lanes, VLEN1024, fixed ordinary VALU/VMFPU queues4/4 and SLDU descriptors4; same frozen source/ELF per workload; simulation cycles','measurement_windows_per_configuration':43}
common=None;elfs={};dpi=None
for name,(build,run) in configs.items():
 b=args.root/build;r=args.root/run
 bm=json.loads((b/'source_manifest.json').read_text());m=json.loads((r/'manifest.json').read_text())
 assert bm['compile_returncode']==0 and bm['simulator_sha256']==sha(b/'simv')==m['simulator_sha256'],name
 if common is None:common=bm['sha256'];dpi=bm['dpi']
 assert bm['dpi']==dpi
 for f,h in dpi['input_sha256'].items():assert sha(Path(f))==h,f
 assert sha(Path(dpi['command'][-1]))==dpi['object_sha256']
 assert common==bm['sha256'],'Different functional source inputs'
 # Recheck frozen inputs rather than trusting their manifest alone.
 for f,h in common.items():assert sha(Path(f))==h,f
 assert {t['app'] for t in m['tests']}==set(apps) and len(m['tests'])==6,name
 extra=args.root/('run_stream_'+name);em=json.loads((extra/'manifest.json').read_text())
 assert em['simulator_sha256']==m['simulator_sha256'] and len(em['tests'])==1 and em['tests'][0]['app']=='paper_rce_stream_sum'
 all_tests=[(t,r) for t in m['tests']]+[(em['tests'][0],extra)]
 fl=(b/'filelist').read_text();defs=dict(re.findall(r'\+define\+(\w+)=([^\s]+)',fl))
 assert defs['ARA_RED_RCE_ALU_RESULT_DEPTH']=='4' and defs['ARA_RED_RCE_FP_RESULT_DEPTH']=='4' and 'ARA_RED_RCE_SLDU_BUFFER' in defs
 assert ('ARA_RED_RCE_INT' in defs)==(name!='baseline')
 assert ('ARA_RED_RCE_MIXED' in defs)==(name in ['mixed','full'])
 assert ('ARA_RED_RCE_INT_LATE_SEED' in defs)==(name=='full')
 assert 'ARA_RED_RCE_EXACT_SEED_RECEIVE' not in defs
 row={'simulator_sha256':m['simulator_sha256'],'manifest_sha256':sha(r/'manifest.json'),'defines':defs,'tests':{},'windows':{}}
 for t,run_path in all_tests:
  a=t['app'];s=(run_path/a/'stdout.log').read_text(errors='replace')
  assert t['returncode']==0 and t['pass'] and not t['failures'] and 'Core Test *** SUCCESS *** (tohost = 0)' in s,a
  assert not re.search(r'^.*(?:Fatal:|Error:|FAILED|\bFAIL\b|started at .*failed at|watchdog_timeout: 1).*$',s,re.M),a
  assert sha(run_path/'inputs'/a)==t['elf_sha256'],a
  if a not in elfs:elfs[a]=t['elf_sha256']
  assert elfs[a]==t['elf_sha256'],'ELF mismatch: '+a
  row['tests'][a]={'pass':True,'elf_sha256':t['elf_sha256'],'log_sha256':sha(run_path/a/'stdout.log'),'seconds':t['seconds']}
  if a=='paper_rce_sweep':
   found=re.findall(r'PAPER kind=(\w+) mode=(\w+) vl=(\d+) n=32 cycles=(\d+)',s);assert len(found)==30
   for kind,mode,vl,c in found:row['windows'][f'{kind}/{mode}/vl{vl}']=int(c)
  elif a in ['paper_rce_kernels','paper_rce_stream_sum']:
   found=re.findall(r'PAPER kernel=(\w+) vl=(\d+) rows=16 cycles=(\d+)',s);assert len(found)==(6 if a=='paper_rce_kernels' else 3)
   for kind,vl,c in found:row['windows'][f'kernel/{kind}/vl{vl}']=int(c)
  else:
   found=re.findall(r'PASS:.*cycles=(\d+)',s);assert len(found)==1,(a,found)
   row['windows'][a]=int(found[0])
 assert len(row['windows'])==43
 result['configurations'][name]=row
keys=set(result['configurations']['baseline']['windows'])
assert all(set(c['windows'])==keys for c in result['configurations'].values())
result['source_files']=len(common);result['program_executions']=28
result['source_identity_sha256']=hashlib.sha256(json.dumps(common,sort_keys=True).encode()).hexdigest()
args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n')
print('Verified 28 executions, 43 matched windows per configuration, identical source/ELF identities.')
