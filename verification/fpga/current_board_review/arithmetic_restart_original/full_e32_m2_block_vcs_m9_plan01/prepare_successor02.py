"""Bind Host02 locator-only successor, preserving the stopped Host01 unchanged."""
import argparse
import inspect
from pathlib import Path
import replay as r

source=inspect.getsource(r.prepare)
for old,new in (("'host01.json'","'host02.json'"),("'host01_process_exit.json'","'host02_process_exit.json'"),
                ("'host01.log'","'host02.log'"),("'host01_command.json'","'host02_command.json'")):
    assert old in source
    source=source.replace(old,new)
old="actual_host_pins=dict(host['pins']);common.base.verify_pins(actual_host_pins)"
new="""actual_host_pins=dict(host['pins'])
    actual_host_pins.update(read(HERE/'host02_command.json')['pins'])
    for name in ('prepare_successor02.py','host02_command.json','host_successor.diff'):
        actual_host_pins[str(HERE/name)]=sha(HERE/name)
    common.base.verify_pins(actual_host_pins)"""
assert source.count(old)==1
source=source.replace(old,new)
namespace=dict(r.__dict__)
exec(compile(source,str(Path(__file__).resolve()),'exec'),namespace)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--reserved-slots',type=int,default=0)
    parser.add_argument('--authorize-prepare',action='store_true')
    args=parser.parse_args()
    r.require(args.authorize_prepare and args.out.resolve().parent==r.HERE,'Explicit owned preparation')
    old=r.read(r.HERE/'host01_process_exit.json')
    r.require(old['returncode']==-15 and old['timed_out'] is False and old['pins_unchanged'] is True,
        'Preserved stopped Host diagnostic, not PASS')
    r.common.base.verify_pins(r.read(r.HERE/'host01_command.json')['pins'])
    namespace['prepare'](args.image.resolve(),args.out.resolve(),args.reserved_slots)
