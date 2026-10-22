"""Strengthen the sealed offline idle-flush gate; reuse the same VPD, never VCS."""
import inspect
from pathlib import Path
from types import FunctionType
import diagnose_scalar_fpu_backpressure as predecessor

p=predecessor.p
OLD_SEAL='c27c1438d7d685ccef4b3fecb7875837697473aedd3c721f666896294315cd3e'
OUT=p.OUT/'scalar-fpu-backpressure-offline-diagnostic-771-agent-20261007-04'


def checked_wave_function():
    old=p.life.read_bound(predecessor.OUT/'diagnostic.json',OLD_SEAL)
    path=Path(predecessor.__file__).resolve()
    p.require(p.life.digest(path)==old['input_pins'][str(path)],'Sealed predecessor code identity')
    text=inspect.getsource(predecessor.wave_audit)
    before="pending is None and state==0 and valid==0 and value(before,'hold_inputs')==0,"
    after="pending is None and state==0 and valid==0 and value(before,'hold_inputs')==0 and value(before,'use_hold')==0,"
    p.require(text.count(before)==1,'Unique reviewed idle-flush gate')
    namespace=dict(predecessor.__dict__)
    exec(compile(text.replace(before,after),str(Path(__file__)), 'exec'),namespace)
    return namespace['wave_audit']


def main():
    wave=checked_wave_function()
    namespace=dict(predecessor.__dict__,OUT=OUT,wave_audit=wave,__file__=__file__)
    FunctionType(predecessor.main.__code__,namespace)()
    diagnostic=OUT/'diagnostic.json'
    pins={str(path):p.life.digest(path) for path in (
        Path(__file__).resolve(),Path(__file__).with_name('test_diagnose_scalar_fpu_backpressure_v2.py'),
        Path(predecessor.__file__).resolve(),Path(predecessor.__file__).with_name('test_diagnose_scalar_fpu_backpressure.py'),
        predecessor.OUT/'diagnostic.json',diagnostic)}
    p.require(pins[str(predecessor.OUT/'diagnostic.json')]==OLD_SEAL,'Closed predecessor seal')
    p.life.check(pins)
    p.life.save(OUT/'reviewed-consumer-binding.json',dict(status='OFFLINE_STRICT_IDLE_FLUSH_GATE_BOUND_NOT_ADMITTED',
        pins=pins,only_gate_change='idle READY&&valid0&&hold0&&use_hold0&&pendingNone; every other flush rejects',
        original_run_modified=False,simulation_repeated=False,coverage_admitted=False))
    print('BINDING',p.life.digest(OUT/'reviewed-consumer-binding.json'),flush=True)

if __name__=='__main__':main()
