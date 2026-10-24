"""Separate layout-repair micro-ops from actual QBACC commands, fail closed."""
import csv
import io

from run_qbacc_soc import check_probe


SHAPES=((1,1),(1,1),(3,17),(3,17),(4,32),(4,32),(5,7),(5,7),
        (8,15),(8,15),(8,16),(8,16),(4,7))


class ProjectedAllocations:
    def __init__(self,fields,rows):
        self.fields,self.rows=fields,rows

    def open(self):
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=self.fields)
        writer.writeheader();writer.writerows(self.rows);stream.seek(0)
        return stream


def check_probe_with_maintenance(log,trace):
    groups={};fields=None
    with trace.open() as stream:
        reader=csv.DictReader(stream);fields=reader.fieldnames
        for row in reader:
            word=int(row["insn"],16)
            if word&0x707f!=0x5b or not word&(1<<28):continue
            group=groups.setdefault(row["arch_seq"],dict(alloc=[],write=[]))
            if row["event"] in group:group[row["event"]].append(row)
    if len(groups)!=13 or list(map(int,groups))!=sorted(map(int,groups)):
        raise ValueError("Wrong logical QBACC request sequence")
    actual=[];maintenance_ops=0;maintenance_bytes=0;result_bytes=0
    for i,((m,n),group) in enumerate(zip(SHAPES,groups.values())):
        mixed=(i%2==1 or i==12)
        allocations=group["alloc"]
        expected=[(8+r,32) for r in range(m)] if mixed else []
        expected.append((8,m*32))
        if len(allocations)!=len(expected):
            raise ValueError("Unexpected repair or duplicate actual QBACC allocation")
        word=((m-1+8)<<25)|(11<<20)|(10<<15)|(8<<7)|0x5b
        for row,(vd,vl) in zip(allocations,expected):
            if (int(row["insn"],16),row["vd"],row["eew"],row["vl"],row["vstart"],row["use_vd"]) != \
                    (word,str(vd),"2",str(vl),"0","1"):
                raise ValueError("Repair or actual allocation geometry differs")
        maintenance_ops+=m if mixed else 0
        repair_writes={}
        command_bytes=0
        for row in group["write"]:
            source=int(row["source"]);mask=int(row["be"],16)
            if source==3:
                # operand_requester.sv maps source3 to SLDU, source4 to LDU.
                key=(int(row["addr"]),int(row["lane"]))
                if not mixed or mask!=255 or key in repair_writes:
                    raise ValueError("Invalid/duplicate SLDU layout repair write")
                repair_writes[key]=row
            elif source==4:
                command_bytes+=bin(mask).count("1")
            else:raise ValueError("Unexpected writer for a QBACC-origin request")
        expected_keys={(reg*4+w,lane) for reg in range(8,8+m) for w in range(4) for lane in range(4)} if mixed else set()
        if set(repair_writes)!=expected_keys:
            raise ValueError("Layout repair did not write exactly the actual-M register words")
        want=0 if i==12 else (m*128 if m<=4 else m*n*4)
        if command_bytes!=want:
            raise ValueError("Actual QBS commit byte count differs, or fault wrote a destination")
        maintenance_bytes+=len(repair_writes)*8;result_bytes+=command_bytes
        actual.append(allocations[-1])
    result=check_probe(log,ProjectedAllocations(fields,actual))
    result.update(logical_commands=13,maintenance_allocations=maintenance_ops,
        maintenance_vrf_bytes=maintenance_bytes,qbs_result_vrf_bytes=result_bytes,
        source3="SLDU layout repair",source4="LDU QBS commit")
    return result
