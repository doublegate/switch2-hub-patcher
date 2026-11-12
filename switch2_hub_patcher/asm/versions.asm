; UNVERIFIED virtual version replies04/06, layered on exact v6.
; Not actual VIA/RTD2142 versions or an HDR capability claim.
; Original source-ready/entered/header/role/busy/priority guards remain.
; No extra stack, RAM allocation, GPIO/converter actions or update handlers.
.module versions
.area VERSIONS (ABS,CODE)
.org 0x7f00
versions_admit:
    mov a,r1
    jnz prior_admit
    mov a,r0
    cjne a,#4,check06
    sjmp exact_length
check06:
    cjne a,#6,prior_admit
exact_length:
    mov a,r6
    cjne a,#2,prior_admit
    mov r2,#6
    mov r7,#1
    ret
prior_admit:
    ljmp 0x7e00            ; v6 query02 and original classifier

.org 0x7f40
versions_extra:
    mov a,r1
    jnz prior_extra
    mov a,r0
    cjne a,#4,extra06
    mov r6,#0
    sjmp copy_start
extra06:
    cjne a,#6,prior_extra
    mov r6,#16
copy_start:
    mov r7,#0              ; bank0 private counter; never ISR-shared67
copy_byte:
    mov dptr,#0x7fa0
    mov a,r7
    add a,r6
    movc a,@a+dptr
    mov r2,a
    mov a,r7
    add a,#0x2a
    mov dpl,a
    clr a
    addc a,#0x10
    mov dph,a
    mov a,r2
    movx @dptr,a
    inc r7
    cjne r7,#16,copy_byte
    ret
prior_extra:
    ljmp 0x7e40            ; v6 query02 and original query01 data handling

.org 0x7fa0
reply04:
    .db 0xda,0x07,0x01,0x33,0x61,0x6d,0x01,0x06
    .db 0xda,0x07,0x01,0x33,0x61,0x6d,0x01,0x06
reply06:
    .db 0xda,0x07,0x01,0x33,0x68,0x6d,0x01,0x06
    .db 0xda,0x07,0x01,0x33,0x68,0x6d,0x01,0x06
