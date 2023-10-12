

;   Initial Stack
;  slot  |   type    | value
; -------|-----------|-------
            <empty>
;
;   Args (like stack but R/O)
;  slot  |   type    | value
; -------|-----------|-------
;    0   |ref<u8[][]>| @abcd
;
;   Locals (like args but writeable)
;  slot  |   type    | value
; -------|-----------|-------
;
;   Initial Heap
;  "addr" |    type     | index |  slot   | value
; --------|-------------|-------|---------|-------
;         |             |   0   | usize_t |   2
;  @abcd  |    u8[][]   |   1   |ref<u8[]>| @beef
;         |             |   2   |ref<u8[]>| @face
; --------|-------------|-------|---------|-------
;         |             |   0   | usize_t |   6
;  @beef  |     u8[]    |  1-6  |   u8    |"Hello,"
; --------|-------------|-------|---------|-------
;         |             |   0   | usize_t |   6
;  @face  |     u8[]    |  1-6  |   u8    |"World!"
; --------|-------------|-------|---------|-------


; main: i32(args: str[]) {
;     return args.length;
; };
; /* run with: "./foo Hello, World!" */
main:
    ; Load the value from argument 0 onto stack
    loadarg 0

    ; stack[0] is now ref<u8[][]>: @abcd

    ; Pop stack[0] (@abcd), and push the value from @abcd[0] onto the stack
    refslot 0

    ; stack[0] is now usize_t: 0x0000000000000002

    ; Pop from the stack and convert to i32 (checked), storing back onto the stack
    cconv.i32

    ; stack[0] is now i32: 0x00000002

    ; Return should be the only thing on the stack now
    ret

; main: i32(args: str[]) {
;     ret: i32;
;     ret = args.length;
;     return ret;
; };
; /* run with: "./foo Hello, World!" */
main:
    ; ret is uninitialized. We don't do anything except inform about Initial
    initlocal i32 ; local[0], or ret

    ; Load the value from argument 0 onto stack
    poparg 0

    ; stack[0] is now ref<u8[][]>: @abcd

    ; Pop stack[0] (@abcd), and push the value from @abcd[0] onto the stack
    refslot 0
    
    ; stack[0] is now usize_t: 0x0000000000000002

    ; Pop from the stack and convert to i32 (checked), storing back onto the stack
    cconv.i32

    ; stack[0] is now i32: 0x00000002

    ; pop stack into local[0]
    poplocal 0

    ; stack is now empty and local[0] (ret) is 0x00000002

    ; push the value of local[0] onto stack
    pushlocal 0

    ; stack[0] is now i32: 0x00000002

    ; return
    ret





; main: i32(args: str[]) {
;     return args.length;
; };
:
; Lexical:
;   (return (dot args length))
;           (dot args length)
;
; Logical:
;   return an i32 <- convert u64 to i32 <- Array<T>.length is a u64 <- args is a ref Array<str>
; Reversed:
;   args -> .length -> convert -> return
;
; 1. args is a parameter of type ref Array<str>
;    -> loadarg 0
; 2. .length is a property of Array at slot 0
;    -> refslot 0
; 3. Convert u64 to i32
;    -> cconv.i32
; 4. Return
;
; /* run with: "./foo Hello, World!" */
main:
    ; Load the value from argument 0 onto stack
    loadarg 0

    ; stack[0] is now ref<u8[][]>: @abcd

    ; Pop stack[0] (@abcd), and push the value from @abcd[0] onto the stack
    refslot 0

    ; stack[0] is now usize_t: 0x0000000000000002

    ; Pop from the stack and convert to i32 (checked), storing back onto the stack
    cconv.i32

    ; stack[0] is now i32: 0x00000002

    ; Return should be the only thing on the stack now
    ret

; main: i32(args: str[]) {
;     ret: i32;
;     ret = args.length;
;     return ret;
; };
; Lexical:
;   scope (= ret (. args length)) (return ret)
;                (. args length)
;
; Logical:
;   store in local ret, an i32 <- convert u64 to i32 <- Array<T>.length is a u64 <- args is a ref Array<str>
;   return an i32 <- load local ret, an i32
; Reversed:
;   args -> .length -> convert -> store ret
;   load ret -> return
;
; 1. args is a parameter of type ref Array<str>
;    -> loadarg 0
; 2. .length is a property of Array at slot 0
;    -> refslot 0
; 3. Convert u64 to i32
;    -> cconv.i32
; 4. Store in local ret
;    -> poplocal 0
; 5. load local ret
;    -> pushlocal 0
; 6. return
;
; /* run with: "./foo Hello, World!" */
main:
    ; Load the value from argument 0 onto stack
    pusharg 0

    ; stack[0] is now ref<u8[][]>: @abcd

    ; Pop stack[0] (@abcd), and push the value from @abcd[0] onto the stack
    refslot 0
    
    ; stack[0] is now usize_t: 0x0000000000000002

    ; Pop from the stack and convert to i32 (checked), storing back onto the stack
    cconv.i32

    ; stack[0] is now i32: 0x00000002

    ; pop stack into local[0]
    poplocal 0

    ; stack is now empty and local[0] (ret) is 0x00000002

    ; push the value of local[0] onto stack
    pushlocal 0

    ; stack[0] is now i32: 0x00000002

    ; return
    ret


arg-push <argnum>
local-push <localnum>
     -pop <localnum>
ref-push <slotnum>
   -pop <slotnum>
slot-push <slotnum>
    -pop <slotnum>

cconv<T>
uconv<T>

ret