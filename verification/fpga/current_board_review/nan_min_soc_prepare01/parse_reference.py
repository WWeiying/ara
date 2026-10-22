"""Single full extraction with inherited complete effect/raw-witness gates."""
import copy
from common import *
import check_reference as checker
from raw_mutations import insert_nv

def decode(line, original):
    match = checker.LINE.fullmatch(line.rstrip('\n'))
    require(match is not None, 'raw witness syntax')
    pc, encoding, tail = int(match[1],16), match[2][2:], match[3]
    row = copy.deepcopy(original)
    row.update(pc=pc, insn=encoding,
               regs={k:int(v,16) for k,v in checker.REG.findall(tail)},
               csrs={k:int(v,16) for k,v in checker.CSR.findall(tail)},
               vectors={k:int(v,16).to_bytes(128,'little').hex() for k,v in checker.VECTOR.findall(tail)},
               memory=[[int(a,16),int(v,16) if v else None] for a,v in checker.MEM.findall(tail)])
    return row


def parse(shape):
    dest = HERE/shape
    out = dest/'reference01'
    s = checker.specification(dest)
    a = read(dest/'reference01/admission.json')
    checkpins(a['pins'])
    helper_lines = {}
    oracle_lines = []
    target_pcs = {f'0x{r[0]:016x}':i for i,r in enumerate(s['helper'])}
    lbu_pc = f"0x{s['output_lbu'][0]:016x}"
    def capture(line):
        # Capture authentic effect witnesses during the only full raw scan.
        for pc, index in target_pcs.items():
            if pc in line[:48]:
                require(index not in helper_lines, 'repeated helper capture')
                helper_lines[index] = line
                break
        if lbu_pc in line[:48]:
            oracle_lines.append(line)
        return line
    raw = dest/'reference01/commits.log'
    data = checker.extract(dest, raw, capture)
    checker.validate(s, data)
    require(data['terminal']['firmware_retired'] < read(dest/'static_cost.json')['upper_instructions'],
            'actual firmware cost exceeds static bound')
    require(len(helper_lines)==21 and len(oracle_lines)==144, 'complete authentic raw witnesses')
    baseline = checker.host_negatives(s,data)
    negatives = []
    for name,index,operation in [
        ('raw_inserted_NV',11,insert_nv),
        ('raw_wrong_result',11,lambda line:checker.VECTOR.sub(
            lambda m:f'v{m[1]} 0x'+('00'*128),line,count=1)),
        ('raw_wrong_mask',5,lambda line:checker.VECTOR.sub(
            lambda m:f'v{m[1]} 0x'+('ff'*128),line,count=1)),
        ('raw_wrong_seed',1,lambda line:checker.VECTOR.sub(
            lambda m:f'v{m[1]} 0x'+('00'*128),line,count=1)),
        ('raw_wrong_input',4,lambda line:checker.VECTOR.sub(
            lambda m:f'v{m[1]} 0x'+('00'*128),line,count=1)),
        ('raw_nonzero_return_flags',13,lambda line:checker.REG.sub(
            lambda m:f'x{m[1]} 0x0000000000000010',line,count=1)),
        ('raw_missing_explicit_clear',10,lambda line:checker.CSR.sub('',line)),
        ('raw_wrong_opcode',11,lambda line:line.replace('0x14881c57','0x1c881c57')),
    ]:
        mutated = operation(helper_lines[index])
        require(mutated != helper_lines[index], 'raw mutation applied')
        bad = copy.deepcopy(data)
        bad['helper'][index] = decode(mutated,data['helper'][index])
        try:
            checker.validate(s,bad)
        except ValueError as error:
            negatives.append({'negative':name,'reason':str(error),'original_line':helper_lines[index],
                              'mutated_line':mutated})
        else:
            raise ValueError('actual raw witness negative accepted: '+name)
    for offset in (0,8,100,143):
        bad = copy.deepcopy(data)
        line = checker.REG.sub(lambda m:f'x{m[1]} 0x0000000000000000',oracle_lines[offset],count=1)
        match = checker.LINE.fullmatch(line.rstrip('\n'))
        values = checker.REG.findall(match[3])
        require(len(values)==1,'raw oracle GPR effect')
        bad['output_reads'][offset][1] = int(values[0][1],16)
        # Offset8 is already zero in canonical NaN: corrupt to a nonzero byte.
        if bad['output_reads'][offset][1] == data['output_reads'][offset][1]:
            bad['output_reads'][offset][1] ^= 1
            line = checker.REG.sub(lambda m:f'x{m[1]} 0x0000000000000001',line,count=1)
        try:
            checker.validate(s,bad)
        except ValueError as error:
            negatives.append({'negative':'raw_oracle_byte_'+str(offset),'reason':str(error),
                              'original_line':oracle_lines[offset],'mutated_line':line})
        else:
            raise ValueError('actual raw oracle negative accepted')
    save(out/'ledger.json',data)
    save(out/'raw_witness_host.json',{'status':'PASS_HOST_ACTUAL_RAW_WITNESSES','negatives':negatives,
         'baseline':baseline,'full_raw_passes':1,'witness_source':'captured in original full extraction',
         'scope':'raw-line effect decode + complete ledger validation; no repeated whole-stream extraction'})
    checkpins(a['pins'])
    save(out/'architectural_result.json',{'status':'ARCHITECTURAL_REFERENCE_ACCEPTED_BY_EXECUTOR_NOT_DUT',
         'shape':shape,'original_scope':config(shape),'target_calls':1,'helper_instructions':21,
         'full_output_oracle_bytes':144,'result':hex(config(shape)['expected']),'flags':0,'vstart':0,
         'firmware_retired':data['terminal']['firmware_retired'],'retired_total':data['retired_total'],
         'parking_retired':data['parking_retired'],'pins_pre_post_unchanged':True,
         'raw_sha256':sha(raw),'DUT_run':False,'sealed_MAX_unchanged':True})
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('shape',choices=SHAPES)
    parse(p.parse_args().shape)
