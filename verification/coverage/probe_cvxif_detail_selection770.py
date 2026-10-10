"""Prepare one readonly Line-row selection diagnostic; never native qualification."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import capture_cvxif_passive_two_scope770 as old

life,require=old.life,old.require
HERE=Path(__file__).resolve().parent
FAILED=life.OUT/'cvxif-passive-two-scope-native770-agent-20261007-02'
SEAL='e5390fb4b6f3254ad4ee49efaed29f7d16b7014da2e0c2dc99dd762dd7c18073'
MENU=old.MENU.parent/'cmenuprocs.tcl'


def decode(text):
    lines=text.splitlines(); require(lines and lines[0]=='key\tcode\tutf8hex','Diagnostic schema')
    result={}
    for line in lines[1:]:
        fields=line.split('\t'); require(len(fields)==3,'Truncated diagnostic')
        key,code,value=fields
        require(key not in result and code in ('0','1'),'Duplicate key/status')
        result[key]=dict(code=int(code),value=bytes.fromhex(value).decode('utf-8'))
    return result


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh output')
    c=old.check(FAILED,SEAL)
    terminal=json.loads((FAILED/'terminal.json').read_text())
    require(terminal['returncode']==0 and not terminal['timeout'],'Prior DVE receipt')
    require((FAILED/'error.txt').read_text().startswith('Native detail selection identity\n'),'Exact original failure')
    require((FAILED/'before_Line_0.tsv').read_text()=='path\tmeta\tname\texcluded\tcells\n','No actual row was captured')
    require('set selectedItem [lindex [lindex  $tmp 0] 0]' in MENU.read_text(),'Installed double-wrapper evidence')
    dependencies=[Path(__file__),HERE/'probe_cvxif_detail_selection770.tcl',
                  HERE/'test_probe_cvxif_detail_selection770.py',MENU,FAILED/'config.json',
                  FAILED/'terminal.json',FAILED/'error.txt',FAILED/'before_Line_0.tsv',
                  FAILED/'DVEfiles/dve_gui.log']
    pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in dependencies})
    config=dict(schema='CVXIF_ONE_LINE_ROW_READONLY_SELECTION_API_V1',timeout_seconds=60,
                scope=old.SCOPES[0], metric='Line',exclusions_allowed=False,native_qualified=False,
                launch_authorized=False,parent_review_required=True,
                hypothesis='Nested -first wrapper vs GUI handle/name; actual raw/count/flat and token lookup decide',
                **{k:c[k] for k in ('identity','design','vdb','test')})
    selection=''
    for key,value in {**{k:c[k] for k in ('design','vdb','test')},'scope':old.SCOPES[0],
                      'library':HERE/'apply_points740_v4.tcl'}.items():
        require(not any(x in str(value) for x in ('{','}','\\','\n','\x00')),'Tcl literal')
        selection+='set ::cp_'+key+' {'+str(value)+'}\n'
    entry=(HERE/'probe_cvxif_detail_selection770.tcl').read_text()
    require('gui_exclude_items' not in entry and 'gui_exclusion -' not in entry and '{*}' not in entry,'Readonly/Tcl8.4')
    r=subprocess.run(['tclsh'],input='set ::cp_test_only 1\n'+selection+entry+'\nputs SOURCE_OK\n',
                     text=True,capture_output=True,timeout=10)
    require(r.returncode==0 and not r.stderr and 'SOURCE_OK' in r.stdout,'Generated source/eval')
    out.mkdir()
    for name,text in [('selection.tcl',selection),('probe.tcl',entry)]:
        with (out/name).open('x') as f:f.write(text)
        pins[str(out/name)]=life.digest(out/name)
    config['pins']=pins;life.save(out/'config.json',config)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins),
                         generated_source_eval='PASS',EDA_launched=False,budget_seconds=60)))


def check(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins']);old.local.tools.revalidate(c['identity'])
    require(c['scope']==old.SCOPES[0] and c['metric']=='Line' and c['timeout_seconds']==60 and
            c['exclusions_allowed'] is False and c['native_qualified'] is False,'Closed readonly contract')
    return c


def verify(out,seal):
    c=check(out,seal);t=json.loads((out/'terminal.json').read_text())
    require(t['returncode']==0 and not t['timeout'] and len(t['actual_dve'])==1,'Real terminal/identity')
    require(not (out/'error.txt').exists(),'Diagnostic error')
    require((out/'DVEfiles/dve_gui.log').read_text().splitlines().count('CVXIF_ONE_ROW_READONLY_DONE')==1,'Incomplete probe')
    for name in ('before-empty.el','after-empty.el'):require((out/name).read_bytes()==b'','Nonempty EL')
    data=decode((out/'row-api.tsv').read_text())
    for key in ('original_handle','original_path','original_meta','original_name','count','first','flat','first_flat'):
        require(key in data and data[key]['code']==0,'Missing actual query '+key)
    require(data['count']['value']=='1','No selected singleton')
    life.save(out/'diagnostic-result.json',dict(status='ONE_ROW_READONLY_API_CAPTURE_NOT_QUALIFICATION',
        native_qualified=False,population_application=False,observations=data,pins=c['pins'],
        output_pins={str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('service.log','diagnostic-result.json')}))


def run(out,seal,authorized):
    require(authorized,'Parent review before EDA');c=check(out,seal)
    require(not (out/'execution.json').exists(),'No retry')
    env=old.local.tools.controlled_environment(c['identity'],os.environ)
    env.pop('DVE',None);env['DVE_COVERAGE_OUTPUT']=str(out)
    command=[c['identity']['roles']['xvfb_run'],'-a','-e',str(out/'xvfb.log'),'-s','-screen 0 1280x1024x24',
             c['identity']['roles']['launcher'],'-full64','-cov','-script',str(out/'probe.tcl')]
    life.save(out/'execution.json',dict(command=command,cwd=str(out),config_seal=seal,timeout_seconds=60))
    with (out/'launcher.log').open('x') as stream:
        start=time.monotonic();p=subprocess.Popen(command,cwd=out,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        actual=[]
        while time.monotonic()-start<8 and p.poll() is None and not actual:
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit():continue
                try:
                    if (proc/'exe').resolve()==Path(c['identity']['executable']) and (proc/'cwd').resolve()==out:
                        actual.append(dict(pid=int(proc.name),exe=str((proc/'exe').resolve()),cwd=str(out)))
                except OSError:continue
            if not actual:time.sleep(.25)
        life.save(out/'live-identity.json',actual);timeout=False
        try:p.wait(timeout=max(.1,60-(time.monotonic()-start)))
        except subprocess.TimeoutExpired:
            timeout=True;os.killpg(p.pid,signal.SIGKILL);p.wait()
    life.save(out/'terminal.json',dict(returncode=p.returncode,timeout=timeout,actual_dve=actual))
    verify(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','run','verify'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-reviewed',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    elif a.mode=='run':run(out,a.seal,a.parent_reviewed)
    elif a.mode=='verify':verify(out,a.seal)
    else:check(out,a.seal);print('READONLY_PROBE_CHECK_PASS_NO_EDA')
