"""Exact732 native predicate prediction and independently unpacked unit-scale Q3/Q8 oracle."""
import json
import struct
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'coverage'))
import prepare_gap109_raw_gain_v2 as mapping
life, require = mapping.life, mapping.require
ROOT=life.ROOT
BASE=life.OUT/'gap109-offline-admitted-732-parent-20261006-01'
BASE_SEAL='badbcc7aad21ce6dab6c8c0eeabc7f85b2c13226bbe893a56c88995eab149794'
SCOPE=mapping.pre_scope().rsplit('.i_compute_engine',1)[0]+'.i_compute_engine.i_block_adapter_bank1.i_payload_buffer'


def fixtures(phase):
    require(type(phase) is int and phase in (0,1),'Exactly two commands')
    block=bytes([255]*32+[85]*64+[17]*8+[170]*4)+struct.pack('<H',0x3c00)
    activation=bytearray(2336)
    for context in range(8):
        native=struct.pack('<I',0x3f800000)+bytes([context+1]*256)+struct.pack('<16h',*([16*(context+1)]*16))
        for byte,value in enumerate(native):
            index=4*context+byte if byte<4 else 32+8*(byte-4)+context if byte<260 else 2080+16*((byte-260)//2)+2*context+(byte&1)
            activation[index]=value
    return block*8,bytes(activation)


def unpack_oracle(weight,activation,n):
    require(len(weight)==880 and len(activation)==2336 and n in (5,7),'Exact native storage geometry')
    contexts=[]
    for ctx in range(8):
        require(struct.unpack_from('<I',activation,4*ctx)[0]==0x3f800000,'Bounded unit activation scale')
        qs=[struct.unpack('b',activation[32+8*i+ctx:33+8*i+ctx])[0] for i in range(256)]
        for group in range(16):
            bs=struct.unpack_from('<h',activation,2080+16*group+2*ctx)[0]
            require(sum(qs[16*group:16*group+16])==bs,'Native bsum mismatch')
        contexts.append(qs)
    for row in range(8): require(struct.unpack_from('<H',weight,110*row+108)[0]==0x3c00,'Bounded unit weight scale')
    outputs=[]
    for ctx in range(5):
        for row in range(n):
            block=weight[110*row:110*(row+1)];dot=0
            for i in range(256):
                group=i//16;section=group//4;slot=group%4
                scale=((block[96+(section%2)*4+slot]>>(4*(section//2)))&15)|(((block[104+slot]>>(2*section))&3)<<4)
                scale-=32
                packet,lane=divmod(i,32)
                quant=(block[32+32*(packet//4)+lane]>>(2*(packet%4)))&3
                if not (block[lane]>>packet)&1:quant-=4
                dot+=scale*quant*contexts[ctx][i]
            require(abs(dot)<2**23,'Exact integer representability bound')
            outputs.append(struct.unpack('<I',struct.pack('<f',dot))[0])
    return dict(phase=0 if n==7 else 1,flags=0,bits=outputs)


def contract():
    pins={}
    def bound(path,sha):
        value=life.read_bound(path,sha);pins.update(life.merge_pins(pins,{str(path):sha}));return value
    manifest=bound(BASE/'admission-manifest.json',BASE_SEAL)
    bits=bound(BASE/'combined-bits.json',manifest['output_pins'][str(BASE/'combined-bits.json')])
    book=bound(BASE/'evidence-pins.json',manifest['output_pins'][str(BASE/'evidence-pins.json')])
    status=bound(BASE/'status.json',manifest['output_pins'][str(BASE/'status.json')])
    require(len(bits['tests'])==len(set(bits['tests']))==732 and status['coverage_admitted'] is True,'Formal732 required')
    build=bound(mapping.qualifier.BUILD,mapping.qualifier.BUILD_SHA)
    sources=('hardware/include/qbs_pkg.sv','hardware/src/vlsu/qbs/qbs_payload_buffer.sv',
        'hardware/src/vlsu/qbs/qbs_block_adapter.sv','hardware/src/vlsu/qbs/qbs_compute_engine.sv',
        'hardware/src/vlsu/qbs/qbs_engine.sv','hardware/src/vlsu/qbs/qbs_read_engine.sv',
        'hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv','hardware/src/vlsu/qbs/qbs_profile_decoder.sv')
    for relative in sources:
        path=ROOT/relative;require(path.resolve()==path and not path.is_symlink(),'Direct old source')
        pins.update(life.merge_pins(pins,{str(path):build[str(path)]}))
    dispatcher=life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    pins[str(dispatcher)]=build[str(ROOT/'hardware/src/ara_dispatcher.sv')]
    pins[str(ROOT/'hardware/tb/ara_commit_monitor.sv')]=build[str(ROOT/'hardware/tb/ara_commit_monitor.sv')]
    db=mapping.DESIGN/'snps/coverage/db'
    pins.update(life.merge_pins(pins,{str(db/p):h for p,h in bits['design'].items()}))
    info=db/'shape/cond.verilog.info.xml';pins[str(info)]=book[str(info)]
    checks=[n.get('chksum') for n in mapping.inventory.read_xml(info).iter('instance_data') if n.get('name')==SCOPE]
    row=bits['metrics']['cond'][SCOPE]
    require(row['width']==21503 and str(row['checksum'])=='2947893042' and checks==['2947893042'],'Exact payload metric/info')
    design=mapping.inventory.read_xml(db/'design/verilog.design.xml')
    nodes={n.get('id'):(n,d) for d in design for n in d.findall('srcinst')}
    def path(key):
        node,_=nodes[key];parent=node.get('pid');return (path(parent)+'.' if parent in nodes else '')+node.get('name')
    hierarchy={path(key):d for key,(_,d) in nodes.items()}
    shape=mapping.inventory.read_xml(db/'shape/cond.verilog.shape.xml')
    definition=mapping.inventory.definition(shape,hierarchy[SCOPE],row['checksum'])
    points=mapping.inventory.points('cond',definition,row['width']);targets=[]
    for phase,(n,wp,offset,valid,rr,count,raw0,id0) in enumerate([(7,0,328,2,3,14,11128,4628),(5,12,108,2,1,12,10348,4336)]):
        require(((wp+440+offset)%16)==0 and valid==(n-4)*110-offset,'Exact compact final beat')
        for j in range(count):
            raw=raw0+8*j;point=points[raw]
            require(point['native_id']==str(id0+3*j) and point['line']=='223' and point['vector']=='011' and
                    point['spec']['generate_info']=='slot=1,p=1,r=%d,b=%d'%(rr,2+j) and
                    point['truth_table']==dict(nrows='4',ncols='3',vecs='011101110111'),'Exact compiled leaf/table')
            require(not mapping.bit(row,raw),'Target already hit732')
            targets.append(dict(phase=phase,scope=SCOPE,metric='cond',width=row['width'],checksum=row['checksum'],
                compiled_definition_checksum=definition.get('chksum'),point=point,before_hit=False,measured_hit=None,
                transport_prediction=dict(range_bytes=(n-4)*110,range_address_mod16=(wp+440)%16,
                    beat_offset=offset,valid_bytes=valid,byte_lane=2+j,target_row=rr,native_offset=j,
                    mask=False,plane=1,row_equals=True)))
    for module in (mapping,mapping.inventory,mapping.inventory.score):
        p=Path(module.__file__).resolve();require(str(p) in book,'Unbound reused coverage parser');pins[str(p)]=book[str(p)]
    life.check(pins)
    return dict(status='GAP110_STATIC26_PREDICTIONS_NOT_MEASURED',baseline=str(BASE),baseline_seal=BASE_SEAL,
        targets=targets,pins=pins,commands=[dict(m=5,n=7,k=1,weight_mod16=0),dict(m=5,n=5,k=1,weight_mod16=12)],
        profile='Q3_KxQ8_K',weight_layout='R4_BLOCK_MAJOR',activation_layout='M8_INTERLEAVED',
        activation_mod16=4,vd=8,word=0x08b5045b,full_scalar_isa_verified=False,custom_spike_pass=False,
        coverage_admitted=False,measured_gain=None,rtl_changed=False,vcs_launched=False)
