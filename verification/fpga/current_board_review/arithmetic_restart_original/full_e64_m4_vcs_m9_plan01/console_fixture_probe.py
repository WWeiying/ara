"""Actual Builder tail AST -> actual CSV decoder -> Strict UART -> console gate."""
import ast
import csv
import inspect
import io
import time
from pathlib import Path
import checker as c
import host_records

def console_function(module):
    tree=ast.parse(Path(module.__file__).read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Builder')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='records')
    loop=method.body[-3]
    assert isinstance(loop,ast.For) and isinstance(loop.target,ast.Name) and loop.target.id=='byte'
    function=ast.FunctionDef(name='actual_console_tail',args=method.args,body=[loop],decorator_list=[])
    unit=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]))
    namespace=dict(vars(module));exec(compile(unit,str(module.__file__), 'exec'),namespace)
    return namespace['actual_console_tail'],ast.dump(loop,include_attributes=False)

def run(module):
    spec=c.specification();state=c.Strict(spec);builder=module.Builder(spec)
    # Local post-bootstrap UART component checkpoint, not a full-source result.
    state.retired=builder.order=1;state.main_entered=state.body_entered=True
    state.life.entered=state.life.boot_locked=True
    function,tail_ast=console_function(module)
    started=time.monotonic()
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=c.mature.transport.transport.FIELDS)
    writer.writeheader();writer.writerows(function(builder));stream.seek(0)
    rows=0
    for row in csv.DictReader(stream):state.consume(row);rows+=1
    text=state.console.decode('ascii');c.console_gate(text,simulator=False)
    return dict(actual_events=rows,uart_bytes=len(state.console),decoded_console=text,
        core_elapsed_s=time.monotonic()-started,source_sha256=c.sha(module.__file__),tail_AST=tail_ast,
        full_source_acceptance=False)

def main():
    began=time.monotonic();positive=run(host_records)
    assert positive['core_elapsed_s']<1 and positive['actual_events']>positive['uart_bytes']>0
    old=c.load('actual_old_bad_uart_fixture',c.HERE/'host01_source/host_records.py')
    try:run(old)
    except ValueError as error:
        assert 'marker' in str(error);negative=str(error)
    else:raise AssertionError('Actual old literal newline fixture was accepted')
    result=dict(status='PASS_ACTUAL_BUILDER_CSV_UART_COMPONENT_NOT_DUT',positive=positive,
        original_bad_builder_rejected=negative,total_including_model_image_setup_s=time.monotonic()-began)
    import replay as r
    r.durable(c.HERE/'console_fixture_probe01.json',result)
    print(result['status'],positive['core_elapsed_s'],result['total_including_model_image_setup_s'])
if __name__=='__main__':main()
