#!/usr/bin/env python3
"""
Rewrite pg_textsearch's GCC-only trailing struct attributes into a form MSVC also accepts, WITHOUT changing
binary layout. Applied to the upstream clone by .github/workflows/build-pg-textsearch.yml on every platform —
not just Windows — so the layout assertions this injects are verified by the GCC builds too.

Sizes below were measured from an unpatched clang build against PostgreSQL 17 and match the sizes stated in
upstream's own comments. They are asserted at compile time on every platform.

Usage: apply-portable-packing.py <upstream-clone-dir> <tp_portable.h>
"""
import os, re, shutil, sys

# (header, struct, kind, arg, sizeof, alignof)
STRUCTS = [
    ("src/memtable/expull.h",  "TpExpullEntry",    "packed",  None,  7, 1),
    ("src/segment/segment.h",  "TpSegmentPosting", "packed",  None, 14, 1),
    ("src/segment/format.h",   "TpDictEntryV3",    "aligned", 4,    12, 4),
    ("src/segment/format.h",   "TpDictEntry",      "aligned", 8,    16, 8),
    ("src/segment/format.h",   "TpSkipEntryV3",    "packed",  None, 16, 1),
    ("src/segment/format.h",   "TpSkipEntry",      "packed",  None, 20, 1),
    ("src/segment/format.h",   "TpCtidMapEntry",   "packed",  None,  6, 1),
]

root, portable = sys.argv[1], sys.argv[2]
shutil.copyfile(portable, os.path.join(root, "src", "tp_portable.h"))

def ensure_include(path):
    """Insert #include "tp_portable.h" after the file's first #include, once."""
    p = os.path.join(root, path)
    s = open(p).read()
    if '#include "tp_portable.h"' in s:
        return
    m = re.search(r'^#include .*$', s, re.M)
    if not m:
        sys.exit(f"{path}: no #include to anchor to")
    s = s[:m.end()] + '\n#include "tp_portable.h"' + s[m.end():]
    open(p, "w").write(s)

changed = 0
for path, name, kind, arg, size, align in STRUCTS:
    p = os.path.join(root, path)
    s = open(p).read()
    # Layout is load-bearing: prove it rather than assume it. Asserts sit OUTSIDE any pack region.
    asserts = (
        f'StaticAssertDecl(sizeof({name}) == {size}, "{name} layout changed — on-disk format break");\n'
        f'StaticAssertDecl(_Alignof({name}) == {align}, "{name} alignment changed — on-disk format break");'
    )
    if kind == "packed":
        trailer = f"}} __attribute__((packed)) {name};"
        if trailer not in s:
            sys.exit(f"{path}: expected trailing packed attribute on {name} — upstream changed, re-verify layout")
        # #pragma pack is honoured identically by GCC, Clang and MSVC.
        s = s.replace(f"typedef struct {name}\n", f"#pragma pack(push, 1)\ntypedef struct {name}\n", 1)
        s = s.replace(trailer, f"}} {name};\n#pragma pack(pop)\n{asserts}", 1)
    else:
        trailer = f"}} __attribute__((aligned({arg}))) {name};"
        if trailer not in s:
            sys.exit(f"{path}: expected trailing aligned attribute on {name} — upstream changed, re-verify layout")
        s = s.replace(f"typedef struct {name}\n", f"typedef struct TP_ALIGNED({arg}) {name}\n", 1)
        s = s.replace(trailer, f"}} {name};\n{asserts}", 1)
    open(p, "w").write(s)
    changed += 1

for path in sorted({p for p, *_ in STRUCTS}):
    ensure_include(path)

# __attribute__((unused)) only silences warnings, but MSVC still cannot parse it.
for dirpath, _, files in os.walk(os.path.join(root, "src")):
    for f in files:
        if not f.endswith((".c", ".h")) or f == "tp_portable.h":
            continue
        p = os.path.join(dirpath, f)
        s = open(p).read()
        if "__attribute__((unused))" not in s:
            continue
        open(p, "w").write(s.replace("__attribute__((unused))", "TP_UNUSED"))
        ensure_include(os.path.relpath(p, root))

# PG_FUNCTION_INFO_V1(f) emits `extern PGDLLEXPORT Datum f(PG_FUNCTION_ARGS);`. MSVC then rejects the
# definition, which carries default linkage, as C2375 "redefinition; different linkage". PGDLLEXPORT expands to
# nothing off Windows, so marking the definitions is portable.
v1_names = []
for dirpath, _, files in os.walk(os.path.join(root, "src")):
    for f in files:
        if f.endswith(".c"):
            src = open(os.path.join(dirpath, f)).read()
            v1_names += re.findall(r"PG_FUNCTION_INFO_V1\(\s*(\w+)\s*\)", src)

exported = 0
for name in sorted(set(v1_names)):
    hit = False
    for dirpath, _, files in os.walk(os.path.join(root, "src")):
        for f in files:
            if not f.endswith(".c"):
                continue
            p = os.path.join(dirpath, f)
            src = open(p).read()
            # Definition only (followed by `{`). The arg list may carry extra macros, e.g.
            # `(PG_FUNCTION_ARGS pg_attribute_unused())`, so consume to the last `)` on the line.
            pat = re.compile(r"(?<!PGDLLEXPORT )\bDatum(\s+)" + re.escape(name)
                             + r"\(PG_FUNCTION_ARGS([^\n]*)\)(\s*\{)")
            src2, n = pat.subn(r"PGDLLEXPORT Datum\1" + name + r"(PG_FUNCTION_ARGS\2)\3", src)
            if n:
                open(p, "w").write(src2)
                exported += n
                hit = True
    if not hit:
        sys.exit(f"PG_FUNCTION_INFO_V1({name}) has no matching definition to export — MSVC would reject it")

# If upstream introduces a new GCC attribute, fail here rather than on a Windows runner — or worse, silently.
leftover = []
for dirpath, _, files in os.walk(os.path.join(root, "src")):
    for f in files:
        if f.endswith((".c", ".h")) and f != "tp_portable.h" \
                and "__attribute__" in open(os.path.join(dirpath, f)).read():
            leftover.append(os.path.relpath(os.path.join(dirpath, f), root))
if leftover:
    sys.exit("unhandled __attribute__ remains in: " + ", ".join(sorted(leftover)))

print(f"portable-packing: rewrote {changed} structs, exported {exported} V1 functions; no __attribute__ remains")
