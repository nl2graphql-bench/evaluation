"""Control for the 2026_eval.py (split, DataID) keying fix.

Run:  EVALS_DIR=2026_evals .venv/bin/python test_2026_eval_split_keying.py
Exits non-zero if the split-aware loader ever returns the wrong split's schema.
Replicates BOTH loaders over the real 6 committed xlsx and asks: for a test_main
DataID, do we get test_main's schema or part2's?
"""
import glob, os, sys, pandas as pd
D=os.environ.get("EVALS_DIR", "2026_evals")
files=sorted(glob.glob(D+"/*.xlsx"))
print(f"xlsx present: {len(files)}")

# --- OLD loader (origin/main): one flat dict keyed by DataID, every file ---
old={}
for p in files:
    df=pd.read_excel(p)
    for _,r in df.iterrows():
        old[r["DataID"]]={"CleanSchema":r.get("CleanSchema",""),"src":os.path.basename(p)}

# --- NEW loader: (split, DataID), clean preferred, one file per split ---
SPLIT={"test_main":"test_main","test_part2":"test_part2"}
def split_of(p):
    n=os.path.basename(p)
    for s,v in SPLIT.items():
        if n.startswith(s): return v
def rank(p):
    n=os.path.basename(p)
    return 0 if "_clean_backup" in n else (2 if "_clean" in n else 1)
chosen={}
for p in files:
    s=split_of(p)
    if s is None: continue
    if s in chosen and rank(chosen[s])>=rank(p): continue
    chosen[s]=p
new={}
for s,p in chosen.items():
    df=pd.read_excel(p)
    for _,r in df.iterrows():
        new[(s,r["DataID"])]={"CleanSchema":r.get("CleanSchema",""),"src":os.path.basename(p)}

print("\nNEW loader picked:")
for s,p in sorted(chosen.items()): print(f"  {s:11s} <- {os.path.basename(p)}")

# truth: test_main's own clean schema per DataID
truth={}
for _,r in pd.read_excel(D+"/test_main_clean.xlsx").iterrows():
    truth[r["DataID"]]=r.get("CleanSchema","")

ids=sorted(truth)[:1845]
old_wrong=sum(1 for i in ids if str(old.get(i,{}).get("CleanSchema",""))!=str(truth[i]))
new_wrong=sum(1 for i in ids if str(new.get(("test_main",i),{}).get("CleanSchema",""))!=str(truth[i]))
print(f"\ntest_main ids checked: {len(ids)}")
print(f"  OLD loader WRONG schema for: {old_wrong}/{len(ids)}  ({100*old_wrong/len(ids):.1f}%)")
print(f"  NEW loader WRONG schema for: {new_wrong}/{len(ids)}  ({100*new_wrong/len(ids):.1f}%)")
srcs=set(old.get(i,{}).get("src") for i in ids)
print(f"  OLD loader sourced test_main ids from: {srcs}")

sys.exit(0 if new_wrong == 0 else 1)
