import importlib.util
from newscope import PREP

_spec = importlib.util.spec_from_file_location('source700_model', PREP/'model.py')
_source = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_source)
CAP, BOUND, INPUT = _source.CAP, _source.BOUND, _source.INPUT
compare, require, model = _source.compare, _source.require, _source.model
