"""Exact formal736 binding for frozen generic narrowing gain. No EDA/admission."""
from pathlib import Path
import prepare_narrow_source_group_gain as prior

life,require=prior.life,prior.require
PRIOR_SHA='ace911d24dbdf0d25f2c2da27a95f5d9250bc233102048b0645807616d988ca4'
BASE=prior.OUT/'sv39-masked-offline-admitted-736-parent-20261006-01'
BASE_SEAL='a46222989c3c88436c5e2f431eaafa3b8790ffa9fa05bd65920dc695b6088784'


def adapted_source(source):
    replacements=(
        ('def inputs(qualpath,qualseal,baseline,baseseal):',
         'def inputs(qualpath,qualseal,baseline,baseseal):\n'
         '    require(baseline==EXACT_BASE and baseseal==EXACT_BASE_SEAL, "Exact sealed formal736 required")'),
        ("    state=life.read_bound(baseline/'status.json',pins[str(baseline/'status.json')])",
         "    require(len(before['tests'])==len(set(before['tests']))==736, 'Exact unique736 required')\n"
         "    state=life.read_bound(baseline/'status.json',pins[str(baseline/'status.json')])"),
        ("Path(__file__).with_name('test_prepare_narrow_source_group_gain.py')",
         "Path(__file__).with_name('test_prepare_narrow_source_group_gain_736.py'), "
         "Path(PRIOR_FILE), Path(PRIOR_FILE).with_name('test_prepare_narrow_source_group_gain.py')"))
    for old,new in replacements:
        require(source.count(old)==1 and new not in source,'Exact736 adapter source differs')
        source=source.replace(old,new,1)
    return source


def load_adapter():
    require(life.digest(Path(prior.__file__))==PRIOR_SHA,'Frozen generic gain predecessor drift')
    ns=dict(__file__=str(Path(__file__).resolve()),__name__='narrow_gain_exact736',
            EXACT_BASE=BASE,EXACT_BASE_SEAL=BASE_SEAL,PRIOR_FILE=str(Path(prior.__file__).resolve()))
    source=adapted_source(Path(prior.__file__).read_text())
    exec(compile(source,str(Path(__file__).resolve()),'exec'),ns)
    return ns


if __name__=='__main__':load_adapter()['main']()
