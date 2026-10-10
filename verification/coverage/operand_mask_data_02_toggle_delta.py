"""Typed raw Toggle gain for already independently qualified mask02; no EDA."""
import argparse
import json
from pathlib import Path
import review_srt_radix16_child_residual as r

ADMITTED=r.OUT/'operand-mask-data-defined-policy-admitted763-agent-20261007-01'
SEAL='962d7292ff80e5fffe4fd8e8e8de00938c32dca3a92d21e179b8cf59f915200c'
SCOPE='ara_tb.dut.i_ara_soc.i_system'


def merge(union,rows):
    r.need(set(union)==set(rows),'Toggle full instance universe differs')
    gains=[]
    for scope,old in union.items():
        new=rows[scope]
        r.need((old['width'],old['checksum'])==(new['width'],new['checksum']),
               'Toggle native width/checksum differs')
        a,b=int(old['bits'],16),int(new['bits'],16)
        r.need(a.bit_length()<=old['width'] and b.bit_length()<=old['width'],'Out-of-width bitmap')
        gain=bin(b & ~a).count('1')
        if gain:gains.append(dict(scope=scope,new_raw_positions=gain))
        old['bits']=hex(a|b)
    return gains


def collect():
    admission=r.load(ADMITTED/'admission-manifest.json',SEAL)
    r.need(admission['coverage_admitted'] and admission['population']==763,'Candidate not qualified/admitted')
    pins={str(ADMITTED/'admission-manifest.json'):SEAL,str(r.CACHE):r.CACHE_SHA}
    cache=r.load(r.CACHE,r.CACHE_SHA)
    book=r.load(r.BASE/'admission-manifest.json',
        '6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5')
    baseline=r.BASE/'combined-inputs.txt';inputs=baseline.read_text().splitlines()
    old=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    r.need(r.digest(old)==cache['input_pins'][str(old)] and
           r.digest(baseline)==book['output_pins'][str(baseline)] and len(inputs)==763 and
           inputs[:742]==old.read_text().splitlines(),'Exact741-prefix/762 ledger differs')
    pins[str(old)]=r.digest(old);pins[str(baseline)]=r.digest(baseline)
    union={s:{k:n[k] for k in ('bits','width','checksum')} for s,n in cache['instances'].items()}
    def sample(vdb,allowed):
        paths=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        r.need(len(paths)==1,'Ambiguous native Toggle test')
        path=paths[0];sha=r.digest(path)
        r.need(allowed.get(str(path))==sha,'Unpinned native Toggle')
        pins[str(path)]=sha
        rows={}
        for n in r.xml(path).iter('instance_data'):
            s,value=n.get('name'),n.get('value')
            r.need(s not in rows and set(value)<={'0','1'},'Duplicate/malformed Toggle row')
            rows[s]=dict(width=len(value),checksum=n.get('chksum'),bits=hex(int(value or '0',2)))
        r.need(r.digest(path)==sha,'Native file changed')
        return rows
    for vdb in inputs[742:]:merge(union,sample(vdb,book['input_pins']))
    candidate=ADMITTED/'combined-inputs.txt'
    r.need(r.digest(candidate)==admission['output_pins'][str(candidate)],'763 ledger seal differs')
    successor=candidate.read_text().splitlines()
    r.need(successor[:-1]==inputs,'Not exact single successor')
    gains=merge(union,sample(successor[-1],admission['input_pins']))
    scoped=[n for n in gains if n['scope']==SCOPE or n['scope'].startswith(SCOPE+'.')]
    for path,sha in pins.items():r.need(r.digest(path)==sha,'Evidence drift')
    return dict(status='QUALIFIED02_VS762_RAW_TOGGLE_DELTA',baseline=762,population=763,
        new_raw_toggle_positions=sum(n['new_raw_positions'] for n in scoped),instances=scoped,
        full_instance_universe=len(union),scope=SCOPE,pins=pins,
        cache_provenance='Sealed741 OR; exact ledger prefix; rehashed21 native suffix and qualified02',
        historical741_native_files_rehashed=False,official_denominator_available=False,
        EDA_launched=False,population_or_reports_modified=False)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();r.need(args.output.parent.resolve()==r.OUT and not args.output.exists(),'Fresh output required')
    result=collect()
    result['pins'][str(Path(__file__).resolve())]=r.digest(Path(__file__).resolve())
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(seal=r.digest(args.output),new_raw_toggle_positions=result['new_raw_toggle_positions'])))
