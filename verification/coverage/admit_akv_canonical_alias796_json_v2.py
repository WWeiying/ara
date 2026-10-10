"""Compare complete native records in their sealed, typed JSON representation."""
import inspect
import json
from pathlib import Path
import re
from types import FunctionType
import admit_akv_canonical_alias796 as old

life,require=old.life,old.require
OLD_SHA='35cebb56a00ba8902671c37f4bdf6fba5f2a8cf618e6668fabbd95a998e409a2'


def native_equal(actual,saved):
    return json.dumps(actual,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(saved,sort_keys=True,separators=(',',':'),allow_nan=False)


def lifecycle_equal(actual,saved):
    for name in ('starts','allocations','done'):
        require(all(type(k) is int and k>=0 and type(v['order']) is int and v['order']==k
            for k,v in actual[name].items()),'Actual integer native sequence identity')
        require(all(type(k) is str and re.fullmatch(r'0|[1-9][0-9]*',k) and type(v['order']) is int and v['order']==int(k)
            for k,v in saved[name].items()),'Saved canonical JSON native sequence identity')
    normalized=json.loads(json.dumps(actual))
    return native_equal(normalized,saved)


def evaluate():
    require(life.digest(Path(old.__file__))==OLD_SHA,'Frozen796 original source drift')
    text=inspect.getsource(old.evaluate)
    previous="arch==doc(QUAL,'lifecycle.json',q['output_pins'])"
    require(text.count(previous)==1,'Exactly one lifecycle JSON comparison replacement')
    wave="c.native_wave(QUAL/'akv-alias.vcd',model.symbols,arch)==doc(QUAL,'native-capture.json',q['output_pins'])"
    require(text.count(wave)==1,'Exactly one complete native capture JSON comparison replacement')
    text=text.replace(previous,"lifecycle_equal(arch,doc(QUAL,'lifecycle.json',q['output_pins']))")
    text=text.replace(wave,"native_equal(c.native_wave(QUAL/'akv-alias.vcd',model.symbols,arch),doc(QUAL,'native-capture.json',q['output_pins']))")
    g=dict(old.evaluate.__globals__,lifecycle_equal=lifecycle_equal,native_equal=native_equal)
    exec(compile(text,str(Path(__file__).resolve())+':exact_evaluate','exec'),g)
    products,ledger=g['evaluate']()
    files=(Path(__file__).resolve(),Path(__file__).with_name('test_admit_akv_canonical_alias796_json_v2.py').resolve())
    pins=life.merge_pins(products['evidence-pins.json'],{str(p):life.digest(p) for p in files});life.check(pins)
    products['evidence-pins.json']=pins
    products['lifecycle-serialization-audit.json']=dict(status='EXACT_COMPLETE_TYPED_JSON_LIFECYCLE_AND_NATIVE_CAPTURE_MATCH',
        source_sha256=OLD_SHA,successor_pins={str(p):life.digest(p) for p in files},
        fields_omitted=[],sequence_keys='Only canonical integer seq keys serialized to JSON string keys',
        native_ranges='Complete tuple records serialized to JSON arrays; all values and types retained',
        qualification_seal=old.Q_SHA,receipt_seal=old.RECEIPT_SHA)
    return products,ledger


if __name__=='__main__':FunctionType(old.main.__code__,dict(old.main.__globals__,evaluate=evaluate))()
