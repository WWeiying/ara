#!/usr/bin/env python3
"""Declaration-safe successor; preserve the failed probe worker and its inputs."""
from pathlib import Path
from types import FunctionType

from audit import digest,require
from matrix_fault_schedule import probe_bench as original_probe
import run_matrix_fault_schedule as original

FROZEN='7f55511386111949c332fc512fc676240fd5ca15d0c070b4c26e83ae0337d5bf'


def probe_bench(text):
    rendered=original_probe(text)
    include='  `include "matrix_replay_probe.svh"'
    end='endmodule : qbs_engine_tb'
    require(rendered.count(include)==rendered.count(end)==1,'Probe placement anchors')
    # VCS resolves unqualified procedural names in declaration order. Keep the
    # passive observer after the bench imports, declarations and task bodies.
    return rendered.replace(include+'\n','',1).replace(end,include+'\n\n'+end,1)


def main():
    path=Path(original.__file__).resolve()
    require(digest(path)==FROZEN,'Frozen first worker changed')
    namespace=dict(original.main.__globals__,probe_bench=probe_bench,__file__=__file__)
    successor=FunctionType(original.main.__code__,namespace,original.main.__name__)
    try:successor()
    finally:require(digest(path)==FROZEN,'Frozen first worker changed during execution')


if __name__=='__main__':main()
