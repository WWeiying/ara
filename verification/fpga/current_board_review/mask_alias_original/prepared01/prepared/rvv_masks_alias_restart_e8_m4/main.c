extern int ma_original_main(void);
extern void replay_text(const char *);
extern volatile unsigned long replay_case;
int main(void) { unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case=1;
replay_text("BOARD_CASE_BEGIN rvv_masks_alias_restart_e8_m4\n");
int status=ma_original_main();
if(status) { replay_text("BOARD_CASE_FAIL rvv_masks_alias_restart_e8_m4\n"); return status; }
replay_text("BOARD_CASE_PASS rvv_masks_alias_restart_e8_m4\nBOARD_REPLAY_PASS\n");
return 0;
}
