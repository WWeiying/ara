import json,pathlib,hashlib,time
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
p=pathlib.Path('verification/fpga/current_board_review/masked_translation/negative_stride_remaining38_batch01/sv39/vcs_m6_plan02/prepared01').resolve();a=json.loads((p/'plan.json').read_text());c=json.loads((p/'complete.json').read_text());start=time.monotonic();seen={};bad=[]
for kind,pins in [('plan',a['pins']),('evidence',c['evidence_pins'])]:
 for name,want in pins.items():
  if name not in seen:
   try:seen[name]=sha(name)
   except OSError as e:seen[name]=str(e)
  if seen[name]!=want:bad.append([kind,name,want,seen[name]])
 print(kind,'count',len(pins),'checked',flush=True)
for n in ['plan.json','complete.json']:print(n,sha(p/n),flush=True)
print('BAD',bad,'unique',len(seen),'elapsed',time.monotonic()-start,flush=True)
for case in a['cases']:
 r=p/'replay/tests'/case['id'];ch=json.loads((r/'child_outcome.unvalidated.json').read_text());m=json.loads((r/'monitor_outcome.unvalidated.json').read_text());s=json.loads((r/'strict_original.json').read_text());t=json.loads((r/'trace_summary.json').read_text());w=json.loads((r/'observer.wait.json').read_text())
 assert seen[str(r/'input.elf')]==case['sha256']
 assert ch['command_sha256']==m['command_sha256']==seen[str(r/'command.json')]
 assert s['cases']==len(case['source_names']) and s['checks']==case['checks'] and s['rows']==t['rows'] and s['retired']==t['retire_count']
 assert ch['returncode']==m['returncode']==w['actual_wait_returncode']==0
names=[n for x in a['cases'] for n in x['source_names']];assert len(names)==len(set(names))==38
print('ELF_COMMAND_COUNTS_38_UNIQUE_MATCH')
