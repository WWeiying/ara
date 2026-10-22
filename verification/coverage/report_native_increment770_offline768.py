"""Formal770 thin context with one exact offline-qualified full768 predecessor."""
import argparse
import copy
import inspect
import json
import re
from pathlib import Path
from types import FunctionType, SimpleNamespace

import report_native_increment770 as frozen
import verify_full768_observer_union_offline as closure

life,require=frozen.life,frozen.require
HERE=Path(__file__).resolve().parent
QUALIFICATION=life.OUT/'native-batch-full768-offline-closure-agent-20261007-01/qualification.json'
QUALIFICATION_SHA='29f835bb59e38bc770793849b5fc468a0d92de2578567bce0ce6ad2079569dee'
CLOSURE=QUALIFICATION.parent/'closure.json'
CLOSURE_SHA='a31cf87be8ffc0dea70cccef37ceb006c0aa64d9013442f8f7e4426e9832d78b'
MANIFEST=life.OUT/'mfpu-restart-word-boundary-offline-admitted-770-agent-20261007-01/admission-manifest.json'
MANIFEST_SHA='7f8cbc5061a61c776d008590617c8727a07ead3c87dfb762139626166d2ba80a'
FROZEN_SHA='048bb0364b50e82c7cead84de581b56314f1bcbb12f0ff222757cdd6abedf1e5'


def predecessor_gate(path,seal):
    require(path==QUALIFICATION and seal==QUALIFICATION_SHA,'Only sealed offline full768 qualification accepted')
    q=life.read_bound(path,seal);book=life.read_bound(CLOSURE,CLOSURE_SHA)
    require(book['status']=='FULL768_RETAINED_OWNER_OFFLINE_CLOSURE_PASS' and
            book['source']==str(closure.OUT) and book['config_seal']==closure.SEAL and
            book['qualification_sha256']==seal and book['source_directory_unchanged'] is True and
            book['original_failure_preserved'] is True and book['EDA_launched'] is False,
            'Exact successful offline closure required')
    require(q['status']=='SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED' and
            q['population']==768 and q['config_seal']==closure.SEAL and
            q['source_first_full_session_qualified']==sorted(closure.report.FIRST) and
            q['source_first_local_qualification_inherited'] is False and
            q['original_failure_preserved'] is True and q['EDA_replayed'] is False,
            'Full source-first offline qualification required')
    for pins in (book['input_pins'],book['external_pins'],q['input_pins'],q['output_pins'],q['offline_adapter_pins']):life.check(pins)
    receipt=life.read_bound(closure.launch.UNIT_RECEIPT,closure.launch.UNIT_RECEIPT_SHA)
    failure=json.loads((closure.OUT/'failure.json').read_bytes())
    live=json.loads((closure.OUT/'live-identity.json').read_bytes())
    body=inspect.getsource(closure.report.base.prior.old.frozen.prior.old.base.run)
    terminal=closure.terminal_evidence((closure.OUT/'service.log').read_text(),failure,live,receipt,
                                      body,q['terminal_evidence']['systemd_properties'])
    require(terminal==q['terminal_evidence']==book['terminal_evidence'],
            'Original wrapper1/native-zero evidence differs')
    reports=q['module_reports'];main='ara_tb.dut.i_ara_soc.i_system'
    require(all(main in reports[s] for s in ('raw','applied','reset','reloaded','final')) and
            reports['raw']==reports['reset']==reports['final'] and
            reports['applied']==reports['reloaded'],'Main root full five-stage parity required')
    source=life.read_bound(closure.OUT/'config.json',closure.SEAL)
    groups,proof=closure.corrected_groups(source)
    recorded=q['observer_owner_reconciliation']
    require(recorded['whole_owner_proof']==proof and recorded['unique_fields']==84 and
            len(recorded['exact_conflicts'])==168 and recorded['changed_EL_coordinates']==0 and
            recorded['partial_vector_membership_relaxed'] is False and
            recorded['full_five_stage_complement_passed'] is True,'Exact old ownership reconciliation required')
    return dict(q,observed_terminal_evidence=terminal)


def tcl_dependencies():
    files=set();active=set()
    def visit(path):
        path=path.resolve()
        require(path.parent==HERE and path.suffix=='.tcl' and path.is_file(),'Bound Tcl dependency path required')
        require(path not in active,'Cyclic Tcl source dependency')
        if path in files:return
        active.add(path);files.add(path)
        for line in path.read_text().splitlines():
            line=line.strip()
            if not line or line.startswith('#'):continue
            literal=re.fullmatch(r'source\s+\{([^{}]+\.tcl)\}',line)
            read=re.fullmatch(r'set stream \[open \{([^{}]+\.tcl)\} r\]',line)
            if literal or read:
                visit(Path((literal or read)[1]));continue
            if line.startswith(('source ', 'uplevel #0 [list source ')):
                # Historical standalone p740_session is not the full-report hook.
                legacy=(path==HERE/'apply_points740_v4.tcl' and
                        line=='source [file join $env(DVE_COVERAGE_OUTPUT) root-selection.tcl]')
                require(legacy or line in (
                    'source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]',
                    'uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]'),
                    'Unknown dynamic Tcl source; explicit binding required: '+str(path)+' '+line)
        active.remove(path)
    visit(frozen.TCL)
    return files


def dependency_pins():
    files=[Path(__file__).resolve(),HERE/'test_report_native_increment770_offline768.py',
           Path(frozen.__file__),Path(frozen.frozen.__file__),Path(closure.__file__),
           HERE/'test_verify_full768_observer_union_offline.py']
    files.extend(sorted(tcl_dependencies()))
    return frozen.frozen.base.merge({str(p):life.digest(p) for p in files},
        {str(QUALIFICATION):QUALIFICATION_SHA,str(CLOSURE):CLOSURE_SHA})


def dependency_gate(c):
    for p,sha in dependency_pins().items():
        require(c['pins'].get(p)==sha,'Offline adapter dependency pin differs: '+p)


def context():
    require(life.digest(frozen.__file__)==FROZEN_SHA,'Frozen770 source drift')
    ctx=frozen.context(MANIFEST,MANIFEST_SHA)
    ctx['__file__']=__file__
    ctx['predecessor_gate']=predecessor_gate
    rawprivate=ctx['private_namespace'];rawfamilies=ctx['new_families']

    def private():
        inner=rawprivate();rawrecords=inner['records'];rawhost=inner['host_hook']
        # Bind the proven adapter to this context's complete family registry.
        original_model=dict(inner)
        shim=SimpleNamespace(private_namespace=lambda:original_model,base=closure.report.base)
        owner=FunctionType(closure.corrected_groups.__code__,dict(closure.corrected_groups.__globals__,report=shim))
        inner['merged_observers']=lambda c:owner(c)[0]
        def records(text,c):
            template=Path(c['output'])/'combined.el'
            if not template.exists() or text==template.read_text():return rawrecords(text,c)
            env=dict(closure.export_partition.__globals__,report=shim,OUT=template.parent)
            # The template partition remains the frozen field router, not this adapter.
            model=dict(inner,records=rawrecords)
            env['report']=SimpleNamespace(private_namespace=lambda:model,base=closure.report.base)
            parser=FunctionType(closure.export_partition.__code__,env)
            return FunctionType(rawrecords.__code__,dict(rawrecords.__globals__,partition=parser))(text,c)
        def audit(out,c):
            closure.report.base.prior.audit_observers(out,dict(c,observer_captures=owner(c)[0]))
        inner.update(records=records,audit_observers=audit)
        inner['host_hook']=lambda selection,c:rawhost(selection,dict(c,observer_captures=owner(c)[0]))
        check=inner['check']
        def bound_check(out,seal):
            dependency_gate(life.read_bound(out/'config.json',seal))
            c=FunctionType(check.__code__,inner)(out,seal)
            require(c['predecessor_full_qualification']==dict(path=str(QUALIFICATION),seal=QUALIFICATION_SHA),
                    'Offline predecessor binding differs')
            predecessor_gate(QUALIFICATION,QUALIFICATION_SHA)
            dependency_gate(c)
            return c
        inner['check']=bound_check
        return inner

    def families():
        result=copy.deepcopy(rawfamilies())
        result['lzc23132']['source_pins']=frozen.frozen.base.merge(
            result['lzc23132']['source_pins'],dependency_pins())
        return result
    ctx.update(private_namespace=private,new_families=families)
    body=inspect.getsource(frozen.frozen.prepare).replace('population=769','population=770')
    dependency="HERE/'test_report_native_increment769.py'"
    require(body.count(dependency)==1,'Frozen prepare dependency anchor differs')
    body=body.replace(dependency,"HERE/'test_report_native_increment770_offline768.py'")
    anchor='    body=inspect.getsource(base.prepare)\n'
    require(body.count(anchor)==1,'Frozen construction source anchor differs')
    union="combined=(BASE/'combined.el').read_text()+''.join(i['el'] for i in extra.values())"
    replacement=union.replace('extra.values()','added.values()')
    body=body.replace(anchor,anchor+'    union='+repr(union)+'\n'+
        "    require(body.count(union)==1,'Frozen EL union anchor differs')\n"+
        '    body=body.replace(union,'+repr(replacement)+')\n')
    exec(compile(body,__file__,'exec'),ctx)
    # Rebind existing prepare/namespace to the new context; no frozen source edits.
    for name in ('prepare','namespace'):ctx[name]=FunctionType(ctx[name].__code__,ctx)
    return ctx


def prepare(out):
    frozen.manifest_gate(MANIFEST,MANIFEST_SHA)
    context()['prepare'](out,QUALIFICATION,QUALIFICATION_SHA)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','verify','run'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seal');p.add_argument('--authorize-reviewed-run',action='store_true')
    p.add_argument('--authorize-source-first-full-session',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    else:
        require(a.seal,'Exact runtime config seal required')
        if a.mode=='run':frozen.frozen.inherited.authorize(a.authorize_reviewed_run,a.authorize_source_first_full_session)
        context()['namespace']()[a.mode](out,a.seal)
