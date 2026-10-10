"""One <=300s read-only DVE diagnostic, independent of frozen native01."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import capture_csr_reserved1193 as source

life,tools,require=source.life,source.tools,source.require
HERE=Path(__file__).resolve().parent
ORIGIN=life.OUT/'csr-reserved1193-native-agent-20261007-01'
ORIGIN_SHA='bb4624d77946b3edee17fed9dfaf2b2411c69c8169a72843f31ef84345c05f36'
PROBE=HERE/'csr_reserved1193_view_probe.tcl'
PROBE_SHA='ec467512ca182610f883842d8759c4c4e12e6e961f0bc990b14c23a486e604e5'
MENU=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/gui/dve/auxx/gui/dve/preferencesCovMainMenu.tcl')


def diagnostic_hook(text):
    require(text.count('    gui_dump_common_list -id CovDetail.1\n')==1,'Fixed diagnostic boundary')
    # Preserve both actual stdout and return value; unsupported window is evidence, not a skipped row.
    return text.replace('    gui_dump_common_list -id CovDetail.1\n','''    puts "CSR1193_DUMP_BEGIN $label"
    if {[catch {gui_dump_common_list -id CovDetail.1} value]} {
        puts "CSR1193_DUMP_UNSUPPORTED $label $value"
    } else {
        puts "CSR1193_DUMP_RETURN $label $value"
    }
    puts "CSR1193_DUMP_END $label"
''')


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh independent probe output')
    original=life.read_bound(ORIGIN/'config.json',ORIGIN_SHA);life.check(original['pins'])
    require(life.digest(PROBE)==PROBE_SHA,'Reviewed probe source differs')
    tools.revalidate(original['identity'])
    menu=MENU.read_text()
    require('gui_eval_and_log_cmd gui_cov_tgl_compress -id $window -opt $opt' in menu and
            'gui_cov_tgl_expand "uncompress"' in menu,'Installed explicit uncompress evidence')
    pins=life.merge_pins(original['pins'],{str(ORIGIN/'config.json'):ORIGIN_SHA,str(PROBE):PROBE_SHA})
    for p in (Path(__file__).resolve(),HERE/'test_run_csr_reserved1193_probe.py',MENU):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    out.mkdir()
    for name,text in [('selection.tcl',(ORIGIN/'selection.tcl').read_text()),
                      ('probe.tcl',diagnostic_hook(PROBE.read_text()))]:
        with (out/name).open('x') as f:f.write(text)
        pins[str(out/name)]=life.digest(out/name)
    c=dict(output=str(out),pins=pins,identity=original['identity'],timeout_seconds=300,
           origin_config_sha=ORIGIN_SHA,automatic_retry=False,exclusions_allowed=False,
           objects=['dcache_q[63:0]','mstatus_q.uxl[1:0]'],official_percentage=None)
    life.check(pins);life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins))),flush=True)


def run(out,seal):
    c=life.read_bound(out/'config.json',seal)
    require(c['output']==str(out) and c['timeout_seconds']==300 and c['exclusions_allowed'] is False and
            c['origin_config_sha']==ORIGIN_SHA and not (out/'execution.json').exists(),'Fixed one-shot diagnostic contract')
    life.check(c['pins']);tools.revalidate(c['identity'])
    env=tools.controlled_environment(c['identity'],os.environ);env.pop('DVE',None)
    env['DVE_COVERAGE_OUTPUT']=str(out)
    command=tools.launch_command(c['identity'],out/'probe.tcl')
    life.save(out/'execution.json',dict(command=command,cwd=str(out),timeout_seconds=300,automatic_retry=False))
    live=[];timeout=False;returncode=None;error=None
    try:
        with (out/'launcher.log').open('x') as stream:
            process=subprocess.Popen(command,cwd=out,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            launch=tools.process_info(process.pid);started=time.monotonic()
            time.sleep(10)
            for p in Path('/proc').iterdir():
                if not p.name.isdigit():continue
                try:
                    if (p/'exe').resolve()==Path(c['identity']['executable']) and (p/'cwd').resolve()==out:
                        live.append(tools.verify_live_executable(int(p.name),c['identity'],process.pid,launch['starttime']))
                except (FileNotFoundError,PermissionError):continue
            life.save(out/'live-identity.json',live)
            print(json.dumps(dict(actual_dve=live)),flush=True)
            try:process.wait(timeout=max(1,300-(time.monotonic()-started)))
            except subprocess.TimeoutExpired:
                timeout=True;os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            returncode=process.returncode
        life.check(c['pins']);tools.revalidate(c['identity'])
    except Exception as exc:
        error=str(exc)
        if 'process' in locals() and process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            returncode=process.returncode
        raise
    finally:
        life.save(out/'terminal.json',dict(returncode=returncode,timeout=timeout,actual_dve=live,error=error,
                                         qualification=False,population_application=False))
        log=out/'DVEfiles/dve_gui.log'
        complete=log.is_file() and log.read_text().splitlines().count('CSR1193_READONLY_PROBE_DONE_NOT_QUALIFICATION')==1
        life.save(out/'diagnostic-result.json',dict(status='READONLY_PROBE_COMPLETE_NOT_QUALIFICATION' if
            complete and returncode==0 and not timeout and not error else 'READONLY_PROBE_INCOMPLETE_HOLD',
            original_preserved=True,source_pins_postchecked=error is None,config_seal=seal,
            output_pins={str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name!='diagnostic-result.json'}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal')
    a=p.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    else:require(a.seal,'Config seal');run(out,a.seal)
