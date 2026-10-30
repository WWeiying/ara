"""Independent expected geometry for real twelve-head multioutput QK inquiry."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    kind: int
    kv_head: int
    first_q: int
    m: int
    first_token: int
    n: int

    @property
    def weight_row_bytes(self):
        return 72 if self.kind else 136

    @property
    def payload_bytes(self):
        return 16 + 136*self.m + self.weight_row_bytes*self.n

    @property
    def read_ranges(self):
        return 1 + 4*self.m + 4*self.n

    @property
    def outputs(self):
        return self.m*self.n

    def key_range(self, column):
        if not 0 <= column < self.n:
            raise ValueError('Output column outside command')
        start = (self.kv_head*256+self.first_token+column)*self.weight_row_bytes
        return start,start+self.weight_row_bytes


def sequence():
    result = []
    for kind in range(2):
        for kv_head in range(2):
            for start,m in ((0,4),(4,2)):
                for token in (0,32,64,96):
                    result.append(Command(kind,kv_head,kv_head*6+start,m,token,32))
            result.append(Command(kind,kv_head,kv_head*6+4,2,32,31))
            result.append(Command(kind,kv_head,kv_head*6,4,64,1))
    return tuple(result)


def expected():
    commands = sequence()
    return dict(commands=len(commands),outputs=sum(c.outputs for c in commands),
                query_exports=24,query_export_bytes=24*136,
                payload_bytes=sum(c.payload_bytes for c in commands),
                read_ranges=sum(c.read_ranges for c in commands),
                complete_matrix_outputs=2*12*128,extra_tail_outputs=264)
