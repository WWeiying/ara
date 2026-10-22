import json,sys,hashlib,collections,re
from pathlib import Path
sys.path.insert(0,'verification/coverage')
import inventory_operand_debug as compiled
from closure_point_inventory import read_xml,definition
root=Path(__file__).resolve().parents[2]
out=root/'verification/out'
base=out/'pure-war-offline-admitted-731-parent-20261006-01'
build=out/'repaired-aligned-build-20260930-01/build-source-pins.json'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected=json.loads(build.read_bytes())
source_names=['hardware/src/vlsu/qbs/qbs_payload_buffer.sv','hardware/src/vlsu/qbs/qbs_block_adapter.sv','hardware/src/vlsu/qbs/qbs_compute_engine.sv','hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv','hardware/src/vlsu/qbs/qbs_engine.sv','hardware/include/qbs_pkg.sv']
pins={str(build):sha(build)}
sources={}
for name in source_names:
 p=root/name; h=sha(p); assert expected[str(p)]==h,(name,h)
 pins[str(p)]=h;sources[name]={'sha256':h,'build_matches':True}
manifest=base/'admission-manifest.json'
assert sha(manifest)=='79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641'
m=json.loads(manifest.read_bytes())
for name in ['admission-manifest.json','combined-bits.json','combined-inputs.txt','status.json']:
 p=base/name;h=sha(p);pins[str(p)]=h
 if name!='admission-manifest.json':assert m['output_pins'][str(p)]==h
bits=json.loads((base/'combined-bits.json').read_bytes())
assert len(bits['tests'])==len(set(bits['tests']))==731
design=compiled.Design(out/'repaired-aligned-build-20260930-01/sim/simv.vdb')
shape_path=design.db/'shape/cond.verilog.shape.xml'
shape=read_xml(shape_path)
for p in [shape_path,design.db/'design/verilog.design.xml',design.db/'auxiliary/verilog.sourceinfo.xml']:
 pins[str(p)]=sha(p)
def loc_w(o):
 return (0,o) if o<128 else (1,o-128) if o<192 else (2,o-192)
def loc_a(o):
 return (2,o) if o<4 else (0,o-4) if o<260 else (2,o-256)
def starts(size,phase):
 return [0]+list(range(16-phase if phase else 16,size,16))
wsets={j:set() for j in range(16)}
wwitness={}
for group in range(2):
 phase=(2+group*840)%16
 for start in starts(840,phase):
  size=min(16-phase,840) if start==0 and phase else min(16,840-start)
  for j in range(size):
   absolute=start+j;row,o=divmod(absolute,210)
   if row>=4:continue
   plane,offset=loc_w(o)
   wsets[j].add(offset);wwitness.setdefault((j,offset),dict(group=group,phase=phase,beat_offset=start,byte=j,row=row,profile_offset=o,plane=plane,location_offset=offset))
asets={bank:{j:set() for j in range(16)} for bank in (0,1)}
awitness={}
for phase in (0,4,8,12):
 for start in starts(2336,phase):
  size=min(16-phase,2336) if start==0 and phase else min(16,2336-start)
  for j in range(size):
   o=start+j
   if o<32:ctx,native=divmod(o,4)
   elif o<2080: native,ctx=divmod(o-32,8);native+=4
   else:
    pair,byte=divmod(o-2080,2);aux,ctx=divmod(pair,8);native=260+2*aux+byte
   plane,offset=loc_a(native)
   bank=ctx//4
   if bank>1:continue
   asets[bank][j].add(offset)
   awitness.setdefault((bank,j,offset),dict(phase=phase,beat_offset=start,byte=j,context=ctx,profile_offset=native,plane=plane,location_offset=offset))
report={'schema':'PAYLOAD_COND731_STATIC_CLUSTER_REVIEW_V1','status':'READONLY_STATIC_REVIEW_NO_QUALIFICATION','baseline':str(base),'baseline_seal':sha(manifest),'source_bindings':sources,'pins':pins,'parameters':{'NativeView':False,'PredecodedWriteLocations':True,'StreamWriteData':True,'ActivationContextBase_bank0':0,'ActivationContextBase_bank1':4},'banks':{}}
for bank in (0,1):
 scope=next(s for s in bits['metrics']['cond'] if s.endswith('bank%d.i_payload_buffer'%bank))
 rec=bits['metrics']['cond'][scope]; assert (rec['width'],rec['checksum'])==(21503,'2947893042')
 node=definition(shape,design.hierarchy[scope],rec['checksum'])
 pts=compiled.points('cond',node,rec['width'])
 miss=[p for p in pts if not (int(rec['bits'],16)>>(rec['width']-1-p['raw_index']))&1]
 clusters=[]
 for line,n in collections.Counter(p['line'] for p in miss).most_common():
  rows=[p for p in miss if p['line']==line]
  clusters.append({'source_line':int(line),'missing':n,'vectors':dict(collections.Counter(p['vector'] for p in rows)),'examples':rows[:2]})
 reachable=[]
 for point in miss:
  line=int(point['line'])
  if line not in (91,97,346,349) or point['vector']!='1':continue
  gen=dict((k,int(v)) for k,v in re.findall(r'(\w+)=(\d+)',point['spec']['generate_info']))
  j=gen.get('writer',gen.get('n',-1))-16
  byte=gen.get('byte_lane',gen.get('b',-1))
  if not 0<=j<16:continue
  offsets=wsets[j] if line in (91,346) else asets[bank][j]
  mask=15 if line==91 else 31 if line==97 else 255
  matching=next((o for o in sorted(offsets) if o&mask==byte),None)
  if matching is not None:
   witness=wwitness[j,matching] if line in (91,346) else awitness[bank,j,matching]
   reachable.append({'raw_index':point['raw_index'],'native_id':point['native_id'],'vector':point['vector'],'source_line':line,'spec_checksum':point['attributes']['chksum'],'expression':point['expression'],'generate_info':point['spec']['generate_info'],'finite_transport_witness':witness})
 report['banks'][str(bank)]={'scope':scope,'module_source':design.source(scope),'metric_checksum':rec['checksum'],'width':rec['width'],'missing':len(miss),'clusters':clusters,'direct_elaboration_predicate_missing':[p for p in miss if re.fullmatch(r'\((p|slot|StreamWriteData|NativeView)\s*(?:==|!=).*\)',p['expression'])],'native_view_405_469_missing':sum(405<=int(p['line'])<=469 for p in miss),'incoming_comparison_witness_count':len(reachable),'incoming_comparison_witnesses':reachable,'side_older_cluster_upper_bound':sum(int(p['line']) in (375,378,401,403) for p in miss),'dynamic_byte_valid_preserved_count':sum(int(p['line']) in (282,285,288) for p in miss)}
report['numerical_bounds']={'total_missing':sum(v['missing'] for v in report['banks'].values()),'incoming_comparison_finite_witnesses':sum(v['incoming_comparison_witness_count'] for v in report['banks'].values()),'guaranteed_DUT_gain':0,'side_older_source_induction_review_population_upper_bound':sum(v['side_older_cluster_upper_bound'] for v in report['banks'].values()),'native_waiver_qualified':0}


def replay_pending(kind,bank,phase,group=0):
 size=840 if kind=='weight' else 2336
 actualphase=(phase+group*840)%16 if kind=='weight' else phase
 beats=[]
 for start in starts(size,actualphase):
  length=min(16-actualphase,size) if start==0 and actualphase else min(16,size-start)
  row=[]
  for j in range(16):
   o=start+j
   if kind=='weight':
    ctx,native=divmod(o,210);plane,offset=loc_w(native)
    valid=j<length and ctx<4
   else:
    if o<32:ctx,native=divmod(o,4)
    elif o<2080:native,ctx=divmod(o-32,8);native+=4
    else:
     pair,byte=divmod(o-2080,2);aux,ctx=divmod(pair,8);native=260+2*aux+byte
    plane,offset=loc_a(native)
    valid=j<length and bank*4<=ctx<bank*4+4 and o<size
    ctx-=bank*4
   row.append(dict(valid=valid,ctx=ctx,plane=plane,offset=offset,native=native))
  beats.append((start,row))
 pending=None;index=0;captures=[];turns=0
 while pending is not None or index<len(beats):
  turns+=1
  assert turns<2000
  old=[] if pending is None else pending[1]
  multi=False
  for p in ((0,1) if kind=='weight' else (0,)):
   shift=4 if kind=='weight' else 5
   for ctx in range(4):
    words={b['offset']>>shift for b in old if b['valid'] and b['plane']==p and b['ctx']==ctx}
    multi|=len(words)>1
  new=beats[index] if not multi and index<len(beats) else None
  rows=[old,[] if new is None else new[1]]
  consumed=[set(),set()]
  for slot,row in enumerate(rows):
   for j,b in enumerate(row):
    if b['valid'] and b['plane']==2:consumed[slot].add(j)
  for p in ((0,1) if kind=='weight' else (0,)):
   shift=4 if kind=='weight' else 5
   for ctx in range(4):
    candidates=[[j for j,b in enumerate(row) if b['valid'] and b['plane']==p and b['ctx']==ctx] for row in rows]
    selected=None
    for slot in (0,1):
     if selected is None and candidates[slot]:selected=rows[slot][candidates[slot][0]]['offset']>>shift
     if selected is not None:
      consumed[slot].update(j for j in candidates[slot] if rows[slot][j]['offset']>>shift==selected)
  if new is not None:
   remaining=[dict(b,valid=b['valid'] and j not in consumed[1]) for j,b in enumerate(new[1])]
   if any(b['valid'] for b in remaining):
    pending=(new[0],remaining)
    captures.append(dict(kind=kind,bank=bank,phase=phase,group=group,beat_offset=new[0],locations=new[1],remaining_lanes=[j for j,b in enumerate(remaining) if b['valid']]))
   else:pending=None
   index+=1
  elif pending is not None:
   remaining=[dict(b,valid=b['valid'] and j not in consumed[0]) for j,b in enumerate(old)]
   pending=(pending[0],remaining) if any(b['valid'] for b in remaining) else None
 return captures
caps={}
for bank in (0,1):
 caps[bank]=[cap for phase in range(0,16,2) for cap in replay_pending('weight',bank,phase,bank)]
 caps[bank]+=[cap for phase in (0,4,8,12) for cap in replay_pending('activation',bank,phase)]
 report['banks'][str(bank)]['finite_pending_captures']=len(caps[bank])
 scope=report['banks'][str(bank)]['scope'];rec=bits['metrics']['cond'][scope]
 pts=compiled.points('cond',definition(shape,design.hierarchy[scope],rec['checksum']),rec['width'])
 targets=[]
 for p in pts:
  if (int(rec['bits'],16)>>(rec['width']-1-p['raw_index']))&1 or p['vector']!='1' or int(p['line']) not in (91,97,346,349):continue
  line=int(p['line']);gen=dict((k,int(v)) for k,v in re.findall(r'(\w+)=(\d+)',p['spec']['generate_info']))
  j=gen.get('writer',gen.get('n',-1));byte=gen.get('byte_lane',gen.get('b',-1))
  if not 0<=j<16:continue
  kind='weight' if line in (91,346) else 'activation'
  mask=15 if line==91 else 31 if line==97 else 255
  cap=next((c for c in caps[bank] if c['kind']==kind and c['locations'][j]['offset']&mask==byte),None)
  if cap is not None:
   witness={k:v for k,v in cap.items() if k!='locations'}
   witness.update(writer=j,location=cap['locations'][j])
   targets.append(dict(raw_index=p['raw_index'],native_id=p['native_id'],vector=p['vector'],source_line=line,spec_checksum=p['attributes']['chksum'],expression=p['expression'],generate_info=p['spec']['generate_info'],finite_pending_witness=witness))
 report['banks'][str(bank)]['pending_comparison_witness_count']=len(targets)
 report['banks'][str(bank)]['pending_comparison_witnesses']=targets
report['numerical_bounds']['pending_comparison_finite_witnesses']=sum(v['pending_comparison_witness_count'] for v in report['banks'].values())

# These are source-induction candidates, not native exclusions.
for bank in (0,1):
 scope=report['banks'][str(bank)]['scope'];rec=bits['metrics']['cond'][scope]
 pts=compiled.points('cond',definition(shape,design.hierarchy[scope],rec['checksum']),rec['width'])
 exact=[]
 for point in pts:
  if (int(rec['bits'],16)>>(rec['width']-1-point['raw_index']))&1:continue
  line=int(point['line'])
  if line not in (375,378,401,403):continue
  gen=dict((k,int(v)) for k,v in re.findall(r'(\w+)=(\d+)',point['spec']['generate_info']))
  assert set(gen)=={'row','b'} and 0<=gen['row']<4
  kind='weight' if line in (375,378) else 'activation'
  assert 0<=gen['b']<(20 if kind=='weight' else 36)
  prefix='gen_side_row[%d].gen_%s_byte[%d]'%(gen['row'],kind,gen['b'])
  older='(%s_valid_i[0] && %s.older[8])'%(kind,prefix)
  ternary='(%s.use_newer ? %s.newer[7:0] : %s.older[7:0])'%(prefix,prefix,prefix)
  outer='(%s.use_newer || %s)'%(prefix,older)
  assert ((point['expression']==older and point['vector'] in ('01','11')) or
          (point['expression']==outer and point['vector']=='01') or
          (point['expression']==ternary and point['vector']=='0')),point
  exact.append([point['raw_index'],point['native_id'],point['vector'],point['attributes']['chksum'],line,gen['row'],gen['b']])
 assert len(exact)==896
 report['banks'][str(bank)]['side_induction_candidates']={
  'status':'SOURCE_PROVED_CANDIDATE_NATIVE_HOLD_NOT_APPLIED',
  'exact_count':len(exact),
  'coordinate_columns':['raw_index','compiled_cond_id_NOT_native_selector','vector','spec_checksum','source_line','row','b'],
  'coordinates':exact}
report['numerical_bounds'].update(source_induction_candidate_count=1792,
 protected_cond_points=2*21503-1792,remaining_zero_points_not_classified=9301-1792,
 scope_only_two_payload_buffers=True)
report['proof']={
 'scope':'Frozen integrated postreset QBS producer, no force/X injection; not standalone arbitrary client; no whole-module exclusion.',
 'base':'Adapter reset clears pending valid and pending strb. Registered target.valid is pending_target.valid AND pending.strb, so side hit is zero even if location flops are initially unknown.',
 'step1':'Payload source slot1 plane2 masks are consumed unconditionally whenever source_valid1 and mask are true: payload_buffer305/307. Therefore remaining1=mask1 AND NOT consumed1 has no valid plane2 bits.',
 'step2':'Adapter273..312 captures pending targets/locations and assigns pending.strb=remaining1 only on source_valid1 with nonzero remainder. Holds preserve the property; source0 remaining update only removes more bits. Clears reset pending_valid but do not introduce side strb.',
 'step3':'payload_buffer338..342 derives side_row from old mask AND registered plane2 AND row. Induction proves side_row bits0..15 allzero, hence older[8]=OR hit[15:0]=0 at356/382 (StreamWriteData1).',
 'step4':'Older conjunctions at375/401 cannot have their older operand1. enable reduces to use_newer; gated always_ff378/403 thus never evaluates its assignment with use_newer0. Exactly 4 zero condition records per side byte x(20+36)x4rowsx2banks=1792.',
 'protected':'Raw zero alone does not prove unreachable. Do not extend this induction to plane==2 or offset subexpressions without their mask, incoming slot, StreamWriteData byte_valid, read/write priority, stale unmasked locations, or other metrics.'}
report['reachable_priority']={
 'decision':'Do not launch a phase-only matrix yet. Independent finite transport model finds zero new comparator witnesses for the tested matrix; this is NOT a universal unreachable proof.',
 'tested_model':'Q6_K R4 n8 grouped ranges of840 bytes, bank0 group0 / bank1 group1, weight base phases0,2,..14; Q8_K M8 m8 packed2336 bytes phases0,4,8,12. Logical no-read load drain uses oldest selected word, slot1 blocked by old multiword, plane2 immediate consumption, registered pending capture.',
 'profile_gate':'Decoder85..150 accepts Q6_K/Q8_K, R4/M8, m8 n8 k1 destination group aligned and address base weight2/activation4 bytes. engine783..863 tagged range reader -> engine1004..1008 -> compute_engine300..317 write_ready/fire -> adapter FIFO152..159 -> pending capture273..312 -> payload merge200..305.',
 'bank_guard':'Weight bank1 is ping-pong selected via read_data_tag.weight_bank, not enabled merely by m8; engine1440..1443 toggles issue bank on lookahead_weight_range_fire. Activation bank1 uses contexts4..7 via ActivationContextBase4 and context_wave. This model separately binds the two paths.',
 'genuinely_protected_clusters':[219,223,244,255,261,262,282,285,288,340,342,374,400],
 'budget':'No simulation budget recommendation yet: no proven positive gain. Any reachable successor first needs exact pending-state/tuple witness outside already-covered matrix, host retirement/check budget and strict native expected-output oracle; no full-ISA custom-QBS fiction.',
 'dedup':'Existing gap51 Q5_K/Q2_K m2/m5, gap81 M4 phase12, gap105 Q5_K M8 phase8 have been source-scanned. All incoming comparator targets for this attempted Q6_K/M8 alignment matrix are already hit in formal731. Do not rerun gap105 or relabel its gain.',
 'software_oracle':'For a future positive-gain matrix reuse native independent QBS decoder/output/CSR/fullVRF/guard checks; Spike checks ordinary scalar transport only, never claim Spike implements QBS. No new ELF or build performed.'}
report['status']='READONLY_PAYLOAD731_STATIC1792_CANDIDATES_NO_NATIVE_QUALIFICATION'
report['EDA_started']=False
report['exclusions_applied']=False
report['RTL_changed']=False
report['pins'][str(Path(__file__).resolve())]=sha(Path(__file__).resolve())

print(json.dumps(report,separators=(',',':')))
