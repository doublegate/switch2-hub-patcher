; EXPERIMENTAL REAL-IMAGE integration, NOT the 8000+ simulation overlay.
; Source/UFP, native source-ready 42=1D/43=17 only. New persistent state: bit45.
; No new XDATA allocation, queue, MessageID counter or hardware-status names.
; Bounded EA-masked validation -> bank0 registers, native RX-pending claim.
; TX busy: leave original RX pending and return. New RX/error before trigger:
; drop the old draft, retain fresh event, no mode change, no TX trigger.
; Mode flag changes optimistically at TX START, like stock DP handling, NOT
; confirmed delivery. Uses stock65D5 and generic stockVDM wait78/previous72.
; Private bit45 and erased CODE cave are explicit experimental assumptions.
.module target_responder
.area TARGET (ABS,CODE)
.org 0x7000
source_router:
    push 0x82
    push 0x83
    push 0x00
    push 0x01
    push 0x02
    push 0x03
    push 0x04
    push 0x05
    push 0x06
    push 0x07
    push 0xa8
    clr 0xaf
    mov a,0xd0
    anl a,#0x18
    jnz fallback
    mov a,0x42
    cjne a,#0x1d,fallback
    mov a,0x43
    cjne a,#0x17,fallback
    mov a,0x36
    anl a,#3
    cjne a,#1,fallback
    mov a,0x4b
    jnb 0xe4,fallback
    jb 0x38,fallback
    mov a,0x2c
    cjne a,#0x2f,fallback
    lcall validate
    mov a,r7
    jz fallback
    mov a,0x4b
    anl a,#0x86
    jnz defer
    mov a,0x4c
    jb 0xe1,defer           ; native source dispatcher gives this event priority
    mov dptr,#0x28d1
    movx a,@dptr
    jnb 0xe0,defer
    ; Freeze PD header context into bank0 before restoring interrupts.
    mov r4,#0x4f
    jnb 0x03,revision_ready
    mov r4,#0x8f
revision_ready:
    mov a,r2
    swap a
    orl a,#1
    mov r5,a
    anl 0x4b,#0xef
    pop 0xa8
    lcall build_reply
    ljmp finish_reply
fallback:
    pop 0xa8
    pop 0x07
    pop 0x06
    pop 0x05
    pop 0x04
    pop 0x03
    pop 0x02
    pop 0x01
    pop 0x00
    pop 0x83
    pop 0x82
    ; Relocate precisely the four replaced bytes; resume original JZ at5D43.
    mov a,0x2c
    add a,#0xde
    ljmp 0x5d43
defer:
    pop 0xa8
    ljmp restore_context

.org 0x7100
validate:
    mov r7,#0
    mov r6,0x2b
    mov dptr,#0x28d3
    movx a,@dptr
    mov r0,a
    inc dptr
    movx a,@dptr
    mov r1,a
    inc dptr
    movx a,@dptr
    cjne a,#0x7e,validate_return
    inc dptr
    movx a,@dptr
    cjne a,#0x05,validate_return
    mov a,r1
    jb 0xe7,structured_branch
    ljmp proprietary_validate
structured_branch:
    ljmp structured_validate
validate_return:
    ret

.org 0x7180
structured_validate:
    mov a,r6
    cjne a,#1,structured_reject
    mov a,r0
    anl a,#0xe0
    jnz structured_reject
    mov a,r1
    anl a,#0xf8
    cjne a,#0x80,structured_v2
    sjmp structured_version_ok
structured_v2:
    cjne a,#0xa0,structured_v21
    sjmp structured_version_ok
structured_v21:
    cjne a,#0xa8,structured_reject
structured_version_ok:
    mov r3,#1
    mov a,r0
    cjne a,#3,structured_not_modes
    mov a,r1
    anl a,#7
    jnz structured_reject
    mov r2,#2
    sjmp structured_accept
structured_not_modes:
    cjne a,#4,structured_not_enter
    sjmp structured_position
structured_not_enter:
    cjne a,#5,structured_reject
structured_position:
    mov a,r1
    anl a,#7
    cjne a,#1,structured_reject
    mov r2,#1
structured_accept:
    mov r7,#1
    ret
structured_reject:
    mov r7,#0
    ret

.org 0x7200
proprietary_validate:
    jnb 0x45,proprietary_reject
    mov a,r0
    cjne a,#1,proprietary_reject
    mov a,r1
    jnz proprietary_reject
    mov a,r6
    clr c
    subb a,#2
    jc proprietary_reject
    mov a,r6
    clr c
    subb a,#6
    jnc proprietary_reject
    inc dptr
    movx a,@dptr
    mov r0,a
    inc dptr
    movx a,@dptr
    mov r1,a
    inc dptr
    movx a,@dptr
    jnz proprietary_reject
    inc dptr
    movx a,@dptr
    jnz proprietary_reject
    mov r3,#0
    ljmp proprietary_command
proprietary_reject:
    mov r7,#0
    ret

.org 0x7280
proprietary_command:
    mov a,r1
    jz low_command
    cjne a,#1,command_reject
    mov a,r0
    cjne a,#0x31,command_reject
    sjmp expect3
low_command:
    mov a,r0
    cjne a,#0x20,not20
    sjmp expect2
not20:
    cjne a,#1,not01
    sjmp expect2
not01:
    cjne a,#0x29,not29
    mov a,r6
    cjne a,#5,command_reject
    sjmp echo_accept
not29:
    cjne a,#0x44,not44
    sjmp expect3
not44:
    cjne a,#0x41,not41
    sjmp expect3
not41:
    cjne a,#0x49,not49
    sjmp expect3
not49:
    cjne a,#0x23,not23
    sjmp expect3
not23:
    cjne a,#0x51,command_reject
    mov a,r6
    cjne a,#3,command_reject
    mov dptr,#0x28db
    mov r2,#4
argument_zero:
    movx a,@dptr
    jnz command_reject
    inc dptr
    djnz r2,argument_zero
    sjmp echo_accept
expect3:
    mov a,r6
    cjne a,#3,command_reject
echo_accept:
    mov r2,#2
    mov r7,#1
    ret
expect2:
    mov a,r6
    cjne a,#2,command_reject
    mov r2,#3
    mov r7,#1
    ret
command_reject:
    mov r7,#0
    ret

.org 0x7400
build_reply:
    mov r7,#30
    mov dptr,#0x1020
    clr a
clear_loop:
    movx @dptr,a
    inc dptr
    djnz r7,clear_loop
    mov dptr,#0x1020
    mov a,r4
    movx @dptr,a
    inc dptr
    mov a,r5
    movx @dptr,a
    inc dptr
    mov a,r3
    jz build_proprietary
    mov a,r0
    orl a,#0x40
    movx @dptr,a
    inc dptr
    mov a,r1
    movx @dptr,a
    inc dptr
    mov a,#0x7e
    movx @dptr,a
    inc dptr
    mov a,#0x05
    movx @dptr,a
    ret
build_proprietary:
    mov a,#0x41
    movx @dptr,a
    inc dptr
    clr a
    movx @dptr,a
    inc dptr
    mov a,#0x7e
    movx @dptr,a
    inc dptr
    mov a,#0x05
    movx @dptr,a
    inc dptr
    mov a,r0
    movx @dptr,a
    inc dptr
    mov a,r1
    movx @dptr,a
    mov a,r0
    cjne a,#1,build_done
    mov a,r1
    jnz build_done
    mov dptr,#0x102a
    mov a,#3
    movx @dptr,a
    inc dptr
    mov a,#5
    movx @dptr,a
    inc dptr
    mov a,#1
    movx @dptr,a
    inc dptr
    mov a,#3
    movx @dptr,a
build_done:
    ret

.org 0x7500
finish_reply:
    push 0xa8
    clr 0xaf
    mov a,0x4b
    anl a,#0x96             ; fresh RX or native error => do not trigger old draft
    jnz finish_abort
    mov a,0x4c
    jb 0xe1,finish_abort
    clr 0x42
    lcall 0x65d5            ; bounded original trigger, no wait in masked region
    mov a,r3
    jz finish_state
    mov a,r0
    cjne a,#4,finish_not_enter
    setb 0x45
    sjmp finish_state
finish_not_enter:
    cjne a,#5,finish_state
    clr 0x45
finish_state:
    mov 0x43,#0x72          ; recognized generic VDM cleanup context
    mov 0x42,#0x78
finish_abort:
    ljmp finish_unmask
.org 0x7580
finish_unmask:
    pop 0xa8
    ljmp restore_context
.org 0x7600
restore_context:
    pop 0x07
    pop 0x06
    pop 0x05
    pop 0x04
    pop 0x03
    pop 0x02
    pop 0x01
    pop 0x00
    pop 0x83
    pop 0x82
    ret

.org 0x7a00
reset_veneer:
    clr 0x45
    clr a
    mov dptr,#0x2a29
    ljmp 0x5920
.org 0x7a10
boot_veneer:
    clr 0x45
    ljmp 0x1ae7
