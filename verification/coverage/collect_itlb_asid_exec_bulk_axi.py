"""Offline packed AXI adapter; frozen CSR/gold/AXI transaction gates retained."""
import argparse
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace
import collect_itlb_asid_exec_bulk_csr as csr

core, life, require = csr.core, csr.life, csr.require
WIDTHS = {'addr_t':64, 'id_t':4, 'user_t':1, 'data_t':64, 'strb_t':8,
          'logic':1, 'axi_pkg::len_t':8, 'axi_pkg::size_t':3,
          'axi_pkg::burst_t':2, 'axi_pkg::cache_t':4, 'axi_pkg::prot_t':3,
          'axi_pkg::qos_t':4, 'axi_pkg::region_t':4, 'axi_pkg::atop_t':6,
          'axi_pkg::resp_t':2}
CHANNELS = {
    'AW': [('id_t','id'),('addr_t','addr'),('axi_pkg::len_t','len'),
           ('axi_pkg::size_t','size'),('axi_pkg::burst_t','burst'),('logic','lock'),
           ('axi_pkg::cache_t','cache'),('axi_pkg::prot_t','prot'),
           ('axi_pkg::qos_t','qos'),('axi_pkg::region_t','region'),
           ('axi_pkg::atop_t','atop'),('user_t','user')],
    'W': [('data_t','data'),('strb_t','strb'),('logic','last'),('user_t','user')],
    'B': [('id_t','id'),('axi_pkg::resp_t','resp'),('user_t','user')],
    'R': [('id_t','id'),('data_t','data'),('axi_pkg::resp_t','resp'),
          ('logic','last'),('user_t','user')],
}
CHANNELS['AR'] = [x for x in CHANNELS['AW'] if x[1] != 'atop']
TOPS = {'REQ': [('aw_chan_t','aw'),('logic','aw_valid'),('w_chan_t','w'),
                ('logic','w_valid'),('logic','b_ready'),('ar_chan_t','ar'),
                ('logic','ar_valid'),('logic','r_ready')],
        'RESP': [('logic','aw_ready'),('logic','ar_ready'),('logic','w_ready'),
                 ('logic','b_valid'),('b_chan_t','b'),('logic','r_valid'),('r_chan_t','r')]}


def clean(text):
    return re.sub(r'\s+', '', re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S))


def source_contract():
    book_path, book_sha = core.bulk.old.shared.SOURCE, core.bulk.old.shared.SOURCE_SHA
    book = life.read_bound(book_path, book_sha)
    rels = ('hardware/deps/axi/include/axi/typedef.svh','hardware/deps/axi/src/axi_pkg.sv',
            'hardware/src/ara_soc.sv','hardware/src/ara_system.sv','hardware/tb/ara_tb.sv',
            'hardware/deps/cva6/core/cva6.sv','hardware/tb/ara_testharness.sv')
    pins = {str(book_path):book_sha}
    for rel in rels:
        path = csr.ROOT / rel
        pins[str(path)] = book[str(path)]
    life.check(pins)
    texts = {rel: (csr.ROOT / rel).read_text() for rel in rels}
    macros = texts[rels[0]]
    for name, fields in dict(CHANNELS, **TOPS).items():
        body = re.findall(r'`define AXI_DECL_'+name+r'(?:_CHAN)?_T\([^\n]*\)\s*\\\s*struct packed\s*\{(.*?)\}',
                          macros, re.S)
        require(len(body) == 1, 'Missing/ambiguous AXI macro '+name)
        declarations = re.findall(r'([\w:]+)\s+(\w+)\s*;', body[0].replace('\\',''))
        require(declarations == fields, 'AXI packed order/types differ '+name)
    pkg = clean(texts[rels[1]])
    for typ, width in WIDTHS.items():
        if typ.startswith('axi_pkg::'):
            require('typedeflogic['+str(width-1)+':0]'+typ.split('::')[1]+';' in pkg,
                    'AXI primitive width differs '+typ)
    soc, system, tb = [clean(texts[r]) for r in rels[2:5]]
    for token in ('unsignedAxiAddrWidth=64,','unsignedAxiUserWidth=1,','unsignedAxiIdWidth=5,',
                  'localparamNrAXIMasters=1;', 'localparamAxiNarrowDataWidth=64;',
                  'localparamAxiSocIdWidth=AxiIdWidth-$clog2(NrAXIMasters);',
                  'localparamAxiCoreIdWidth=AxiSocIdWidth-1;',
                  '`AXI_TYPEDEF_ALL(ariane_axi,axi_addr_t,axi_core_id_t,axi_narrow_data_t,axi_narrow_strb_t,axi_user_t)',
                  '.ariane_axi_req_t(ariane_axi_req_t)', '.ariane_axi_resp_t(ariane_axi_resp_t)'):
        require(token in soc, 'Frozen SoC type binding differs '+token)
    for token in ('.noc_req_t(ariane_axi_req_t)', '.noc_resp_t(ariane_axi_resp_t)'):
        require(token in system, 'CVA6 actual port type differs')
    # The TB leaves address/user/ID type parameters at these frozen defaults.
    harness = clean(texts[rels[6]])
    for token in ('unsignedAxiIdWidth=5,','unsignedAxiUserWidth=1,','unsignedAxiAddrWidth=64,',
                  '.AxiIdWidth(AxiIdWidth)', '.AxiUserWidth(AxiUserWidth)', '.AxiAddrWidth(AxiAddrWidth)'):
        require(token in harness, 'Harness parameter propagation differs')
    instance = re.findall(r'ara_testharness#\((.*?)\)dut\(', tb)
    require(len(instance)==1 and not any('.'+n+'(' in instance[0] for n in
            ('AxiUserWidth','AxiIdWidth','axi_addr_t','axi_user_t','axi_id_t')) and
            '.AxiAddrWidth(AxiAddrWidth)' in instance[0] and 'localparamAxiAddrWidth=64;' in tb,
            'TB AXI type override')
    return pins


def layouts():
    result = {}
    for name, members in TOPS.items():
        flat = []
        for typ, member in members:
            if typ == 'logic':
                flat.append((member,1))
            else:
                flat.extend((member+'.'+field,WIDTHS[fieldtype])
                            for fieldtype,field in CHANNELS[member.upper()])
        total = sum(width for _,width in flat)
        require(total == (281 if name=='REQ' else 84), 'Frozen packed AXI total differs')
        offset = total
        fields = {}
        for field,width in flat:
            offset -= width
            fields[field] = (offset+width-1,offset)
        result['noc_req_o' if name=='REQ' else 'noc_resp_i'] = (total,fields)
    return result


def project(iterator):
    _, decl = next(iterator)
    decl = dict(decl)
    projections = []
    for port,(width,fields) in layouts().items():
        parent = core.support.old.CORE+'.'+port
        require(decl.get(parent,{}).get('width')==width, 'Missing/foreign packed AXI parent '+parent)
        for field,(hi,lo) in fields.items():
            full = parent+'.'+field
            code = 'SOURCE_AXI_'+port+'_'+field
            require(full not in decl and not any(d['code']==code for d in decl.values()),
                    'Ambiguous native/derived AXI child')
            decl[full] = dict(width=hi-lo+1,code=code,type='source-derived-packed-member')
            projections.append((decl[parent]['code'],width,hi,lo,code))
    yield 'declarations',decl
    for time,before,after in iterator:
        states = []
        for original in (before,after):
            state = dict(original)
            for parent,width,hi,lo,code in projections:
                bits = original.get(parent,'x'*width)
                require(len(bits)==width and set(bits)<=set('01xz'), 'Invalid packed AXI encoding')
                state[code] = bits[width-1-hi:width-lo]
            states.append(state)
        yield time,states[0],states[1]


def waveform(path):
    pins = source_contract()
    def factory(code, namespace):
        require(code is core.support.old.wave.vcd.__code__, 'Foreign waveform reader boundary')
        return lambda p: project(iter(core.support.projected_vcd(p)))
    implementation = FunctionType(core.support.old.waveform.__code__,
        dict(core.support.old.waveform.__globals__,FunctionType=factory))
    result = implementation(path)
    return dict(result, AXI_source_pins=pins, AXI_layouts=layouts(),
                derived_not_native_child_signals=True, update_encoding=core.support.source_layout())


def collect(prepared, seal, output):
    extra = source_contract()
    for path in (Path(__file__).absolute(),Path(__file__).with_name('test_collect_itlb_asid_exec_bulk_axi.py').absolute(),
                 life.OUT/'itlb-asid-exec-bulk-csr-qualified-773-agent-20261007-01/failure.json'):
        extra = life.merge_pins(extra,{str(path):life.digest(path)})
    patched_core = SimpleNamespace(**dict(core.__dict__, collect=FunctionType(core.collect.__code__,
        dict(core.collect.__globals__,waveform=waveform))))
    implementation = FunctionType(csr.collect.__code__,dict(csr.collect.__globals__,core=patched_core,
        source_pins=lambda:life.merge_pins(csr.source_pins(),extra)))
    implementation(prepared,seal,output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',type=Path,required=True)
    parser.add_argument('--seal',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    collect(args.prepared.absolute(),args.seal,args.output.absolute())
