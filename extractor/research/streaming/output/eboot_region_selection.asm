Addresses below are eboot.bin file offsets, not ELF virtual addresses.
0079e390: push rbp
0079e391: mov rbp, rsp
0079e394: push r15
0079e396: push r14
0079e398: push r13
0079e39a: push r12
0079e39c: push rbx
0079e39d: sub rsp, 0xa8
0079e3a4: mov r15, r9
0079e3a7: mov rbx, rsi
0079e3aa: mov qword ptr [rbp - 0xb8], r8
0079e3b1: mov qword ptr [rbp - 0xb0], rcx
0079e3b8: mov qword ptr [rbp - 0x98], rdx
0079e3bf: test r15, r15
0079e3c2: je 0x79e3cb
0079e3c4: mov qword ptr [r15], 0
0079e3cb: lea rax, [rip + 0xd9132e]
0079e3d2: mov rdi, qword ptr [rbx + 8]
0079e3d6: mov r14, qword ptr [rax + 0x48]
0079e3da: call 0x8414b0
0079e3df: mov rdi, r14
0079e3e2: mov esi, eax
0079e3e4: call 0x7aa310
0079e3e9: xor r12d, r12d
0079e3ec: test rax, rax
0079e3ef: je 0x79e770
0079e3f5: mov rsi, qword ptr [rbx]
0079e3f8: mov edx, 0x89335b6e
0079e3fd: mov rdi, rax
0079e400: mov qword ptr [rbp - 0xa0], r15
0079e407: call 0x7a4a60
0079e40c: mov r15, rax
0079e40f: cmp dword ptr [r15 + 8], 0
0079e414: je 0x79e770
0079e41a: mov r13, qword ptr [r15]
0079e41d: nop dword ptr [rax]
0079e420: mov esi, dword ptr [rbx + 0x10]
0079e423: mov r14, qword ptr [r13]
0079e427: test esi, esi
0079e429: je 0x79e440
0079e42b: mov rdi, r14
0079e42e: call 0x8110a0
0079e433: test rax, rax
0079e436: je 0x79e440
0079e438: mov eax, dword ptr [rax + 8]
0079e43b: cmp eax, dword ptr [rbx + 0x14]
0079e43e: jne 0x79e4a2
0079e440: mov rsi, qword ptr [rbx]
0079e443: vxorps xmm0, xmm0, xmm0
0079e447: xor edx, edx
0079e449: xor ecx, ecx
0079e44b: mov r8d, 1
0079e451: xor r9d, r9d
0079e454: mov rdi, r14
0079e457: call 0x812820
0079e45c: test al, al
0079e45e: je 0x79e4a2
0079e460: mov edi, dword ptr [r14 + 8]
0079e464: call 0x7a9b20
0079e469: test rax, rax
0079e46c: jne 0x79e734
0079e472: mov esi, 0xf131b5e1
0079e477: mov rdi, r14
0079e47a: call 0x811b70
0079e47f: mov ecx, 1
0079e484: test rax, rax
0079e487: je 0x79e4c2
0079e489: mov esi, 0xf131b5e1
0079e48e: mov edx, 1
0079e493: mov rdi, r14
0079e496: call 0x811e00
0079e49b: mov rcx, rax
0079e49e: test ecx, ecx
0079e4a0: jg 0x79e4c2
0079e4a2: movsxd rax, dword ptr [r15 + 8]
0079e4a6: add r13, 8
0079e4aa: xor r12d, r12d
0079e4ad: shl rax, 3
0079e4b1: add rax, qword ptr [r15]
0079e4b4: cmp r13, rax
0079e4b7: jne 0x79e420
0079e4bd: jmp 0x79e770
0079e4c2: lea r15, [rbp - 0x48]
0079e4c6: lea rsi, [rip + 0x9866e9]
0079e4cd: xor eax, eax
0079e4cf: mov edx, ecx
0079e4d1: mov qword ptr [rbp - 0xc0], rbx
0079e4d8: mov qword ptr [rbp - 0xc8], rcx
0079e4df: xor r12d, r12d
0079e4e2: mov rbx, rcx
0079e4e5: mov rdi, r15
0079e4e8: call 0x6def30
0079e4ed: mov esi, 1
0079e4f2: mov rdi, r15
0079e4f5: call 0xbf3270
0079e4fa: lea r13, [rbp - 0x68]
0079e4fe: mov r15d, eax
0079e501: lea rsi, [rip + 0x9866b7]
0079e508: xor eax, eax
0079e50a: mov edx, ebx
0079e50c: mov rdi, r13
0079e50f: mov dword ptr [rbp - 0xa4], r15d
0079e516: call 0x6def30
0079e51b: mov esi, 1
0079e520: mov rdi, r13
0079e523: call 0xbf3270
0079e528: cmp ebx, 1
0079e52b: mov ebx, 0x3729e786
0079e530: mov dword ptr [rbp - 0xa8], eax
0079e536: mov ecx, 0xc4c6f3cc
0079e53b: cmovne ebx, eax
0079e53e: mov ax, word ptr [r14 + 0x30]
0079e543: cmovne ecx, r15d
0079e547: mov dword ptr [rbp - 0xa0], ecx
0079e54d: test ax, ax
0079e550: jle 0x79e6d5
0079e556: xor r15d, r15d
0079e559: nop dword ptr [rax]
0079e560: mov rcx, qword ptr [r14 + 0x40]
0079e564: mov rdx, r15
0079e567: shl rdx, 4
0079e56b: mov esi, dword ptr [rcx + rdx]
0079e56e: cmp esi, ebx
0079e570: je 0x79e5a0
0079e572: cmp esi, dword ptr [rbp - 0xa8]
0079e578: je 0x79e5a0
0079e57a: cmp esi, dword ptr [rbp - 0xa0]
0079e580: je 0x79e5a0
0079e582: cmp esi, 0x4f807b48
0079e588: je 0x79e5a0
0079e58a: cmp esi, dword ptr [rbp - 0xa4]
0079e590: jne 0x79e6c5
0079e596: nop word ptr cs:[rax + rax]
0079e5a0: mov rdi, qword ptr [rcx + rdx + 8]
0079e5a5: mov esi, 1
0079e5aa: lea r13, [rcx + rdx]
0079e5ae: mov qword ptr [rbp - 0x70], rdi
0079e5b2: call 0xbf3270
0079e5b7: lea rcx, [rip + 0xeb1342]
0079e5be: mov dword ptr [rbp - 0x78], eax
0079e5c1: mov rdi, qword ptr [rcx]
0079e5c4: test rdi, rdi
0079e5c7: je 0x79e5d7
0079e5c9: mov rax, qword ptr [rdi]
0079e5cc: lea rsi, [rbp - 0x78]
0079e5d0: lea rdx, [rbp - 0x70]
0079e5d4: call qword ptr [rax + 0x30]
0079e5d7: mov eax, dword ptr [r13]
0079e5db: cmp eax, 0x4f807b48
0079e5e0: sete cl
0079e5e3: cmp eax, dword ptr [rbp - 0xa4]
0079e5e9: sete dl
0079e5ec: or dl, cl
0079e5ee: mov rcx, qword ptr [rbp - 0x98]
0079e5f5: cmp eax, dword ptr [rbp - 0xa0]
0079e5fb: sete r13b
0079e5ff: movsxd rax, dword ptr [rcx + 0xc00]
0079e606: or r13b, dl
0079e609: test rax, rax
0079e60c: je 0x79e646
0079e60e: lea rcx, [rax*8]
0079e616: mov edx, dword ptr [rbp - 0x78]
0079e619: lea rsi, [rcx + rcx*2]
0079e61d: mov rcx, qword ptr [rbp - 0x98]
0079e624: nop word ptr cs:[rax + rax]
0079e630: cmp dword ptr [rcx + 8], edx
0079e633: je 0x79e6b2
0079e635: add rcx, 0x18
0079e639: add rsi, -0x18
0079e63d: jne 0x79e630
0079e63f: cmp eax, 0x80
0079e644: je 0x79e6c0
0079e646: mov rsi, qword ptr [rbp - 0x70]
0079e64a: lea rdi, [rbp - 0x90]
0079e651: call 0x7b13a0
0079e656: mov al, byte ptr [rbp - 0x82]
0079e65c: mov rdx, qword ptr [rbp - 0x98]
0079e663: and al, 0xfe
0079e665: or al, r13b
0079e668: mov byte ptr [rbp - 0x82], al
0079e66e: movsxd rax, dword ptr [rdx + 0xc00]
0079e675: lea ecx, [rax + 1]
0079e678: lea rax, [rax + rax*2]
0079e67c: mov dword ptr [rdx + 0xc00], ecx
0079e682: mov rcx, qword ptr [rbp - 0x90]
0079e689: mov qword ptr [rdx + rax*8], rcx
0079e68d: mov ecx, dword ptr [rbp - 0x88]
0079e693: mov dword ptr [rdx + rax*8 + 8], ecx
0079e697: lea rcx, [rbp - 0x84]
0079e69e: mov rsi, rcx
0079e6a1: mov ecx, dword ptr [rsi + 8]
0079e6a4: mov dword ptr [rdx + rax*8 + 0x14], ecx
0079e6a8: mov rcx, qword ptr [rsi]
0079e6ab: mov qword ptr [rdx + rax*8 + 0xc], rcx
0079e6b0: jmp 0x79e6c0
0079e6b2: test r13b, r13b
0079e6b5: jne 0x79e6c0
0079e6b7: and byte ptr [rcx + 0xe], 0xfe
0079e6bb: nop dword ptr [rax + rax]
0079e6c0: movzx eax, word ptr [r14 + 0x30]
0079e6c5: inc r15
0079e6c8: movsx rcx, ax
0079e6cc: cmp r15, rcx
0079e6cf: jl 0x79e560
0079e6d5: mov rax, qword ptr [rbp - 0xb0]
0079e6dc: test eax, eax
0079e6de: jle 0x79e6f0
0079e6e0: mov rax, qword ptr [rbp - 0xb8]
0079e6e7: mov r12d, 1
0079e6ed: mov qword ptr [rax], r14
0079e6f0: cmp byte ptr [rbp + 0x10], 0
0079e6f4: je 0x79e770
0079e6f6: mov edi, 2
0079e6fb: call 0xc8f2a0
0079e700: mov rax, qword ptr [rbp - 0xc0]
0079e707: mov rbx, qword ptr [r14]
0079e70a: mov rdi, qword ptr [rax + 8]
0079e70e: call 0x840e20
0079e713: mov rcx, qword ptr [rbp - 0xc8]
0079e71a: lea rdi, [rip + 0x9864b2]
0079e721: lea rdx, [rip + 0x98648d]
0079e728: xor eax, eax
0079e72a: mov rsi, rbx
0079e72d: call 0xc8f2d0
0079e732: jmp 0x79e770
0079e734: mov rcx, qword ptr [rbp - 0xb0]
0079e73b: xor r12d, r12d
0079e73e: test ecx, ecx
0079e740: jle 0x79e752
0079e742: mov rcx, qword ptr [rbp - 0xb8]
0079e749: mov r12d, 1
0079e74f: mov qword ptr [rcx], r14
0079e752: mov rcx, qword ptr [rbp - 0xa0]
0079e759: test rcx, rcx
0079e75c: je 0x79e761
0079e75e: mov qword ptr [rcx], rax
0079e761: mov rsi, qword ptr [rbp - 0x98]
0079e768: mov rdi, rax
0079e76b: call 0x7a9990
0079e770: mov rax, qword ptr [rbp - 0xb0]
0079e777: cmp r12d, eax
0079e77a: jge 0x79e79b
0079e77c: mov rcx, qword ptr [rbp - 0xb8]
0079e783: dec eax
0079e785: xor esi, esi
0079e787: sub eax, r12d
0079e78a: lea rdx, [rax*8 + 8]
0079e792: lea rdi, [rcx + r12*8]
0079e796: call 0x1090c60
00bf3270: mov rax, rdi
00bf3273: test rax, rax
00bf3276: je 0xbf328f
00bf3278: cmp byte ptr [rax], 0
00bf327b: je 0xbf328f
00bf327d: mov rcx, qword ptr [rip + 0x953534]
00bf3284: movzx edx, sil
00bf3288: xor edi, edi
00bf328a: mov rsi, rax
00bf328d: jmp rcx
00bf328f: xor eax, eax
00bf3291: ret 
00c73440: test rsi, rsi
00c73443: je 0xc73479
00c73445: mov cl, byte ptr [rsi]
00c73447: test cl, cl
00c73449: je 0xc73479
00c7344b: inc rsi
00c7344e: lea rax, [rip + 0x52e42b]
00c73455: nop word ptr cs:[rax + rax]
00c73460: mov edx, edi
00c73462: movzx ecx, cl
00c73465: shl edi, 8
00c73468: shr edx, 0x18
00c7346b: xor ecx, edx
00c7346d: xor edi, dword ptr [rax + rcx*4]
00c73470: mov cl, byte ptr [rsi]
00c73472: inc rsi
00c73475: test cl, cl
00c73477: jne 0xc73460
00c73479: mov eax, edi
00c7347b: ret 
00811be0: push rbp
00811be1: mov rbp, rsp
00811be4: push r15
00811be6: push r14
00811be8: push r13
00811bea: push r12
00811bec: push rbx
00811bed: push rax
00811bee: movsx edx, word ptr [rdi + 0x32]
00811bf2: xor eax, eax
00811bf4: mov r15d, ecx
00811bf7: mov ebx, 0
00811bfc: test edx, edx
00811bfe: jle 0x811de5
00811c04: mov rcx, qword ptr [rdi + 0x38]
00811c08: mov edi, edx
00811c0a: dec edi
00811c0c: nop dword ptr [rax]
00811c10: lea ebx, [rax + rdi]
00811c13: mov edx, ebx
00811c15: shr edx, 0x1f
00811c18: add edx, ebx
00811c1a: sar edx, 1
00811c1c: movsxd rbx, edx
00811c1f: shl rbx, 4
00811c23: cmp dword ptr [rcx + rbx], esi
00811c26: jae 0x811c40
00811c28: lea eax, [rdx + 1]
00811c2b: mov ebx, 0
00811c30: cmp edx, edi
00811c32: jl 0x811c10
00811c34: jmp 0x811de5
00811c39: nop dword ptr [rax]
00811c40: jbe 0x811c50
00811c42: mov ebx, 0
00811c47: cmp eax, edx
00811c49: jl 0x811c08
00811c4b: jmp 0x811de5
00811c50: mov r14, qword ptr [rcx + rbx + 8]
00811c55: xor ebx, ebx
00811c57: mov r12d, 1
00811c5d: test r14, r14
00811c60: je 0x811de5
00811c66: mov rbx, 0xffffffffffffffff
00811c6d: jmp 0x811c75
00811c6f: nop 
00811c70: pause 
00811c72: inc r12
00811c75: cmp qword ptr [rip + 0xe403c3], 0
00811c7d: jne 0x811c8c
00811c7f: xor eax, eax
00811c81: lock cmpxchg qword ptr [rip + 0xe403b6], rbx
00811c8a: je 0x811ca1
00811c8c: cmp r12, 0x2711
00811c93: jb 0x811c70
00811c95: mov edi, 1
00811c9a: call 0xc8d080
00811c9f: jmp 0x811c70
00811ca1: lfence 
00811ca4: cmp r15d, 4
00811ca8: jb 0x811cdd
00811caa: call 0xc91770
00811caf: test rax, rax
00811cb2: je 0x811cdb
00811cb4: lea rdi, [rip + 0x91ce1a]
00811cbb: lea rsi, [rip + 0x91ce52]
00811cc2: lea rdx, [rip + 0x91ce96]
00811cc9: lea rcx, [rip + 0x91ce04]
00811cd0: mov r8d, 0x527
00811cd6: xor r9d, r9d
00811cd9: call rax
00811cdb: int 0x41
00811cdd: mov r15d, r15d
00811ce0: lea r12, [rip + 0xe40379]
00811ce7: mov eax, dword ptr [r12 + r15*4]
00811ceb: test eax, eax
00811ced: jns 0x811d26
00811cef: call 0xc91770
00811cf4: test rax, rax
00811cf7: je 0x811d20
00811cf9: lea rdi, [rip + 0x91ce64]
00811d00: lea rsi, [rip + 0x91ce0d]
00811d07: lea rdx, [rip + 0x91ce51]
00811d0e: lea rcx, [rip + 0x91cdbf]
00811d15: mov r8d, 0x528
00811d1b: xor r9d, r9d
00811d1e: call rax
00811d20: int 0x41
00811d22: mov eax, dword ptr [r12 + r15*4]
00811d26: inc eax
00811d28: xor esi, esi
00811d2a: xor edx, edx
00811d2c: mov rdi, r14
00811d2f: mov dword ptr [r12 + r15*4], eax
00811d33: xor eax, eax
00811d35: sfence 
00811d38: xchg qword ptr [rip + 0xe40301], rax
00811d3f: call 0xbceba0
00811d44: mov rbx, rax
00811d47: mov r14d, 1
00811d4d: mov r13, 0xffffffffffffffff
00811d54: jmp 0x811d65
00811d56: nop word ptr cs:[rax + rax]
00811d60: pause 
00811d62: inc r14
00811d65: cmp qword ptr [rip + 0xe402d3], 0
00811d6d: jne 0x811d7c
00811d6f: xor eax, eax
00811d71: lock cmpxchg qword ptr [rip + 0xe402c6], r13
00811d7a: je 0x811d91
00811d7c: cmp r14, 0x2711
00811d83: jb 0x811d60
00811d85: mov edi, 1
00811d8a: call 0xc8d080
00811d8f: jmp 0x811d60
00811d91: lfence 
00811d94: mov eax, dword ptr [r12 + r15*4]
00811d98: test eax, eax
00811d9a: jg 0x811dd3
00811d9c: call 0xc91770
00811da1: test rax, rax
00811da4: je 0x811dcd
00811da6: lea rdi, [rip + 0x91cddc]
00811dad: lea rsi, [rip + 0x91cd60]
00811db4: lea rdx, [rip + 0x91cda4]
00811dbb: lea rcx, [rip + 0x91cd12]
00811dc2: mov r8d, 0x530
00811dc8: xor r9d, r9d
00811dcb: call rax
00811dcd: int 0x41
00811dcf: mov eax, dword ptr [r12 + r15*4]
00811dd3: dec eax
00811dd5: mov dword ptr [r12 + r15*4], eax
00811dd9: xor eax, eax
00811ddb: sfence 
00811dde: xchg qword ptr [rip + 0xe4025b], rax
00811de5: mov rax, rbx
00811de8: add rsp, 8
00811dec: pop rbx
00811ded: pop r12