"""Exact, reversible private fixture edits; never writes a canonical input."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MAIN = ROOT/'verification/akv/reader_handoff/main.c'
ASM = ROOT/'verification/akv/reader_handoff/probe.S'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Source anchor missing/duplicated: '+old)
    return text.replace(old,new,1)


def main_edits():
    return [
        ('descriptor(access,fault ? 0 : (uintptr_t)weights);',
         'descriptor(access,(uintptr_t)weights);'),
        ('if (fault && (rh_trap_cause!=5 || rh_trap_tval!=0 ||',
         'if (fault && (rh_trap_cause!=5 || rh_trap_tval!=(uintptr_t)weights ||'),
        ('if (ordinary() || rh_trap_count!=1 || rh_trap_cause!=5 || rh_trap_tval!=0 ||',
         'if (ordinary() || rh_trap_count!=1 || rh_trap_cause!=5 || rh_trap_tval!=(uintptr_t)weights ||'),
        ('  printf("READER_HANDOFF_BEGIN',
         '  printf("READER_FAULT_TARGET address=%lx ordinal=2 response=2\\n", (unsigned long)weights);\n'
         '  printf("READER_HANDOFF_BEGIN'),
        ('traps=1 cause=5 tval=0 qbs_words=192', 'traps=1 cause=5 tval=weight_base qbs_words=192'),
    ]


def render_main(text):
    for old,new in main_edits():
        text=replace_once(text,old,new)
    return text.replace('READER_HANDOFF_', 'READER_DRAIN_')


def restore_main(text):
    text=text.replace('READER_DRAIN_', 'READER_HANDOFF_')
    for old,new in reversed(main_edits()):
        text=replace_once(text,new,old)
    return text


def render_vlsu(text, shared):
    reader='i_shared_reader.i_read_engine' if shared else 'i_qbs_engine.i_read_engine'
    declarations = ('  logic [1:0] rf_owner, rf_fire, rf_terminal;\n'
                    '  logic rf_qbs_fault, rf_stalled, rf_pending, rf_drain;\n'
                    '  logic [1:0] rf_bursts;\n')
    text=replace_once(text,'  axi_cut #(\n',declarations+'  reader_fault_cut #(\n')
    text=replace_once(text,'    .slv_resp_o(axi_resp  )\n',
        '    .slv_resp_o(axi_resp  ),\n'
        '    .owner_i(rf_owner), .fire_i(rf_fire), .terminal_i(rf_terminal),\n'
        '    .qbs_fault_i(rf_qbs_fault), .reader_stalled_i(rf_stalled),\n'
        '    .reader_pending_i(rf_pending), .reader_drain_i(rf_drain),\n'
        '    .reader_bursts_i(rf_bursts)\n')
    assignments=('  assign rf_owner = {akv_active_q, qbs_active_q};\n'
                 '  assign rf_fire = {akv_command_fire, qbs_command_fire};\n'
                 '  assign rf_terminal = {akv_terminal, qbs_terminal};\n'
                 '  assign rf_qbs_fault = qbs_fault_valid;\n'
                 f'  assign rf_stalled = {reader}.ar_stalled_q;\n'
                 f'  assign rf_pending = {reader}.fault_pending_q;\n'
                 f'  assign rf_drain = {reader}.response_drain_q;\n'
                 f'  assign rf_bursts = {reader}.burst_fifo_count_q;\n')
    return replace_once(text,'endmodule',assignments+'endmodule')
