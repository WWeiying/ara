"""Prepare-only until parent approval; one frozen-image600s run, never admission."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
import build_itlb_ppn_aba as pre

life, require = pre.life, pre.require
PROBE=Path(__file__).with_name('itlb_ppn_aba_probe.tcl').resolve()
SERVICE='ara-itlb-ppn-aba792-parent-20261008-01.service'
CASE='itlb_ppn_aba792'
SCHEMA='ITLB_PPN_ABA792_FROZEN600_PREPARED_V1'


def command(elf,output):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(elf),'+TESTCASE='+CASE,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'),'+VECTOR_TRACE='+str(output/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),'-cm_name',CASE,
        '+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000','-ucli','-do',str(PROBE)]


def prepared_record(path,seal,output):
    q=life.read_bound(path,seal)
    require(q['status']=='ITLB_PPN_ABA_SPIKE_PASS_NOT_RTL' and q['baseline']==792 and
        q['baseline_seal']==pre.BASE_SHA and q['software_checks']==pre.CHECKS and
        q['trap_count']==48 and 0<q['counts']['matched_instructions']<40000 and
        q['coverage_admitted'] is False and q['VCS_launched'] is False,'Exact bounded software preflight required')
    require(output.parent==pre.OUT and output.resolve()==output and not output.exists(), 'Fresh run required')
    pre.source_contract();symbols,layout=pre.elf_contract(path.parent/'input.elf')
    require(symbols==q['symbols'] and layout==life.read_bound(path.parent/'elf-layout.json',
        q['input_pins'][str(path.parent/'elf-layout.json')]), 'ELF identity/layout differs')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['simv']==str(life.IMAGE),'Exact frozen66 image required')
    pins=life.merge_pins(q['input_pins'],image['image'])
    pins=life.merge_pins(pins,{str(path):seal,str(life.PLAN):life.PLAN_SEAL})
    import collect_itlb_ppn_aba as collect
    _,_,_,baseline_pins=collect.baseline()
    pins=life.merge_pins(life.merge_pins(pins,collect.source_layout()),baseline_pins)
    # Include recursively imported local parsers, not just the top-level driver.
    for module in tuple(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name and str(pre.ROOT/'verification') in name and Path(name).is_file():
            p=Path(name).resolve();pins=life.merge_pins(pins,{str(p):life.digest(p)})
    for p in (PROBE,Path(__file__).resolve(),Path(collect.__file__).resolve(),
              Path(__file__).with_name('test_itlb_ppn_aba_runtime.py'),collect.CONVERTER):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    return dict(schema=SCHEMA,case=CASE,output=str(output),preflight=str(path),preflight_seal=seal,
        baseline=str(pre.BASE),baseline_seal=pre.BASE_SHA,baseline_count=792,service=SERVICE,
        command=command(path.parent/'input.elf',output),timeout_s=600,wave_limit_bytes=64*1024*1024,
        pins=pins,automatic_retry=False,coverage_admitted=False,official_percentage=False,
        qualification_output=str(output.with_name(output.name+'-qualified')))


def validate(r):
    out=Path(r['output'])
    require(r['schema']==SCHEMA and r['case']==CASE and r['baseline']==str(pre.BASE) and
        r['baseline_seal']==pre.BASE_SHA and type(r['baseline_count']) is int and r['baseline_count']==792 and
        r['service']==SERVICE and type(r['timeout_s']) is int and r['timeout_s']==600 and
        r['wave_limit_bytes']==64*1024*1024 and r['automatic_retry'] is False and
        r['coverage_admitted'] is False and r['official_percentage'] is False and
        out.parent==pre.OUT and out.resolve()==out and
        r['command']==command(Path(r['preflight']).parent/'input.elf',out), 'Exact runtime contract differs')
    return out


def ownership(pid,output,cmd):
    proc=Path('/proc')/str(pid)
    evidence=dict(pid=pid,exe=os.readlink(proc/'exe'),cwd=os.readlink(proc/'cwd'),
        cgroup=(proc/'cgroup').read_text(),command=(proc/'cmdline').read_bytes().split(b'\0')[:-1],
        starttime=(proc/'stat').read_text().rsplit(')',1)[1].split()[19])
    require(Path(evidence['exe']).resolve()==life.IMAGE.resolve() and evidence['cwd']==str(output) and
            any(line.endswith('/'+SERVICE) for line in evidence['cgroup'].splitlines()) and
            evidence['command']==[s.encode() for s in cmd], 'Actual executable/cwd/service/command differs')
    evidence['command']=cmd
    return evidence


def run(path,seal):
    r=life.read_bound(path,seal);out=validate(r)
    require(not out.exists(),'No rerun/overwrite')
    pins=life.merge_pins(r['pins'],{str(path):seal});life.check(pins)
    out.mkdir();life.save(out/'manifest.json',dict(r,pins=pins));process=None
    try:
        with (out/'console.log').open('x') as log:
            process=subprocess.Popen(r['command'],cwd=out,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            # This short startup handshake is not long-simulation polling.
            identity=None
            for _ in range(20):
                try: identity=ownership(process.pid,out,r['command']);break
                except (ValueError,FileNotFoundError):
                    require(process.poll() is None,'Simulator exited before identity capture');time.sleep(0.05)
            require(identity is not None,'No actual frozen simulator ownership')
            life.save(out/'live-identity.json',dict(identity,prepared_seal=seal))
            rc=process.wait(timeout=600);require(type(rc) is int and rc==0,'Nonzero simulator exit')
        life.check(pins)
        life.save(out/'simulation-status.json',dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=rc,
            timed_out=False,pid=process.pid,prepared_seal=seal,coverage_admitted=False))
    except Exception as error:
        if process is not None and process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        life.save(out/'simulation-status.json',dict(status='HOLD_NOT_ADMITTED',reason=str(error),
            timed_out=isinstance(error,subprocess.TimeoutExpired),prepared_seal=seal,
            traceback=traceback.format_exc(),coverage_admitted=False))
        raise
    import collect_itlb_ppn_aba as collect
    collect.collect(path,seal,Path(r['qualification_output']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','check','run'])
    p.add_argument('--input',type=Path,required=True);p.add_argument('--seal',required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();path=a.input.absolute()
    if a.mode=='prepare':
        require(a.output is not None,'Output required');out=a.output.absolute()
        dest=out.with_name(out.name+'.prepared.json');require(not dest.exists(),'No prepared overwrite')
        life.save(dest,prepared_record(path,a.seal,out));print('PREPARED',dest,life.digest(dest),flush=True)
    elif a.mode=='check':
        r=life.read_bound(path,a.seal);validate(r);life.check(r['pins']);print('PREPARED_CHECK_PASS_NO_EDA',flush=True)
    else:run(path,a.seal)
