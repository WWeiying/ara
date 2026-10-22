extern int fixed_main(void);
extern void replay_text(const char *);
extern volatile unsigned long replay_case;
int main(void) {
    unsigned long vlenb;
    __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
    replay_case=1;
    replay_text("BOARD_CASE_BEGIN fixed_e8_m4_pair775_776\n");
    int result=fixed_main();
    if(result) { replay_text("BOARD_CASE_FAIL fixed_e8_m4_pair775_776\n"); return result; }
    replay_text("FIXED_SELECTION_PASS fixed_e8_m4_pair775_776 first=775 last=776 calls=2\nBOARD_CASE_PASS fixed_e8_m4_pair775_776\nBOARD_REPLAY_PASS\n");
    return 0;
}
