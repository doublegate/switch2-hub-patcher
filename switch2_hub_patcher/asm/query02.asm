; UNVERIFIED query02-only compatibility probe on exact v5. NOT an HDR fix.
; Captured official data0003006E is advertised; this is NOT RTD2142's real version.
; Existing source-ready/entered/header/role/busy/priority guards remain in force.
; JMP veneers only: no new call frame, RAM, mode state, GPIO or converter access.
.module query02
.area QUERY02 (ABS,CODE)
.org 0x7e00
query02_admission:
    mov a,r1
    jnz original_high
    mov a,r0
    cjne a,#2,original_low
    mov a,r6
    cjne a,#2,reject
    mov r2,#3              ; header + echoed command + captured data word
    mov r7,#1
    ret
original_low:
    ljmp 0x728c            ; original MOV A,R0 / low-command classifier
original_high:
    ljmp 0x7283            ; original CJNE A,#1,command_reject; A still R1
reject:
    mov r7,#0
    ret

.org 0x7e40
query02_extra:
    mov a,r0
    cjne a,#2,original_extra
    mov a,r1
    jnz original_done
    mov dptr,#0x102a
    mov a,#0x6e
    movx @dptr,a
    inc dptr
    clr a
    movx @dptr,a
    inc dptr
    mov a,#3
    movx @dptr,a
    inc dptr
    clr a
    movx @dptr,a
    ret
original_extra:
    mov a,r0
    cjne a,#1,original_done
    ljmp 0x743e            ; original R1 check and03010503 data for query01
original_done:
    ljmp 0x7453            ; original build_done RET
