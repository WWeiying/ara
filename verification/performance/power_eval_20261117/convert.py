#!/usr/bin/env python3
"""Convert a completed bounded gate capture, retaining its initial state."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess

TOOL=Path('/home/wangwy/software/synopsys/install/syn/syn/T-2022.03-SP2/bin/vcd2saif')
OUT=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
FS=dict(s=10**15,ms=10**12,us=10**9,ns=10**6,ps=1000,fs=1)


def require(ok,text):
    if not ok:
        raise ValueError(text)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def vcd_window(path):
    header=[]
    first=last=None
    definitions=False
    dumpvars=False
    snapshot_values=0
    in_snapshot=False
    with Path(path).open(errors='strict') as stream:
        for line in stream:
            value=line.strip()
            if not definitions:
                header.append(value)
                if '$enddefinitions' in value:
                    definitions=True
                continue
            if value.startswith('#'):
                tick=int(value[1:])
                require(last is None or tick>=last,'VCD time reversal')
                first=tick if first is None else first
                last=tick
                if in_snapshot:
                    raise ValueError('Unterminated initial dumpvars')
            elif value=='$dumpvars':
                require(first is not None and not dumpvars,'Missing timestamp or duplicate dumpvars')
                dumpvars=True
                in_snapshot=True
            elif in_snapshot and value=='$end':
                in_snapshot=False
            elif in_snapshot and value and not value.startswith('$'):
                snapshot_values+=1
    text=' '.join(header)
    scale=re.findall(r'\$timescale\s+(1|10|100)\s*(s|ms|us|ns|ps|fs)\s+\$end',text)
    require(len(scale)==1 and definitions,'Missing/ambiguous VCD timescale/header')
    require(dumpvars and not in_snapshot and snapshot_values>0,'No complete initial snapshot')
    require(first is not None and first>0 and last>first,'Invalid bounded VCD timestamps')
    tick_fs=int(scale[0][0])*FS[scale[0][1]]
    return dict(first_tick=first,last_tick=last,duration_ticks=last-first,
                tick_fs=tick_fs,duration_fs=(last-first)*tick_fs,
                initial_snapshot_values=snapshot_values)


def saif_summary(path,clock='clk_i',instance=('ara_tb','dut','i_ara_soc')):
    head=[]
    block=[]
    collecting=False
    depth=0
    instances=[]
    clock_depth=None
    with Path(path).open() as stream:
        for line in stream:
            if len(head)<30:
                head.append(line)
            # Track S-expression nesting without loading a multi-GB SAIF tree.
            # Quoted metadata strings must not change the parenthesis depth.
            tokens=re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',line)
            opened=re.match(r'\s*\(INSTANCE\s+([^\s()]+)\s*$',line)
            if opened:
                instances.append((depth+1,opened[1]))
            current=tuple(name for _,name in instances)
            if current==instance and re.fullmatch(r'\s*\('+re.escape(clock)+r'\s*',line):
                require(not block,'Duplicate selected clock record')
                collecting=True
                clock_depth=depth+1
            if collecting:
                block.append(line)
            depth+=sum(t=='(' for t in tokens)-sum(t==')' for t in tokens)
            require(depth>=0,'Malformed SAIF nesting')
            while instances and instances[-1][0]>depth:
                instances.pop()
            if collecting:
                if depth<clock_depth:
                    break
    text=''.join(head)
    duration=re.findall(r'\(DURATION\s+(\d+)\)',text)
    scale=re.findall(r'\(TIMESCALE\s+(1|10|100)\s+(s|ms|us|ns|ps|fs)\)',text)
    require(len(duration)==len(scale)==1,'Missing SAIF duration/scale')
    stats={k:int(v) for k,v in re.findall(r'\((T0|T1|TX|TZ|TC)\s+(\d+)\)',''.join(block))}
    require({'T0','T1','TX','TC'}<=stats.keys(),'Missing selected clock activity')
    return dict(duration_ticks=int(duration[0]),tick_fs=int(scale[0][0])*FS[scale[0][1]],
                clock=clock,clock_activity=stats)


def check_activity(vcd,saif,cycles,period_ns):
    duration_fs=int(Decimal(str(period_ns))*FS['ns']*cycles)
    require(abs(vcd['duration_fs']-duration_fs)<=vcd['tick_fs'],'Captured cycle/time mismatch')
    require(saif['duration_ticks']*saif['tick_fs']==vcd['duration_fs'],'SAIF duration mismatch')
    c=saif['clock_activity']
    require(c['TX']==c.get('TZ',0)==0,'Unknown/high-impedance capture clock')
    require(c['T0']+c['T1']==saif['duration_ticks'],'Incomplete clock observation time')
    require(abs(c['TC']-2*cycles)<=2,'Clock transitions inconsistent with requested cycles')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    capture=a.capture.resolve()
    output=a.output.resolve()
    require(output.parent==OUT and output.name.startswith('power_saif_20261117_') and
            not output.exists(),'Fresh owned conversion output required')
    receipt=json.loads(capture.read_text())
    require(receipt['state']=='CAPTURE_COMPLETE_NOT_TASK_PASS','Not a completed bounded gate capture')
    vcd,log=Path(receipt['vcd']),Path(receipt['log'])
    require(vcd.is_absolute() and log.is_absolute(),'Capture paths must be absolute')
    text=log.read_text()
    begin=re.findall(r'^GATE_ROI_BEGIN cycle=(\d+) time=(\d+)\s*$',text,re.M)
    end=re.findall(r'^GATE_CAPTURE_WINDOW_COMPLETE cycle=(\d+) time=(\d+) task_pass=0\s*$',text,re.M)
    require(len(begin)==len(end)==1,'Missing/duplicate capture completion markers')
    require((int(begin[0][0]),int(end[0][0]))==
            (receipt['first_cycle'],receipt['last_cycle']),'Capture receipt/cycle mismatch')
    require(int(end[0][1])>int(begin[0][1]),'Invalid capture log times')
    require(not re.search(r'(?mi)^\s*(?:Error[-:]|Fatal:)|Assertion failed',text),'Gate log contains error')
    pins={str(path):sha(path) for path in (capture,vcd,log,TOOL,Path(__file__).resolve())}
    for key in ('source_pins','image_pins'):
        if key in receipt:
            path=Path(receipt[key])
            require(path.is_file(),'Missing capture pin inventory')
            pins[str(path)]=sha(path)
            for name,digest in json.loads(path.read_text()).items():
                require(sha(name)==digest,'Capture image/input drift: '+name)
    window=vcd_window(vcd)
    cycles=receipt['last_cycle']-receipt['first_cycle']
    require(cycles>=1024,'Representative power window must span at least 1024 cycles')
    output.mkdir()
    saif=output/'activity.saif'
    # This converter interprets -time values in raw VCD ticks, not ns.
    # A 1-ps synthetic probe independently distinguishes the two conventions.
    argv=[str(TOOL),'-input',str(vcd),'-output',str(saif),'-instance','ara_tb.dut.i_ara_soc',
          '-time',str(window['first_tick']),str(window['last_tick'])]
    result=dict(state='FAIL',capture=str(capture),capture_sha256=sha(capture),
                command=argv,whole_task_pass=False,power_measured=False)
    try:
        with (output/'conversion.log').open('x') as stream:
            proc=subprocess.run(argv,stdout=stream,stderr=subprocess.STDOUT,timeout=1800)
        require(proc.returncode==0 and saif.is_file(),'vcd2saif failure')
        summary=saif_summary(saif)
        check_activity(window,summary,cycles,receipt['clock_period_ns'])
        for name,digest in pins.items():
            require(sha(name)==digest,'Conversion input drift: '+name)
        pins[str(saif)]=sha(saif)
        result.update(state='SAIF_CONVERSION_PASS_NOT_POWER',saif=str(saif),saif_sha256=sha(saif),
                      window=window,saif_summary=summary,source_pins=str(output/'source-pins.json'),
                      instance='ara_tb/dut/i_ara_soc',elf_sha256=receipt['elf_sha256'],
                      simv_sha256=receipt['simv_sha256'])
    except Exception as exc:
        result['error']=repr(exc)
    (output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return int(result['state']!='SAIF_CONVERSION_PASS_NOT_POWER')


if __name__=='__main__':
    raise SystemExit(main())
