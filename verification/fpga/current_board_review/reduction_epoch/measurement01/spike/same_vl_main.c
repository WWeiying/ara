extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int same_vl_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 2;
replay_text("BOARD_CASE_BEGIN same_vl\n");
if (same_vl_main()) { replay_text("BOARD_CASE_FAIL same_vl\n"); return 2; }
replay_text("BOARD_CASE_PASS same_vl\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
