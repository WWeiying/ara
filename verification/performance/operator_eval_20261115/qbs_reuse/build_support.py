"""Local build-only utilities derived from the pinned chain Q6 builder."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def verify(pins):
    for path,sha in pins.items():
        require(digest(path)==sha,'Source/artifact drift: '+path)


class Builder:
    def __init__(self,out):
        self.out = Path(out)
        self.pins = {}
        self.commands = []

    def pin(self,path):
        path = str(Path(path).absolute())
        sha = digest(path)
        require(path not in self.pins or self.pins[path]==sha,'Build-time drift: '+path)
        self.pins[path] = sha

    def run(self,label,argv,cwd=None):
        argv = list(map(str,argv))
        cwd = Path(cwd or self.out)
        self.commands.append(dict(label=label,argv=argv,cwd=str(cwd)))
        save(self.out/'commands.json',self.commands)
        exe = shutil.which(argv[0])
        if exe:
            self.pin(exe)
        result = subprocess.run(argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        (self.out/(label+'.log')).write_bytes(result.stdout)
        require(result.returncode==0,'Failed '+label+': '+result.stdout.decode(errors='replace')[-4000:])
        return result.stdout

    def archive(self,repo,commit,paths,destination):
        archive = self.out/(destination.name+'.tar')
        self.run(destination.name+'-archive',['git','-C',repo,'archive','--format=tar','-o',archive,commit,*paths])
        destination.mkdir(parents=True)
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                require(not Path(member.name).is_absolute() and '..' not in Path(member.name).parts and
                        (member.isfile() or member.isdir()),'Unsafe archive member')
            tar.extractall(destination)
        self.pin(archive)

    def compile(self,cc,flags,source,obj):
        dep = Path(obj).with_suffix('.d')
        label = 'compile-'+Path(obj).parent.name+'-'+Path(obj).stem
        self.run(label,[cc,*flags,'-MD','-MF',dep,'-c',source,'-o',obj])
        for name in shlex.split(dep.read_text().replace('\\\n','').split(':',1)[1]):
            self.pin(name)
        self.pin(obj)
