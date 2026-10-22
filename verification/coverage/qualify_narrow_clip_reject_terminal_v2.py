"""Source-pinned clip17 terminal successor; no EDA, bitmap union or admission."""
import hashlib
import math
from pathlib import Path

import qualify_narrow_clip_reject_terminal as prior
import run_narrow_clip_reject_simulation as runner
from qualify_store_fault_flush_terminal import elf_instruction

life, require = runner.life, runner.require
PRIOR = Path(prior.__file__).resolve()
PRIOR_SHA = '3295f1fad8ff7e28d6fec25ec747ce582d08f0c841bcb89a64c6827a4c81302f'
RUNNER_SHA = '4a31a0eac990dcf301ec4c836319dec8fcaff0917dda5b332b921f6bb6658b44'


def terminal(state, actual, started, record):
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and
            type(state.get('returncode')) is int and state['returncode'] == 0 and
            state.get('case') == runner.NAME and state.get('timeout') is False and
            state.get('coverage_admitted') is False and state.get('admission_performed') is False and
            state.get('terminal_oracle_verified') is False, 'Successful actual OS receipt required')
    require(actual == record and started['command'] == record['command'] and
            started['input_elf'] == str(runner.ELF) and started['elf_sha256'] == runner.ELF_SHA and
            started['image'] == str(life.IMAGE) and started['image_sha256'] == runner.IMAGE_SHA and
            type(started['pid']) is int and started['pid'] > 0 and
            started['pid'] == started['process_group'] == state['pid'] and
            started['budget_s'] == runner.BUDGET and started['foreground_lifetime'] is True and
            started['coverage_admitted'] is False, 'Startup PID/group/budget/command identity differs')
    require(type(state.get('wall_seconds')) in (float, int) and
            math.isfinite(state['wall_seconds']) and state['wall_seconds'] >= 0,
            'Invalid OS wall receipt')


def audit_retirements(rows):
    blob = runner.ELF.read_bytes()
    for row in rows:
        if row['event'] != 'retire':
            continue
        pc, word = int(row['pc'], 16), int(row['insn'], 16)
        require(word & 3 == 3 and elf_instruction(blob, pc, 4) == word,
                'Retirement opcode outside sealed no-C ELF')


def vector_exact(result, rejected, reference):
    prior.inherited.vector_exact(result, rejected, reference)
    require(result['instructions'][-1]['compared_bytes'] == 4 and result['compared_bytes'] == 4100,
            'Exact32 full registers plus four recovery bytes required')


def namespace():
    source = PRIOR.read_bytes()
    require(hashlib.sha256(source).hexdigest() == PRIOR_SHA and
            life.digest(Path(runner.__file__)) == RUNNER_SHA, 'Frozen qualification/runner drift')
    edits = [
        ("STATUS='CLIP17_TERMINAL_QUALIFICATION_PLAN_NOT_EXECUTED'",
         "STATUS='CLIP17_TERMINAL_V2_QUALIFICATION_PLAN_NOT_EXECUTED'"),
        ("    image=life.read_bound(life.PLAN,life.PLAN_SEAL)",
         "    runner.verify_prepared(run,record)\n    image=life.read_bound(life.PLAN,life.PLAN_SEAL)"),
        ("    deps=[Path(__file__).resolve(),Path(__file__).with_name('test_qualify_narrow_clip_reject_terminal.py'),",
         "    deps=[PRIOR,Path(__file__).resolve(),Path(__file__).with_name('test_qualify_narrow_clip_reject_terminal_v2.py'),Path(elf_instruction.__code__.co_filename).resolve(),"),
        ("        require(json.loads(read('manifest.json'))==record,'Executed manifest differs from prepared')",
         "        terminal(state,json.loads(read('manifest.json')),json.loads(read('started.json')),record)"),
        ("        control=lifecycle(rows,vectors,pre['symbols']);gold=observed(rows,pre['symbols'])",
         "        audit_retirements(rows)\n        control=lifecycle(rows,vectors,pre['symbols']);gold=observed(rows,pre['symbols'])"),
        ("        inherited.vector_exact(vector,control['rejected_arch_seqs'],reference)",
         "        vector_exact(vector,control['rejected_arch_seqs'],reference)"),
        ("            raw_bitmap_collected=False,rtl_changed=False,simulations_started=False,new_RTL_signoff=False)",
         "            raw_bitmap_collected=False,rtl_changed=False,simulations_started=False,new_RTL_signoff=False,\n            OS_returncode=0,terminal_source='FOREGROUND_RUNNER_OS_RETURN_RECEIPT',native_known_write_bytes=4100,\n            native_cycle_qualified=False,whole_ISA_qualified=False,official_denominator_verified=False,application_approval=False)")]
    text = source.decode()
    for old, new in edits:
        require(text.count(old) == 1, 'Exact predecessor replacement differs')
        text = text.replace(old, new)
    ns = dict(__name__='clip17_private_successor', __file__=str(Path(__file__).resolve()),
              PRIOR=PRIOR, runner=runner, terminal=terminal, audit_retirements=audit_retirements,
              vector_exact=vector_exact, elf_instruction=elf_instruction)
    exec(compile(text, str(Path(__file__).resolve()) + ':pinned-successor', 'exec'), ns)
    return ns


def main():
    namespace()['main']()


if __name__ == '__main__':
    main()
