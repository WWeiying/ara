extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int first_only_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 1;
replay_text("BOARD_CASE_BEGIN first_only\n");
if (first_only_main()) { replay_text("BOARD_CASE_FAIL first_only\n"); return 1; }
replay_text("BOARD_CASE_PASS first_only\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
