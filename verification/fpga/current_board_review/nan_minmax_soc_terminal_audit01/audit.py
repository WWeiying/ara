"""Conditional two-CSV, single-traversal terminal audit. No DUT/reference launch."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
WORK=HERE.parent/'nan_minmax_soc_vcs_m6_plan01'
RUN=WORK/'prepared03'
SOURCE=HERE.parent/'nan_minmax_soc_prepare01'
GENERIC=Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/verification/ara_verify/trace.py')
PLAN_SHA='3b8e979de31f8b27b86f46014d7d3b6bf7cfc7ee59f4719b7d7fbac090c036ca'
NAMES=['nan_minmax_call1294','nan_minmax_call1234']
ANCHORS={
    str(RUN/'plan.json'):PLAN_SHA,
    str(WORK/'checker.py'):'af6879fd488c5b6318c424d668ef944205d3ea1adebbdd79f48cd12a74a78667',
    str(WORK/'replay.py'):'e7b61ab85a6a7b07c05a856ca2b00bdc9ac289f4337f097602420c54a4c49aa9',
    str(WORK/'host04.json'):'45258a0d42ddc464ad91ff9bc1a3fd5f74a0b804193a14c373399c6ff20b4f46',
    str(GENERIC):'b5751d25426ba78893c52359519d3b6f1df6bc9c77eb341c91cdca1ff75b506a',
}
OUT=HERE/'run01'


def require(ok,why):
    if not ok: raise ValueError(why)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def save(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def verify(pins,raws=()):
    for path,digest in pins.items():
        if Path(path) not in raws:
            require(sha(path)==digest,'Pin drift: '+path)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def modules():
    verify(ANCHORS)
    sys.path.insert(0,str(WORK))
    import replay
    return replay,load('terminal_frozen_protocol',GENERIC),load('independent_nan_observer',HERE/'observer.py')


def authorization(path,digest):
    require(path and digest and sha(path)==digest,'Actual main audit authorization SHA required')
    auth=read(path)
    require(auth['decision']=='AUTHORIZE_NAN_MAX2_TERMINAL_AUDIT_ONCE' and auth['plan_sha256']==PLAN_SHA
            and auth['auditor_ready_sha256']==sha(HERE/'READY.json') and auth['cases']==NAMES,
            'Exact main audit scope')
    verify(read(HERE/'READY.json')['pins'])
    return auth


def terminal_gate(auth):
    worker,protocol,observer=modules()
    worker.authorization_gate(PLAN_SHA,Path(auth['run_parent_review']),auth['run_parent_review_sha256'])
    require(sha(RUN/'complete.json')==auth['complete_sha256'],'Main bound whole2 terminal hash')
    terminal=read(RUN/'complete.json')
    require(terminal['status']==worker.PASS and terminal['aborted'] is False
            and terminal['pins_unchanged'] is True and terminal['retries']==0
            and terminal['plan_sha256']==PLAN_SHA,'Whole2 actual PASS required before any CSV access')
    results=[SimpleNamespace(**dict(r,artifact_dir=Path(r['artifact_dir']))) for r in terminal['results']]
    plan=read(RUN/'plan.json')
    ledger=read(Path(plan['image'])/'image.json')
    worker.terminal_gate(results,read(RUN/'replay/run.json'),threading.Event(),ledger)
    require(terminal['results']==read(RUN/'replay/summary.json'),'Actual complete/summary membership')
    require(not (RUN/'first_cause.json').exists(),'Sticky worker cause veto')
    for result in results:
        root=RUN/'replay/tests'/result.name
        require(result.artifact_dir==root and not (root/'first_cause.json').exists(),'Exact root/first-cause veto')
        child=read(root/'child_outcome.unvalidated.json')
        require(child['name']==result.name and type(child['returncode']) is int and child['returncode']==0
                and child['timed_out'] is False and child['failure_seen'] is False
                and child['architectural_acceptance'] is False and 0<=child['elapsed_s']<=5400,
                'Actual monitor rc0/no timeout/no FAIL, never inferred from classification')
        command=read(root/'command.json')
        require(command==dict(command=worker.monitor_command(root,ledger['simv'],result.name),
                              cwd=str(root/'work')) and child['command']==command['command']
                and child['cwd']==command['cwd'],'Actual monitor/private command identity')
        provenance=read(root/'child_command.provenance.json')
        require(provenance['command_sha256']==sha(root/'command.json') and provenance['command']==command,
                'Durable command provenance')
    return worker,protocol,observer,plan,terminal,results,ledger


class HashLines:
    def __init__(self,path):
        self.path=path
        self.stream=path.open('rb')
        self.hash=hashlib.sha256()
        self.bytes=0
    def __iter__(self): return self
    def __next__(self):
        line=self.stream.readline()
        if not line: raise StopIteration
        self.hash.update(line);self.bytes+=len(line)
        return line.decode('utf-8')


def identity(path):
    s=path.stat()
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def child(auth_path,auth_sha):
    require(sys.flags.optimize==0,'Assertions in mature observer must remain enabled')
    auth=authorization(auth_path,auth_sha)
    worker,protocol,observer_module,plan,terminal,results,ledger=terminal_gate(auth)
    raws=[RUN/'replay/tests'/n/'commit_trace.csv' for n in NAMES]
    pins=worker.merge_pins(plan['pins'],terminal['evidence_pins'],ANCHORS,
          {str(RUN/'complete.json'):auth['complete_sha256'],str(auth_path):auth_sha},
          read(HERE/'READY.json')['pins'])
    for p in (RUN/'launch.json',RUN/'replay/run.json',RUN/'replay/summary.json',HERE/'READY.json',
              Path(auth['run_parent_review'])):
        pins=worker.merge_pins(pins,{str(p):sha(p)})
    verify(pins,raws)
    save(OUT/'pins_pre.json',pins)
    audited=[]
    for result in results:
        root=result.artifact_dir
        case=next(c for c in plan['cases'] if c['id']==result.name)
        spec=worker.checker.specification(result.name)
        require(spec==plan['specs'][result.name],'Recomputed actual SoC ELF/PC/code specification')
        worker.common.check_artifacts(result,case,ledger)
        for p in (root/'console.log',root/'work/run.vcs.log'):
            worker.checker.console_gate(p.read_text(),result.name)
        raw=root/'commit_trace.csv'
        before=identity(raw)
        observer=observer_module.Observer(spec,SOURCE/worker.shape(result.name),protocol)
        stream=HashLines(raw)
        try:
            strict=worker.checker.retirement(observer.rows(csv.DictReader(stream)),spec)
            generic=observer.finish()
        finally:
            stream.stream.close()
        require(identity(raw)==before and stream.bytes==before[2],'Raw inode/size/time/EOF stable')
        require(stream.hash.hexdigest()==terminal['evidence_pins'][str(raw)],'Whole-file hash during sole traversal')
        generated=dict(generic=generic,strict=strict,csv_sha256=stream.hash.hexdigest())
        require(json.loads(json.dumps(generated))==read(root/'strict_original.json'),'Independent/worker full result agreement')
        require(dict(generic,status='VALID')==read(root/'trace_summary.json'),'Frozen generic protocol summary agreement')
        audited.append(dict(name=result.name,full_csv_traversals=1,raw_identity=before,
            raw_sha256=stream.hash.hexdigest(),raw_bytes=stream.bytes,generated=generated,
            independent_output_reads=observer.output_reads,csr_write_operands=observer.restores,
            independent_helper=observer.helper,observer_rows=observer.count['unmodified_delivered_rows'],
            row_delivery_unchanged=observer.before.digest()==observer.after.digest(),
            independent_oracle_result=hex(observer.result),GPR_unknown_not_default_zero=True))
    verify(pins,raws)
    save(OUT/'pins_post.json',pins)
    save(OUT/'result.json',dict(status='TWO_MAX_SOURCE_SINGLE_TERMINAL_ARCHITECTURAL_ACCEPTED_NOT_PARENT',
         cases=audited,pins_pre_post_unchanged=True,no_DUT_reference_build=True,
         full_parent_accepted=False,min_accepted=False,service_exit_inferred=False,
         source='two closed original CSVs; one traversal each; independent quiet-NaN bitwise oracle'))


def run(auth_path,auth_sha):
    auth=authorization(auth_path,auth_sha)
    terminal_gate(auth)
    require(not OUT.exists(),'Fresh once-only audit, no retries')
    OUT.mkdir()
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'child',
             '--authorization',str(auth_path),'--authorization-sha256',auth_sha]
    save(OUT/'ATTEMPT_STARTED.json',dict(command=command,timeout_s=1200,retries=0))
    start=time.monotonic();timed_out=False
    with (OUT/'audit.log').open('x') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        try: code=process.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            timed_out=True;process.kill();code=process.wait()
        save(OUT/'actual_exit_unvalidated.json',dict(returncode=code,child_pid=process.pid,
             elapsed_s=time.monotonic()-start,timed_out=timed_out,validated=False))
    if code!=0 or timed_out:
        save(OUT/'STOPPED.json',dict(status='STOPPED_FIRST_ERROR_NO_RETRY',returncode=code,
                                   timed_out=timed_out,log=str(OUT/'audit.log')))
        raise ValueError('Terminal audit did not pass; no retry')
    require(read(OUT/'pins_pre.json')==read(OUT/'pins_post.json'),'Audit pin snapshots')
    save(OUT/'TERMINAL.json',dict(status='ACCEPTED_TWO_MAX_SOURCE_SINGLES_NOT_PARENT',
         result_sha256=sha(OUT/'result.json'),actual_execution_sha256=sha(OUT/'actual_exit_unvalidated.json'),
         authorization_sha256=auth_sha,plan_sha256=PLAN_SHA,no_DUT_reference_build=True))
    print('ACCEPTED',sha(OUT/'TERMINAL.json'),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['run','child'])
    p.add_argument('--authorization',type=Path,required=True)
    p.add_argument('--authorization-sha256',required=True)
    args=p.parse_args()
    (run if args.mode=='run' else child)(args.authorization.resolve(),args.authorization_sha256)
