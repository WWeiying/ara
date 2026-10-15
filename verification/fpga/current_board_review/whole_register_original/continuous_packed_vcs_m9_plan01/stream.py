"""Reviewed lossless one-pass fanout copied without the old campaign globals."""
import csv
import hashlib
from types import SimpleNamespace
def need(ok, why):
    if not ok: raise ValueError(why)

def identity(path):
    s = path.stat()
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

class HashLines:
    def __init__(self,path):
        self.file = path.open('rb')
        self.digest = hashlib.sha256()
        self.eof = False
    def __iter__(self): return self
    def __next__(self):
        data = self.file.readline()
        if not data:
            self.eof = True
            raise StopIteration
        self.digest.update(data)
        return data.decode('utf-8')
    def __enter__(self): return self
    def __exit__(self,*_): self.file.close()

def one_pass(path, strict, generic, checkpoint):
    before = identity(path)
    holder = []
    class Input:
        def open(self,**kwargs):
            need(not holder, 'Second raw open refused')
            holder.append(HashLines(path))
            return holder[0]
    class Fanout:
        def __init__(self,stream):
            self.reader = csv.DictReader(stream)
            self.fieldnames = self.reader.fieldnames
            required = {'cycle','event','order','port','trans_id','pc','insn','rd','rd_wdata',
                        'mem_addr','mem_rmask','mem_wmask','mem_wdata','trap'}
            need(self.fieldnames and len(set(self.fieldnames)) == len(self.fieldnames) and
                 required.issubset(self.fieldnames), 'Lossless full RVFI columns required')
            self.count = 0
        def __iter__(self): return self
        def __next__(self):
            row = next(self.reader)
            need(None not in row and all(v is not None for v in row.values()), 'Malformed CSV field count')
            if self.count % 4096 == 0: checkpoint()
            self.count += 1
            strict.consume(row)
            return row
    # This is a private module instance; the frozen generic implementation is unchanged.
    generic.csv = SimpleNamespace(DictReader=Fanout)
    general = generic.validate_trace(Input())
    specific = strict.finish()
    checkpoint()
    need(len(holder) == 1 and holder[0].eof and identity(path) == before, 'Full EOF/immutable single traversal')
    return general,specific,holder[0].digest.hexdigest(),before
