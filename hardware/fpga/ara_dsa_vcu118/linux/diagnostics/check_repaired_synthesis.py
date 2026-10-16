"""Permit only the measured repaired-C2 estimates, with C1 path correspondence."""
import argparse
import csv
from collections import defaultdict
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import re
from check_dual_synthesis import canonical
from check_rebuild_reports import summary, clock_violations

C2 = 'gen_ddr2.i_dram_wrapper_c2/gen_channel_c2.i_dram/inst/'
C1 = 'i_dram_wrapper/gen_channel_c1.i_dram/inst/'


def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter='\t'))


def review_paths(directory, current):
    directory = Path(directory)
    if not re.fullmatch(r'[a-f0-9]{12}', (directory/'completed.txt').read_text().strip()):
        raise ValueError('Missing completed synthesis review')
    reviewed = (directory/'timing.rpt').read_text()
    if summary(reviewed) != summary(current) or clock_violations(reviewed) != clock_violations(current):
        raise ValueError('Review does not match current synthesis timing')
    pins = rows(directory/'pins.tsv')
    expected_pins = {'sys_clk_p': ('E12','71'), 'sys_clk_n': ('D12','71'),
                     'c2_sys_clk_p': ('AW26','41'), 'c2_sys_clk_n': ('AW27','41')}
    if len(pins)!=4 or {r['port']:(r['pin'],r['bank']) for r in pins}!=expected_pins:
        raise ValueError('Illegal/ambiguous MIG reference pin mapping')
    clocks = defaultdict(list)
    for r in rows(directory/'clocks.tsv'):
        clocks[r['clock']].append((r['source'], D(r['period'])))
    for name,pin in (('sys_clk','sys_clk_p'),('c2_sys_clk','c2_sys_clk_p')):
        if clocks[name] != [(pin,D(4))]: raise ValueError('Wrong reference clock source/period')
    for name,prefix in (('mmcm_clkout0',C2),('mmcm_clkout6',C2),
                        ('mmcm_clkout0_1',C1),('mmcm_clkout6_1',C1)):
        if len(clocks[name])!=1 or not clocks[name][0][0].startswith(prefix):
            raise ValueError('MIG clock ownership mismatch')
        if not clocks[name][0][1].is_finite() or clocks[name][0][1]<=0:
            raise ValueError('Invalid MIG period')
    for clock in ('mmcm_clkout0','mmcm_clkout6'):
        if clocks[clock][0][1]!=clocks[clock+'_1'][0][1]: raise ValueError('C1/C2 clock period mismatch')
    specs = {
        ('c2_sys_clk','c2_sys_clk'):(C2,16,D('-.062')),
        ('sys_clk','sys_clk'):(C1,16,D('-.062')),
        ('mmcm_clkout0','mmcm_clkout6'):(C2,1,D('-.173')),
        ('mmcm_clkout0_1','mmcm_clkout6_1'):(C1,1,D('-.154')),
    }
    groups=defaultdict(dict)
    for r in rows(directory/'paths.tsv'):
        pair=r['from'],r['to']
        if pair not in specs: raise ValueError('Unexpected reviewed clock pair')
        prefix,count,worst=specs[pair]
        if not all(r[k].startswith(prefix) for k in ('source','destination')):
            raise ValueError('Reviewed path leaves its MIG')
        source=r['source'][len(prefix):]; dest=r['destination'][len(prefix):]
        if dest in groups[pair]: raise ValueError('Duplicate reviewed endpoint')
        slack=D(r['slack'])
        if not slack.is_finite() or not worst-D('.001')<=slack<0:
            raise ValueError('Reviewed slack outside measured envelope')
        groups[pair][dest]=(source,slack)
    measured=clock_violations(current)
    keys={}
    for pair,(prefix,count,worst) in specs.items():
        group=groups[pair]
        if len(group)!=count or abs(min(v[1] for v in group.values())-worst)>D('.001'):
            raise ValueError('Changed reviewed endpoint inventory')
        key=('Intra Clock Table',(pair[0],),'WHS(ns)') if pair[0]==pair[1] else (
            'Inter Clock Table',pair,'WHS(ns)')
        if measured.get(key)!=(worst,D(count)): raise ValueError('Path inventory/report mismatch')
        keys[pair]=key
    for a,b in ((('c2_sys_clk','c2_sys_clk'),('sys_clk','sys_clk')),
                (('mmcm_clkout0','mmcm_clkout6'),('mmcm_clkout0_1','mmcm_clkout6_1'))):
        if {d:s for d,(s,_) in groups[a].items()}!={d:s for d,(s,_) in groups[b].items()}:
            raise ValueError('C2 paths do not correspond to C1')
    a=groups[('c2_sys_clk','c2_sys_clk')]; b=groups[('sys_clk','sys_clk')]
    if any(abs(a[d][1]-b[d][1])>D('.001') for d in a):
        raise ValueError('Reference-clock hold differs from C1')
    return {keys[('c2_sys_clk','c2_sys_clk')],keys[('mmcm_clkout0','mmcm_clkout6')]}


def check(current, baseline, directory):
    values=summary(current)
    if values[0]<0 or values[1]!=0 or values[2]!=0: raise ValueError('Synthesis setup failed')
    reviewed=review_paths(directory,current)
    old=clock_violations(baseline); new=clock_violations(current)
    counts=defaultdict(int); details=[]
    for key,(slack,count) in new.items():
        if key in reviewed:
            details.append({'group':key,'slack':str(slack),'failing':int(count),
                            'reason':'Matched C1 topology; unplaced C2 estimate, must close after routing'})
            continue
        clocks=tuple(canonical(c).replace('/gen_ethernet.i_eth_loader/','/i_eth_loader/') for c in key[1])
        normalized=(key[0],clocks,key[2])
        if normalized not in old or slack<old[normalized][0]:
            raise ValueError(f'Unreviewed new/worse group: {key}: {slack}')
        counts[normalized]+=count
        details.append({'group':key,'baseline_group':normalized,'slack':str(slack),'failing':int(count)})
    for key,count in counts.items():
        mig=all(re.fullmatch(r'pll_clk\[[0-2]\]|mmcm_clkout[0-6]',c) for c in key[1])
        if key[0]=='Inter Clock Table' or key[2]=='WPWS(ns)':
            if count>old[key][1]*(2 if mig else 1): raise ValueError('Expanded physical group')
    for offset,label in ((4,'WHS(ns)'),(8,'WPWS(ns)')):
        if sum(c for k,(_,c) in new.items() if k[2]==label)!=values[offset+2]:
            raise ValueError('Incomplete physical inventory')
    return {'passed':True,'eligible_for_implementation':True,'synthesis_timing_clean':False,
            'routed_checks_relaxed':False,'deferred':details,
            'report_sha256':hashlib.sha256(current.encode()).hexdigest()}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('current','baseline','review','output'): p.add_argument(arg,type=Path)
    a=p.parse_args()
    try:
        result=check(a.current.read_text(),a.baseline.read_text(),a.review)
    except (OSError,ValueError,KeyError) as e:
        result={'passed':False,'error':str(e)}
    a.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
