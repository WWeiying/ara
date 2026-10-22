"""Private function wiring for reviewed729 identity Context and immutable eight CSV fix."""
import argparse
import json
from pathlib import Path
from types import FunctionType,SimpleNamespace

import prepare_six_policy_population_729 as identity
import lzc_snapshot_eight_policy_runtime as eight
import eight_policy_csv_fix_runtime as fixed
import run_eight_policy_csv_fix as runner

SCRIPT=Path(__file__).resolve()
TEST=SCRIPT.with_name('test_eight_policy_csv_fix_729_wiring.py')
frozen,require=identity.frozen,identity.require


class Context(identity.Context):
    def source_binding(self,pins):
        result=super().source_binding(pins)
        for path in (SCRIPT,TEST):self.pin(pins,path)
        result['actual_consumer_wiring']={str(p):frozen.sha(p) for p in (SCRIPT,TEST)}
        return result


def read_six(output,seal):
    config=frozen.load_sealed(output/'config.json',seal)
    context=Context(config['admitted_base'],config['admission_manifest_sha256'],config['population'])
    context.check_config(config,output)
    return context,config


def private_module(module,**bindings):
    """Clone functions only; do not mutate original module or function globals."""
    namespace=dict(vars(module),**bindings)
    for name,value in vars(module).items():
        if name not in bindings and isinstance(value,FunctionType) and value.__module__==module.__name__:
            namespace[name]=FunctionType(value.__code__,namespace,name,value.__defaults__,value.__closure__)
    return SimpleNamespace(**namespace)


def six_backend():
    return SimpleNamespace(**dict(vars(identity),Context=Context,read_config=read_six,
                                  private=identity.base.private))


def eight_backend():
    return private_module(eight,six=six_backend())


def fixed_backend():
    immutable_dependencies=fixed.dependencies
    def dependencies():return (*immutable_dependencies(),SCRIPT,TEST,identity.SCRIPT,identity.TEST)
    return private_module(fixed,eight=eight_backend(),six=six_backend(),dependencies=dependencies)


def runner_backend():
    return private_module(runner,generic=fixed_backend(),SCRIPT=SCRIPT,TEST=TEST)


def prepare_six(output):
    return identity.prepare(output,Context(identity.ADMISSION,identity.ADMISSION_SEAL,729))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('check-six','check-eight-base','check-fixed-eight','check-launch-entry'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal',required=True)
    a=parser.parse_args();out=a.output.absolute()
    if a.mode=='check-six':context,config=read_six(out,a.seal)
    elif a.mode=='check-eight-base':context,config=eight_backend().read_config(out,a.seal)
    elif a.mode=='check-fixed-eight':context,config=fixed_backend().read_config(out,a.seal)
    else:_,context,config=runner_backend().reviewed_entry(out,a.seal)
    print(json.dumps(dict(status='CHECKED729_NO_DVE',population=config['population'],
                         admission_manifest_sha256=config['admission_manifest_sha256'])))


if __name__=='__main__':main()
