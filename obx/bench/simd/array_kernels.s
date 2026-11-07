/* x64gen's sequence for the int64 array loop of array_obxstyle.c:
   long array_round(long *a, long n, long r).

   Two variants: array_round_check keeps the vector bounds check in the body
   (the loop condition i + 4 <= n does not prove it to the current facts
   engine); array_round_nocheck drops it, as a fact pass would when the loop
   condition is the same bound. Both have the scalar tail. */
    .text
    .intel_syntax noprefix

.macro ARRAY_ROUND name, check
    .globl \name
    .type \name, @function
\name:
    vmovq xmm7, rdx             /* r, broadcast to four int64 lanes */
    vpbroadcastq ymm7, xmm7
    vpxor ymm8, ymm8, ymm8      /* the sum of the elements, four lanes */
    xor eax, eax
    lea r8, [rsi - 3]           /* the vector bound: i + 4 <= n */
    cmp rax, r8
    jae 9f
1:
.if \check
    cmp rax, r8                 /* the checked vload and vstore: i + 4 <= n */
    jae 8f
.endif
    vmovdqu ymm0, [rdi + rax*8]
    vpaddq ymm0, ymm0, ymm7
    vmovdqu [rdi + rax*8], ymm0
    vpaddq ymm8, ymm8, ymm0
    add rax, 4
    cmp rax, r8
    jb 1b
9:
    xor r9, r9
10:
    cmp rax, rsi
    jae 11f
    add [rdi + rax*8], rdx
    mov rcx, [rdi + rax*8]
    add r9, rcx
    inc rax
    jmp 10b
11:
    vmovq xmm0, r9              /* the tail into lane 0 (each round is independent) */
    vpaddq ymm8, ymm8, ymm0
    /* vsum of the four int64 lanes */
    vextracti128 xmm0, ymm8, 1
    vpaddq xmm8, xmm8, xmm0
    vpshufd xmm1, xmm8, 0x4E
    vpaddq xmm8, xmm8, xmm1
    vmovq rax, xmm8
    ret
8:
    ud2
    .size \name, .-\name
.endm

    ARRAY_ROUND array_round_check, 1
    ARRAY_ROUND array_round_nocheck, 0

    .section .note.GNU-stack,"",@progbits
