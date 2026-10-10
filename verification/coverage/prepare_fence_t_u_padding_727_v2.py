"""Exact pin-path scoping repair; preserve the reviewed 727 adapter."""
import inspect
from pathlib import Path
import sys
import prepare_fence_t_u_padding_727 as predecessor

PREDECESSOR_SHA = '6eaa096ad5b24980676737ef3ca5c2a831deed55a591d92c704a93a9333b3cc3'


def adapted():
    predecessor.old.require(
        predecessor.old.sha(Path(predecessor.__file__)) == PREDECESSOR_SHA,
        'Reviewed 727 adapter drift')
    source = inspect.getsource(predecessor.adapted)
    before = 'pin(Path(old.__file__),SOURCE_SHA)'
    after = """pin(ROOT/'verification/coverage/prepare_fence_t_u_padding_static.py',SOURCE_SHA)
    pin(ROOT/'verification/coverage/prepare_fence_t_u_padding_727.py','6eaa096ad5b24980676737ef3ca5c2a831deed55a591d92c704a93a9333b3cc3')
    pin(ROOT/'verification/coverage/test_prepare_fence_t_u_padding_727.py')
    pin(ROOT/'verification/coverage/test_prepare_fence_t_u_padding_727_v2.py')
    pin(ROOT/'verification/coverage/fence_t_u_padding_727_review.txt')"""
    predecessor.old.require(source.count(before) == 1, 'Exact scoping repair boundary differs')
    namespace = dict(predecessor.__dict__, PREDECESSOR_SHA=PREDECESSOR_SHA,
                     __file__=__file__)
    exec(compile(source.replace(before, after), __file__ + ':pin-scope-only', 'exec'), namespace)
    return namespace['adapted']()


if __name__ == '__main__':
    predecessor.old.require(len(sys.argv) == 2, 'Only fresh review output argument allowed')
    adapted()(Path(sys.argv[1]).absolute())
