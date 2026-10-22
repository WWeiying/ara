"""Load immutable shared code privately; exact AST substitutions only."""
import ast
import types
from scope import *


def module(name,filename,expressions=(),constants=(),local_file=None):
    path=SHARED/filename;tree=ast.parse(path.read_text())
    targets={ast.dump(ast.parse(a,mode='eval').body):(ast.parse(b,mode='eval').body,n)
             for a,b,n in expressions}
    seen={k:0 for k in targets};literal_counts=[0]*len(constants)
    class Change(ast.NodeTransformer):
        def visit(self,node):
            key=ast.dump(node)
            if key in targets:
                seen[key]+=1
                return ast.copy_location(targets[key][0],node)
            return super().visit(node)
        def visit_Constant(self,node):
            for i,(a,b,n) in enumerate(constants):
                if node.value==a:
                    literal_counts[i]+=1
                    return ast.copy_location(ast.Constant(value=b),node)
            return node
    tree=Change().visit(tree)
    require(all(seen[k]==v[1] for k,v in targets.items()),'Shared expression sites changed '+filename)
    require(all(literal_counts[i]==n for i,(_,_,n) in enumerate(constants)),'Shared literal sites changed '+filename)
    ast.fix_missing_locations(tree)
    m=types.ModuleType(name);m.__file__=str(local_file or path);sys.modules[name]=m
    exec(compile(tree,str(path),'exec'),m.__dict__)
    m.shared_source_path=str(path);m.shared_source_sha256=sha(path)
    return m
