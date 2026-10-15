"""Change only the Host admission receipt, never the worker/checker/oracle."""
import argparse
import inspect
from pathlib import Path
import replay as r

source=inspect.getsource(r.prepare)
start=source.index("    host=read(HERE/'host01.json')")
end=source.index('    actual_host_pins=',start)
replacement="""    host=read(HERE/'host_composite.json')
    short=read(HERE/'host_abi_process_exit.json');old=read(HERE/'host01_process_exit.json')
    require(host['status']=='PASS_COMPOSITE_HOST_ONLY_ORIGINAL_RC1_PRESERVED' and
        host['original_full_Host_rc']==1 and host['original_tests']==32 and host['original_passed_tests']==31 and
        host['actual_short_ABI_rc']==0 and host['short_ABI_tests']==4 and host['full5985_streams']==1 and
        host['actual_abi_entry_checked'] is True and host['source_checker_builder_unchanged'] is True and
        host['full_positive_shapes']==[SHAPE] and host['full_Host_reruns']==0,
        'Explicit composite full5985 plus corrected actual-ELF ABI evidence')
    require(type(short['returncode']) is int and short['returncode']==0 and short['timeout'] is False and
        short['pins_unchanged'] is True and type(old['returncode']) is int and old['returncode']==1 and
        old['timed_out'] is False and old['pins_unchanged'] is True,'Actual old1 and new ABI0 both retained')
"""
source=source[:start]+replacement+source[end:]
source=source.replace("actual_host_pins=dict(host['pins']);common.base.verify_pins(actual_host_pins)",
    "actual_host_pins=dict(host['pins']);actual_host_pins[str(HERE/'host_composite.json')]=sha(HERE/'host_composite.json');common.base.verify_pins(actual_host_pins)")
source=source.replace("plan=dict(status='PREPARED_NOT_RUN'", "plan=dict(host_admission='COMPOSITE_OLD_FULL_HOST1_WITH_ISOLATED_TEST_ERROR_PLUS_ACTUAL_ABI0',status='PREPARED_NOT_RUN'")
namespace=dict(r.__dict__);exec(compile(source,str(Path(__file__).resolve()),'exec'),namespace)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--image',type=Path,required=True)
    p.add_argument('--reserved-slots',type=int,default=0);p.add_argument('--authorize-prepare',action='store_true');a=p.parse_args()
    r.require(a.authorize_prepare and a.out.resolve().parent==r.HERE,'Only new owned preparation')
    namespace['prepare'](a.image.resolve(),a.out.resolve(),a.reserved_slots)
