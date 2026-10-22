"""Host-only767 readiness gates; pending native families never imply approval."""
import json
from pathlib import Path
import report_native_batch766 as retained

life,require=retained.life,retained.require
MANIFEST=life.OUT/'qbs-payload-residual4-offline-admitted-767-agent-20261007-01/admission-manifest.json'
MANIFEST_SHA='a4dac6fb073fc665cb8f274557d04c8d2bf3ad9291a70bda03bcfdce3542b405'
PREDECESSOR=life.OUT/'native-batch-full766-offline-closure-agent-20261007-01/qualification.json'
PREDECESSOR_SHA='0ed4bbb08ea2dda3ad7b8472698d7ee7964c54db3c3dc0d150284ee40e20d5e8'


def full_or(before,after,one):
    require(len(before['tests'])==len(set(before['tests']))==766 and
        len(after['tests'])==len(set(after['tests']))==767 and after['tests'][:-1]==before['tests'] and
        one['tests']==after['tests'][-1:] and before['design']==after['design']==one['design'],
        'Exact766 prefix/new unique767/design differs')
    require(set(before['metrics'])==set(after['metrics'])==set(one['metrics']),'Metric families differ')
    count=0
    for metric,rows in before['metrics'].items():
        require(set(rows)==set(after['metrics'][metric])==set(one['metrics'][metric]),'Complete hierarchy differs')
        count+=len(rows)
        for scope,p in rows.items():
            n,s=after['metrics'][metric][scope],one['metrics'][metric][scope]
            require((p['width'],p['checksum'])==(n['width'],n['checksum'])==(s['width'],s['checksum']),
                'Compiled shape differs')
            require(int(n['bits'],16)==int(p['bits'],16)|int(s['bits'],16) and
                max(int(n['bits'],16).bit_length(),int(s['bits'],16).bit_length())<=n['width'],
                'Every-instance OR/overflow differs')
    require(count==6162,'Missing6162 compiled instances')


def stdout_gate(unit_text,out,seal,worker):
    require('StandardOutput=append:'+str(out/'service.log')+'\n' in unit_text and
        'StandardError=inherit\n' in unit_text,'Foreground stdout must bind in-directory service.log')
    require('"'+str(worker)+'" "run" "--output" "'+str(out)+'" "--seal" "'+seal+'"' in unit_text,
        'Actual systemd command/config binding differs')


def population():
    book=life.read_bound(MANIFEST,MANIFEST_SHA)
    require(book['schema']=='QBS_RESIDUAL4_HISTORICAL767_NATIVE_ADMISSION_V1' and
        book['baseline']==str(retained.MANIFEST.parent) and book['baseline_seal']==retained.MANIFEST_SHA and
        book['coverage_admitted'] is True and book['output']==str(MANIFEST.parent),'Formal767 authority differs')
    def read(name):
        p=MANIFEST.parent/name
        require(str(p) in book['output_pins'],'Unsealed767 output')
        return life.read_bound(p,book['output_pins'][str(p)])
    beforepath=retained.MANIFEST.parent/'combined-bits.json'
    require(str(beforepath) in book['input_pins'],'Unsealed766 baseline')
    before=life.read_bound(beforepath,book['input_pins'][str(beforepath)])
    after=read('combined-bits.json');full_or(before,after,read('single-bits.json'))
    status=read('status.json')
    require(status['aggregate_passed']==767 and status['exact766_prefix'] is True and
        status['full_OR_instances']==6162 and status['coverage_admitted'] is True,'767 status differs')
    inputs=MANIFEST.parent/'combined-inputs.txt'
    require(life.digest(inputs)==book['output_pins'][str(inputs)],'767 ledger bytes differ')
    ledger=inputs.read_text().splitlines()
    c=life.read_bound(retained.BASE.parent/'native-batch-full766-agent-20261007-01/config.json',
        'ce709dbf1da6a16f16c8c10e7c2006c59429a3ff08c09237a3355a7267f53650')
    require(ledger[:-1]==c['input_ledger'] and ledger==[c['input_ledger'][0],*after['tests']],
        'Exact full766 ordered ledger differs')
    q=life.read_bound(PREDECESSOR,PREDECESSOR_SHA)
    require(q['population']==766 and q['qualified_fsm_union']==173 and
        q['status']=='SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED',
        'Qualified766 predecessor required')
    return dict(status='FORMAL767_HOST_POPULATION_OR_READY_NOT_REPORT_PREPARED',population=767,
        full_OR_instances=6162,exact766prefix=True,manifest_seal=MANIFEST_SHA,
        predecessor_qualification_seal=PREDECESSOR_SHA,pending_captures_included=False,
        runtime_ready=False,EDA_launched=False,required_stdout='NEW_OUTPUT/service.log')


if __name__=='__main__':print(json.dumps(population()))
