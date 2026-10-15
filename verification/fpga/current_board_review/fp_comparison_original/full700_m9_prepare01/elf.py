"""Reuse sealed disassembly parser without rewriting its machine-code rules."""
import importlib.util
from newscope import PREVIOUS

_spec = importlib.util.spec_from_file_location('sealed_fp_elf', PREVIOUS / 'elf.py')
_old = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_old)
disassemble = _old.disassemble
