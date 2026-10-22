"""Retain sealed generic/strict composition; bind actual source700 and diagnostics."""
import importlib.util
from pathlib import Path
import json
from newscope import *
from model import model, require
import strict

_spec = importlib.util.spec_from_file_location('immutable_checker700_composition', PREVIOUS/'checker.py')
_source = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_source)
common, read, sha = _source.common, _source.read, _source.sha
VETO = _source.VETO
source = strict
convert, protocol_gate, console_gate = _source.convert, _source.protocol_gate, _source.console_gate


def specification(elf):
    require(sha(READY)==READY_SHA and sha(elf)==read(READY)['soc_elf_sha256'],'Actual source700 READY/ELF')
    expected = read(PREP/'prepared01/source_budget_gate.json')['mapping']['call_sequence']
    require(expected==[dict(seed=g['seed'],op=g['op'],vl=g['vl'],mask=g['mode'],sticky=g['sticky'],vstart=0)
                      for g in model()['rows']],'All700 original call positions')
    return strict.specification(elf)


def artifacts(result, case, ledger, spec, validator):
    try:
        value = _source.artifacts(result,case,ledger,spec,validator)
    except strict.AuditError as error:
        from replay import durable
        durable(result.artifact_dir/'checker_firstfailure.json',error.diagnostic)
        raise
    value['scope']='Full700/699 predecessors,358400 bits/1400guards/700flags/vstarts; not full17920/Linux'
    return value
