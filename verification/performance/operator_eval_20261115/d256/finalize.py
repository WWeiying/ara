#!/usr/bin/env python3
"""Successor post-link binding for GCC's exact D256 .isra symbol; never compiles.

Preserves the original failed preparation report. All actual compilation,
archived source, independent reference and checker inputs remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
sys.dont_write_bytecode=True
from contract import HERE,ROOT,OUT,REV,CC,ANCHOR,require,save,sha,verify
import elf
from expf_audit import audit


def finalize(original,host,output):
    original=original.resolve(strict=True);host=host.resolve(strict=True);output=output.absolute()
    require(original.parent==host.parent==OUT.resolve() and
        output==output.resolve() and output.parent==OUT.resolve() and
        re.fullmatch(r'operator_d256_prepare_20261115_[A-Za-z0-9_.-]+',output.name) and not output.exists(),
        'Fresh owned successor output required')
    failure=json.loads((original/'build.json').read_text());tests=json.loads((host/'result.json').read_text())
    require(failure['state']=='FAIL' and failure.get('error')=="KeyError('execute_segmented_d256')" and
        failure['schema']=='real-d256-firmware-v1' and not failure['rtl_executed'],
        'Only the documented post-link symbol-binding failure may be audited')
    require(tests['state']=='HOST_TEST_PASS_NOT_RTL' and tests['post_pins_match'] and
        not tests['failures'] and not tests['errors'] and not tests['skipped'] and
        sha(host/'source-pins.json')==tests['source_pins_sha256'] and
        sha(host/'host-tests.log')==tests['log_sha256'],'Pinned passing host proofs required')
    commands=json.loads((original/'commands.json').read_text())
    require(len(commands)==41 and all(c['returncode']==0 for c in commands) and
        sum(c['label'].startswith('compile-') for c in commands)==16 and
        sum(c['label']=='link' for c in commands)==1 and
        sum(c['label']=='objdump' for c in commands)==1,'All original commands must have succeeded')
    pins={}
    def merge(values):
        for p,h in values.items():
            require(p not in pins or pins[p]==h,'Identity conflict: '+p);pins[p]=h
    merge(failure['artifacts'])
    merge(json.loads((host/'source-pins.json').read_text()))
    reference=json.loads((original/'reference.json').read_text());merge(reference['source_pins'])
    # Original preparation failed before persisting its external compiler pin
    # inventory. Recover only dependencies whose exact expected identities are
    # already fixed in earlier reviewed toolchain inventories, never re-bless
    # an unchecked current compiler/header/library.
    tool_pins={};tool_inventories=[]
    for directory in (ANCHOR,OUT/'operator_coexist_prepare_20261115_minimal_01'):
        inventory=directory/'source-pins.json';values=json.loads(inventory.read_text())
        for p,h in values.items():
            require(p not in tool_pins or tool_pins[p]==h,'Historical toolchain inventory conflict: '+p)
            tool_pins[p]=h
        tool_inventories.append(dict(path=str(inventory),sha256=sha(inventory)))
        merge({str(inventory):sha(inventory)})
    dependencies=set()
    for dep in original.glob('*.d'):
        for raw in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):dependencies.add(Path(raw).resolve())
    for name in ('libm.a','libc.a','libgcc.a','libnosys.a','cc1','as','ld'):
        dependencies.add(Path((original/('locate-'+name+'.log')).read_text().strip()).resolve())
    dependencies.update((CC.resolve(),CC.with_name(CC.name.replace('gcc','objdump')).resolve(),Path(sys.executable).resolve()))
    external=[]
    for path in sorted(dependencies):
        if path.is_relative_to(original):
            require(str(path) in failure['artifacts'],'Unpinned original compiler input: '+str(path))
            continue
        require(not path.is_relative_to(ROOT/'software') and not path.is_relative_to(ROOT/'apps'),
                'Live SDK input forbidden')
        require(str(path) in tool_pins,'No historical identity for external dependency: '+str(path))
        merge({str(path):tool_pins[str(path)]});external.append(str(path))
    for path in (original/'build.json',host/'result.json',host/'source-pins.json',host/'host-tests.log',
                 Path(__file__).resolve(),ANCHOR/'objdump.log',ANCHOR/'attention.elf'):
        merge({str(path):sha(path)})
    verify(pins)
    image=original/'d256.elf';symbols,memory=elf.read(image)
    matches=[n for n in symbols if re.fullmatch(r'execute_segmented_d256(?:\.isra\.[0-9]+)?',n)]
    require(matches==['execute_segmented_d256.isra.0'],'Ambiguous/unexpected segmented symbol; never relax entry identity')
    names=dict(d256_full_call=2,akv_device_query=2,akv_decode_execute=2,
        d256_memory_group=1,d256_memory_pack=1,d256_memory_qk=1,d256_memory_pv=1,
        akv_attention_execute_v2_native_auto=1,execute_segmented_d256=1,
        akv_v2_compute_scores_f16_d256_panel4=1,akv_v2_update_outputs_f16_d256_online=1,
        prepare_d256_online_softmax=2,store_outputs=2)
    entries={}
    for role,count in names.items():
        symbol=matches[0] if role=='execute_segmented_d256' else role
        s=symbols[symbol];require(s['size']>0,'Empty function extent')
        entries[role]=dict(s,symbol=symbol,count=count,
            word=int.from_bytes(memory(s['address'],4),'little'))
    require(len({e['address'] for e in entries.values()})==len(entries),'Aliased entry identity')
    exp=audit(original)
    macros=(original/'inputs/fixture.h').read_text()
    values={}
    for key in ('DATA_BYTES','DATA_HASH','QUERY_HASH'):
        match=re.search(r'^#define D256_'+key+r' UINT64_C\(0x([0-9a-f]+)\)$',macros,re.M)
        require(match is not None,'Compiled fixture contract missing: '+key);values[key]=int(match[1],16)
    require(reference['result']['expected_fcsr']==tests['expected_fcsr'] and
        reference['result']['natural_flags']==tests['natural_flags'] and
        reference['result']['model_comparison']==tests['original_model_tolerance'],
        'Reference/test numerical/flags contract changed')
    require(reference['scale_bits']==0x3f800000 and reference['tokens']==17 and
        reference['query_heads']==4 and reference['capacity']==256 and
        reference['original_atol']==0.004 and reference['original_rtol']==0.002,'Original captured contract changed')
    output.mkdir()
    save(output/'binding-audit.json',dict(state='POST_LINK_BINDING_VERIFIED_NOT_RTL_ACCEPTED',
        original_report=str(original/'build.json'),original_report_sha256=sha(original/'build.json'),
        original_state_preserved='FAIL',original_error=failure['error'],
        original_elf=str(image),original_elf_sha256=sha(image),compilation_repeated=False,
        sdk_sources_modified=False,checker_modified=False,numerical_schedule_modified=False,
        resolved_symbol=matches[0],role='execute_segmented_d256',entry=entries['execute_segmented_d256'],
        all_commands_successful=len(commands),external_dependencies_anchored=external,
        historical_toolchain_inventories=tool_inventories,original_artifacts_verified=len(failure['artifacts'])))
    merge({str(output/'binding-audit.json'):sha(output/'binding-audit.json')})
    save(output/'source-pins.json',pins)
    plan=dict(cases=[dict(id='gemma3_d256_h4_kv17_segmented_memory',category='attention_boundary',
        elf=str(image),elf_sha256=sha(image),source_pins=str(output/'source-pins.json'),timeout_seconds=10800,
        checker=[str(Path(sys.executable).resolve()),'-B',str(HERE/'check.py'),'--build',str(output),
            '--log','{log}','--vector','{run}/vector.csv','--commit','{run}/commit.csv','--output','{result}'],
        plusargs=['+AKV_PERF','+AKV_SUMMARY'])])
    save(output/'run-plan.json',plan);verify(pins)
    report=dict(state='BUILT_NOT_EXECUTED',schema='real-d256-firmware-v1',target_executed=False,
        rtl_executed=False,performance_measured=False,hardware_compiled=False,old_rtl_pass_reused=False,
        sdk_commit=REV,source_pins_sha256=sha(output/'source-pins.json'),elf=str(image),elf_sha256=sha(image),
        post_pins_match=True,entries=entries,reference=reference,
        memory=dict(data_bytes=values['DATA_BYTES'],data_hash=values['DATA_HASH'],query_hash=values['QUERY_HASH']),
        scalar_expf_audit=exp,archive_native_assembly_sha256=sha(original/'archive/software/akv/src/akv_v2_attention_rvv.S'),
        dirty_asm_excluded=True,modes=['same_schedule_memory_rvv','current_sdk_segmented_akv'],
        primary_speedup_eligible=False,binding_audit=str(output/'binding-audit.json'),
        original_preparation_failure_preserved=True,compilation_repeated=False,
        host_tests=str(host/'result.json'),host_tests_run=tests['tests_run'],
        scope='Real D256 numerical/shape/path boundary only; no Resident or old RTL acceptance; explicit post-link IPA-name binding audit')
    report['artifacts']={str(p):sha(p) for p in output.iterdir() if p.is_file()}
    save(output/'build.json',report)
    print(json.dumps(dict(state=report['state'],manifest=str(output/'run-plan.json'),
        source_pins=str(output/'source-pins.json'),elf=str(image),host_tests=tests['tests_run'],
        original_failure_preserved=True,compilation_repeated=False)),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for n in ('original','host-tests','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();finalize(a.original,a.host_tests,a.output)


if __name__=='__main__':main()
