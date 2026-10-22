import importlib.util
from newscope import PREVIOUS

_spec = importlib.util.spec_from_file_location('immutable_fp_elf700', PREVIOUS/'elf.py')
_source = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_source)
disassemble, OBJDUMP, NM = _source.disassemble, _source.OBJDUMP, _source.NM
