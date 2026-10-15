"""Owned grouped-NF8 host/DUT adapter utilities."""
import importlib.util
import json
from pathlib import Path
import reference as ref
HERE=Path(__file__).resolve().parent
ANCESTOR=HERE.parents[1]/'indexed_review/sv39'
def read(path): return json.loads(Path(path).read_text())
def save(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2); stream.write('\n')
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
