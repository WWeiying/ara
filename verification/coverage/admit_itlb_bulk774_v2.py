"""774 successor: historical ELF ownership comes only from formal773 evidence."""
from pathlib import Path
from types import FunctionType
import admit_itlb_bulk774 as old

life, require = old.life, old.require


def historical_dedup(ledger, newhash, evidence):
    _, sealed_ledger, historical = old.core.baseline()
    require(ledger == sealed_ledger, 'Exact sealed773 ELF ledger required')
    require(all(evidence.get(p) == h for p,h in historical.items()),
            'Merged inventory lacks/conflicts with historical773 authority')
    # The unchanged fallback matches a run pathname anywhere in JSON. Candidate
    # qualification includes old paths as pins, but cannot establish their ELF.
    result = old.dedup(ledger,newhash,historical)
    require(result['ledger_members'] == 773 and result['duplicate'] is False and
            [r['vdb'] for r in result['members']] == sealed_ledger[1:] and
            all(historical.get(p) == h for p,h in result['pins'].items()),
            'Every resolved historical ELF/command must already have a formal773 pin')
    return result


def evaluate():
    implementation = FunctionType(old.evaluate.__code__,dict(old.evaluate.__globals__,dedup=historical_dedup))
    values,text = implementation()
    pins = values['evidence-pins.json']
    for path in (Path(__file__).absolute(),Path(__file__).with_name('test_admit_itlb_bulk774_v2.py').absolute()):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    values['evidence-pins.json'] = pins
    values['status.json'] = dict(values['status.json'],
        historical_ELF_authority=str(old.BASE/'admission-manifest.json'),
        historical_ELF_authority_seal=old.BASE_SHA,
        candidate_qualification_not_used_as_historical_ELF_owner=True)
    return values,text


def main():
    implementation = FunctionType(old.main.__code__,dict(old.main.__globals__,evaluate=evaluate))
    implementation()


if __name__=='__main__':main()
