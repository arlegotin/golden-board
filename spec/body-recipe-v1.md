# Generic bounded body decoder recipes v1

This owner fixes the logical programs for the development body codec in
`body-codec-v1.md`. It uses only the existing 25 operations, typing, arithmetic,
status rules and resource limits from `bootstrap-v0.md`. The compact wire is
owned by `recipe-wire-v1.md`; compact serialization never changes these logical
programs. This owner does not promote profile 8 or alter a historical carrier.
Independent implementations construct the programs below from this owner,
not by consuming another implementation's serialized recipe package.

## Interfaces and state

| ID | Input descriptors, in order | Output descriptors, in order |
|---:|---|---|
| 201 | BYTES32782, UINT64 | STATUS16, BYTES32782 |
| 202 | BYTES16384, UINT16 | STATUS16, UINT16, BYTES16384 |
| 203 | BYTES9, UINT16 | STATUS16, BYTES8 |

Recipe 202 receives a fixed input buffer and its encoded-prefix length. Bytes
beyond that length are ignored; zero padding is convenient for an adapter but
is not an admission condition. Its success outputs are decoded length and
the decoded prefix followed by zeros to exactly 16384 bytes. Recipe 203
receives a nine-byte token-body buffer and its prefix length (at most 9),
constructs a codec-3 header for decoded length 8, and returns exactly eight
decoded bytes. Its unused input padding is likewise ignored. Neither recipe
coerces input types: the existing VM's descriptor and byte-input checks apply.

Recipe 201 is an internal state step. Its UINT64 iteration ordinal is unused;
progress is carried in the state. Only initialization below establishes the
state invariant required by the complete decoder. Arbitrary external state
is not an alternative entrypoint for validating a section.

All multibyte numbers below are big-endian. Let B=16384 and S=32782.

| Symbol | Offset | Width | Meaning |
|---|---:|---:|---|
| input | 0 | B | Encoded buffer |
| output | B | B | Output buffer, initially zero |
| N | 32768 | 2 | Encoded-prefix length |
| L | 32770 | 2 | Declared decoded length |
| P | 32772 | 2 | Encoded cursor |
| O | 32774 | 2 | Produced byte count |
| D | 32776 | 2 | Active backward distance |
| R | 32778 | 1 | Remaining copy bytes |
| F | 32779 | 1 | Flags shifted left after each consumed token |
| K | 32780 | 1 | Token positions remaining in the flag group |
| E | 32781 | 1 | Header admission result: 1 for valid, 0 for invalid |

Explicit malformed codec input returns status 3 with no output. Automatic VM
checked-arithmetic/resource failures retain status 11. ITERATE propagates a
nonzero body status atomically. Finalization also exposes no prefix on error.
These are codec results, not section, typed-content or learner admission.

## Canonical construction rules

The following ordered construction pseudocode defines the program, including
node order and sharing. Each recipe starts a fresh builder with its input and
output descriptors above and empty caches. Expressions evaluate left to right,
including every argument of a helper call, before that helper executes. All
elements passed to ALL are evaluated before ALL performs its fold. Assignment
aliases a value reference; it emits no node. No optimizer, common-subexpression
elimination, constant folding or dead-node removal is applied.

`emit(op,type,width,args=[],aux=0,imm=0)` appends one node. Its node ID is its
one-based ordinal in this recipe. Its returned value ID is input-count plus
node ID. Unspecified arguments/fields are zero in the expanded wire. Input
value IDs are 1 and 2. Sequence widths use bytes; UINT widths use bits.

Three caches are permitted, and no others:

- `U(w,v)` and `BOOL(v)` share a constant cache keyed by `(type,width,value)`.
  A miss emits CONST/op1. `U8(v)=U(8,v)`; `U16(v)=U(16,v)`; BOOL uses BOOL1.
- `STATUS(v)` has a separate cache keyed by status value. A miss emits
  SUCCESS/op24 for 0 or FAIL/op25 with immediate v otherwise, type STATUS16.
- `TABLE(id,width)` caches by table ID. A miss emits op2 with output type TABLE,
  the given width and auxiliary ID. Table widths below are fixed and never conflict.

The required existing tables are exactly:

| ID | Element type | Width | Count | Payload definition |
|---:|---|---:|---:|---|
| 3 | UINT | 16 | 256 | Big-endian u16 values 0 through 255 in order |
| 4 | BYTES | 1 | 1 | One zero byte |
| 5 | UINT | 8 | 256 | Byte values 0 through 255 in order |

These may be shared only with identical tables in a validated combined
package. Their standalone encoded size, including three 16-byte table headers,
is 817 bytes. The production program definitions are immutable fresh values;
they are not cached mutable builders.

### Primitive shorthand and helper expansion

Every primitive shorthand emits a fresh node unless an explicit cache above
applies. Arithmetic `ADDw/SUBw/SHLw/SHRw(a,b)` emits respectively op6/7/15/16,
UINTw, arguments `(a,b)`. `MASKw(a,m)` emits op14 UINTw, `(a)`, immediate m.
`EQ(a,b)` and `LT(a,b)` emit op17/op18 BOOL1. `SEL(type,width,c,y,n)` emits
op23 with `(c,y,n)`. `CAT(type,width,a,b)` emits CONCAT/op4 with `(a,b)`.
`READ(state,index)` emits op19 UINT8 with `(state,index)`.
`WRITE(state,index,value)` emits op20 BYTESS with `(state,index,value)`.
`LOOK(type,width,table,index)` emits op21 with `(table,index)`.

Helpers expand in the following order. Locals in helper expansions are scoped
to that invocation; host conditionals below concern fixed construction values,
not runtime branching.

```text
NOT(v): return EQ(v, BOOL(false))
AND(a,b): return SEL(BOOL,1,a,b,BOOL(false))
OR(a,b): return SEL(BOOL,1,a,BOOL(true),b)
LE(a,b): return NOT(LT(b,a))
ALL(a,b,...): result=a; for each remaining reference x in order: result=AND(result,x); return result
READ_FIXED(state,offset): return READ(state,U16(offset))
WRITE_FIXED(state,offset,value): return WRITE(state,U16(offset),value)
READ_UINT(state,offset,n):
  value=READ_FIXED(state,offset); width=8
  for i=1 through n-1:
    following=READ_FIXED(state,offset+i)
    width=width+8
    value=CAT(UINT,width,value,following)
  return value
WRITE_UINT(state,offset,n,value):
  width=8*n
  identity=TABLE(5,8)
  for i=0 through n-1:
    shift=8*(n-i-1); shifted=value
    if shift != 0: shifted=SHRw(value,U(width,shift)) where w=width
    masked=MASKw(shifted,255) where w=width
    byte=LOOK(UINT,8,identity,masked)
    state=WRITE_FIXED(state,offset+i,byte)
  return state
WIDEN(v): return LOOK(UINT,16,TABLE(3,16),v)
SAFE_INPUT(index):
  safe=SEL(UINT,16,LT(index,U16(B)),index,U16(0))
  return READ(1,safe)
ITER(state,body,count): return emit(22,BYTES,S,[state],aux=body,imm=count)
FINISH(status,values):
  emit(5,STATUS,16,[status],aux=1)
  for each value in order, with output slot beginning at 2:
    emit(5,STATUS,16,[value],aux=slot)
ZERO_BYTES(length):
  table=TABLE(4,1)
  zero=U8(0)
  first=LOOK(BYTES,1,table,zero)
  powers=[(1,first)]
  while last width <= floor(length/2):
    (width,value)=last pair
    append (2*width,CAT(BYTES,2*width,value,value))
  remaining=length; output=absent
  for (width,value) in powers in reverse order:
    if width <= remaining:
      if output is absent: output=value
      else: output=CAT(BYTES,length-remaining+width,output,value)
      remaining=remaining-width
  require remaining=0 and output present
  return output
```

`SAFE_INPUT` always reads the state input value 1; it is used only in recipe
201. It clamps every speculative read into the fixed input array. SELECT is
eager. In particular, the copy-source subtraction below is clamped before it
executes, even for a literal, rejected token or inactive output iteration.

### Recipe 201: one output-byte iteration

Construct the following statements in this exact order. Multi-assignment here
means each right-hand expression is constructed in the listed order.

```text
n=READ_UINT(1,N,2)
target=READ_UINT(1,L,2)
cursor=READ_UINT(1,P,2)
produced=READ_UINT(1,O,2)
distance=READ_UINT(1,D,2)
remaining=READ_FIXED(1,R)
flags=READ_FIXED(1,F)
tokens=READ_FIXED(1,K)
admitted=READ_FIXED(1,E)
active=LT(produced,target)
new_token=EQ(remaining,U8(0))
new_group=EQ(tokens,U8(0))
next_flags=SEL(UINT,8,new_group,SAFE_INPUT(cursor),flags)
token_cursor=ADD16(cursor,SEL(UINT,16,new_group,U16(1),U16(0)))
first=SAFE_INPUT(token_cursor)
second=SAFE_INPUT(ADD16(token_cursor,U16(1)))
word=CAT(UINT,16,first,second)
high_bit=MASK8(next_flags,128)
copy=EQ(high_bit,U8(128))
new_distance=ADD16(SHR16(word,U16(4)),U16(1))
copy_length=ADD8(MASK8(second,15),U8(3))
token_length=SEL(UINT,8,copy,copy_length,U8(1))
token_end=ADD16(token_cursor,SEL(UINT,16,copy,U16(2),U16(1)))
end_output=ADD16(produced,WIDEN(token_length))
good_token=ALL(LE(token_end,n),LE(end_output,target),OR(NOT(copy),LE(new_distance,produced)))
good=ALL(EQ(admitted,U8(1)),OR(NOT(active),OR(NOT(new_token),good_token)))
status=SEL(STATUS,16,good,STATUS(0),STATUS(3))
distance_used=SEL(UINT,16,new_token,new_distance,distance)
safe_produced=SEL(UINT,16,LT(produced,distance_used),distance_used,produced)
source=ADD16(U16(B),SUB16(safe_produced,distance_used))
copy_byte=READ(1,source)
output_byte=SEL(UINT,8,OR(NOT(new_token),copy),copy_byte,first)
updated=WRITE(1,ADD16(U16(B),produced),output_byte)
selected_cursor=SEL(UINT,16,new_token,token_end,cursor)
updated=WRITE_UINT(updated,P,2,selected_cursor)
updated=WRITE_UINT(updated,O,2,ADD16(produced,U16(1)))
updated=WRITE_UINT(updated,D,2,distance_used)
old_remaining_safe=SEL(UINT,8,new_token,U8(1),remaining)
old_remaining_next=SUB8(old_remaining_safe,U8(1))
new_remaining=SUB8(token_length,U8(1))
updated=WRITE_FIXED(updated,R,SEL(UINT,8,new_token,new_remaining,old_remaining_next))
shifted=SHL8(MASK8(next_flags,127),U8(1))
updated=WRITE_FIXED(updated,F,SEL(UINT,8,new_token,shifted,flags))
available=SEL(UINT,8,new_group,U8(8),tokens)
next_tokens=SUB8(available,U8(1))
updated=WRITE_FIXED(updated,K,SEL(UINT,8,new_token,next_tokens,tokens))
updated=SEL(BYTES,S,active,updated,1)
FINISH(status,[updated])
```

A new token verifies its complete encoded length, final decoded bound and,
for copies, distance at most the bytes already produced. A continuation uses
the previously checked copy run. Every active successful iteration writes one
byte. Remaining flag bits are shifted to the high positions after each token;
they must be all zero at completion. Inactive iterations preserve all state.
For initialized admitted states, produced is at most B, cursor is at most B,
distance is at most 4096 and token length at most 18. Eager candidate arithmetic
therefore stays inside UINT16; the candidate write at output offset B+B while
inactive is inside metadata and is discarded by the final state SELECT.

### Shared construction macros

These macros emit inline nodes, not extra recipe calls. They use each calling
recipe's existing caches. `extra` is either an already constructed BOOL
reference or absent; `include_length` is a construction-time boolean.

```text
INITIALIZE(encoded,encoded_length,extra=absent):
  target=READ_UINT(encoded,1,2)
  good=ALL(LE(U16(3),encoded_length),LE(encoded_length,U16(B)),
           LE(target,U16(B)),EQ(READ_FIXED(encoded,0),U8(3)))
  if extra is present: good=AND(good,extra)
  state=CAT(BYTES,S,encoded,ZERO_BYTES(B+14))
  state=WRITE_UINT(state,N,2,encoded_length)
  state=WRITE_UINT(state,L,2,target)
  state=WRITE_FIXED(state,P+1,U8(3))
  state=WRITE_FIXED(state,E,SEL(UINT,8,good,U8(1),U8(0)))
  return (state,target)
FINALIZE(state,encoded_length,target,output_length,include_length):
  good=ALL(EQ(READ_UINT(state,P,2),encoded_length),EQ(READ_UINT(state,O,2),target),
           EQ(READ_FIXED(state,R),U8(0)),EQ(READ_FIXED(state,F),U8(0)))
  status=SEL(STATUS,16,good,STATUS(0),STATUS(3))
  decoded=emit(3,BYTES,output_length,[state,U16(B),U16(output_length)])
  if include_length: FINISH(status,[target,decoded])
  else: FINISH(status,[decoded])
```

### Recipe 202: full section composition

```text
(state,target)=INITIALIZE(1,2)
state=ITER(state,201,16384)
FINALIZE(state,2,target,16384,true)
```

The exact fixed iteration count also applies to empty output. Header failure
propagates from the first body iteration; it cannot release partially decoded
bytes. Valid empty encoding is exactly `03 00 00`. For nonempty output, flags
and tokens follow `body-codec-v1.md`. Reaching L bytes is insufficient until
the final cursor, remaining-copy and unused-flag checks all succeed.

### Recipe 203: bounded construction example

```text
header=ZERO_BYTES(3)
header=emit(20,BYTES,3,[header,U16(0),U8(3)])
header=emit(20,BYTES,3,[header,U16(2),U8(8)])
prefix=CAT(BYTES,12,header,1)
encoded=CAT(BYTES,B,prefix,ZERO_BYTES(B-12))
length_good=LE(2,U16(9))
safe_length=SEL(UINT,16,length_good,2,U16(0))
encoded_length=ADD16(safe_length,U16(3))
(state,target)=INITIALIZE(encoded,encoded_length,length_good)
state=ITER(state,201,8)
FINALIZE(state,encoded_length,target,8,false)
```

The full-sized buffers are constructed by the carried operations. The example
does not introduce a host decompression operation, hidden loop, alternative
codec, or a new literal-example encoding. The small logical input and expected
output suffice for existing WORKED/HELD framing; the wrapper program remains
fully charged.

## Manual vectors and audited construction totals

For recipe 203, input body `00 31 32 33 34 35 36 37 38`, length `0009`, returns
status `0000` and `31 32 33 34 35 36 37 38`. Body
`40 41 00 04 00 00 00 00 00`, length `0004`, returns `0000` and eight `41`
bytes; changing any of the last five padding bytes does not change that result.
Changing its flags `40` to `41` rejects unused flags; changing its length to
`0005` rejects trailing input. Both return `0003` with no data. Initial copy
body `80 00 05` followed by six padding bytes, length `0003`, rejects a copy
before any output with the same atomic result.

| Recipe | Nodes | v0 record bytes | Compact-v1 record bytes | Steps | Peak live scratch bytes |
|---:|---:|---:|---:|---:|---:|
| 201 | 145 | 4720 | 1774 | 145 | 65604 |
| 202 | 96 | 3164 | 1218 | 2375776 | 98394 |
| 203 | 133 | 4336 | 1584 | 1293 | 98398 |

The three programs total 374 nodes and 4576 compact record bytes. A standalone
diagnostic package with the tables above is 13101 v0 bytes or 5457 compact
bytes. Standalone diagnostic generation uses profile 7. Production profile-8
composition appends the immutable logical programs to its own base program
set and validates through the new explicit profile-8 admission; it must not
pass profile 8 through the old public profile-1..7 parser.

These totals are audited construction checks, not a passing carrier result.
The complete package and route must charge their own headers, tables, examples,
definitions, composition and four sector copies. Existing maxima remain
1048576 package bytes, 65535 nodes, 262140 edges, 1048576 iterations,
268435456 primitive steps and 16777216 live scratch bytes. The body codec still
admits at most 16384 encoded and decoded bytes. The carrier remains bounded
by 2048 squared bits. Neither this recipe owner nor its diagnostic tests lift
any of those limits.
