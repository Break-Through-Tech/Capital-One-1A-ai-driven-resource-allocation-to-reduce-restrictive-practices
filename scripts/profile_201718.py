"""Extract and profile the CRDC 2017-18 core modules (Phase 1, read-only on sources).

Steps:
  1. Extract the five core module CSVs and the 2017-18 documentation files from the
     package zip into data/raw_extracted/2017-18/ (original filenames, flat folder).
     Already-extracted files are re-verified by hash instead of rewritten.
  2. Record SHA-256 hashes of the zip, every extracted file, and the 2017-18
     definitions PDF.
  3. Profile each module CSV: encoding, raw line/record counts vs pandas rows, headers,
     required-field presence, ID validity, cross-module keys, numeric fields (every
     negative code), and category fields.

Prints a compact text report and also writes it to --report. Never prints whole CSVs.

Usage:
  python scripts/profile_201718.py
  python scripts/profile_201718.py --zip <path> --raw-dir <dir> --report <file>
"""

import argparse
import csv
import hashlib
import io
import re
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PKG = "2017-18-crdc-data-corrected-publication 2/2017-18 Public-Use Files"

MODULES = {
    "C": f"{PKG}/Data/SCH/CRDC/CSV/School Characteristics.csv",
    "E": f"{PKG}/Data/SCH/CRDC/CSV/Enrollment.csv",
    "R": f"{PKG}/Data/SCH/CRDC/CSV/Restraint and Seclusion.csv",
    "S": f"{PKG}/Data/SCH/CRDC/CSV/School Support.csv",
    "L": f"{PKG}/Data/LEA/CRDC/CSV/LEA Characteristics.csv",
}
MODULE_NAMES = {"C": "School Characteristics", "E": "Enrollment",
                "R": "Restraint and Seclusion", "S": "School Support",
                "L": "LEA Characteristics"}
DOCS = [
    f"{PKG}/Documentation/2017-18 CRDC Public Data File Manual.pdf",
    f"{PKG}/Documentation/2017-18 CRDC Technical Document.pdf",
    f"{PKG}/Documentation/2017-18 CRDC File Structure.xlsx",
    f"{PKG}/Documentation/Appndx C. Post-Sub Data Quality Checks.xlsx",
]

# Raw fields from the 2017-18 column of playbook section 2.1 (grade flags resolved below).
REQUIRED = {
    "C": ["LEAID", "SCHID", "COMBOKEY", "LEA_STATE", "SCH_NAME", "JJ",
          "SCH_STATUS_SPED", "SCH_STATUS_CHARTER", "SCH_STATUS_ALT", "SCH_STATUS_MAGNET",
          "SCH_GRADE_KG"],
    "E": ["LEAID", "SCHID", "COMBOKEY", "TOT_ENR_M", "TOT_ENR_F",
          "SCH_ENR_IDEA_M", "SCH_ENR_IDEA_F", "SCH_ENR_504_M", "SCH_ENR_504_F",
          "SCH_ENR_LEP_M", "SCH_ENR_LEP_F"],
    "R": ["LEAID", "COMBOKEY", "SCH_RSINSTANCES_SECL_WODIS",
          "SCH_RSINSTANCES_SECL_IDEA", "SCH_RSINSTANCES_SECL_504"],
    "S": ["LEAID", "SCHID", "COMBOKEY", "SCH_FTETEACH_TOT", "SCH_FTECOUNSELORS",
          "SCH_FTESERVICES_NUR", "SCH_FTESERVICES_PSY", "SCH_FTESERVICES_SOC",
          "SCH_FTESECURITY_LEO", "SCH_FTESECURITY_GUA"],
    "L": ["LEAID", "LEA_NAME", "LEA_STATE", "LEA_ENR", "LEA_SCHOOLS"],
}
# Fields the docs say are absent in 2017-18 or that section 8 asks about.
PRESENCE_CHECKS = {
    "C": ["SCH_VIRT_IND", "SCH_JUST_IND"],
    "E": ["TOT_ENR_X", "SCH_ENR_EL_M", "SCH_ENR_EL_F", "SCH_ENR_IDEA_X", "SCH_ENR_504_X"],
    "S": ["SCH_FTETEACH_CERT", "SCH_FTETEACH_NOTCERT", "SCH_FTETEACH_FY",
          "SCH_FTETEACH_SY", "SCH_FTETEACH_ABSENT", "SCH_TEACHERS_CURR_TOT",
          "SCH_TEACHERS_PREV_TOT"],
}
COUNT_FIELDS = {
    "E": ["TOT_ENR_M", "TOT_ENR_F", "SCH_ENR_IDEA_M", "SCH_ENR_IDEA_F",
          "SCH_ENR_504_M", "SCH_ENR_504_F", "SCH_ENR_LEP_M", "SCH_ENR_LEP_F"],
    "R": ["SCH_RSINSTANCES_SECL_WODIS", "SCH_RSINSTANCES_SECL_IDEA",
          "SCH_RSINSTANCES_SECL_504"],
    "L": ["LEA_ENR", "LEA_SCHOOLS"],
}
FTE_FIELDS = ["SCH_FTETEACH_TOT", "SCH_FTECOUNSELORS", "SCH_FTESERVICES_NUR",
              "SCH_FTESERVICES_PSY", "SCH_FTESERVICES_SOC", "SCH_FTESECURITY_LEO",
              "SCH_FTESECURITY_GUA"]
SECL = REQUIRED["R"][2:]
ID_LEN = {"LEAID": 7, "SCHID": 5, "COMBOKEY": 12}
NUMERIC_RE = re.compile(r"^-?(\d+\.?\d*|\.\d+)$")

_lines = []


def out(*parts):
    line = " ".join(str(p) for p in parts)
    print(line)
    _lines.append(line)


def section(title):
    out("")
    out("=" * 78)
    out(title)
    out("=" * 78)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- extraction
def extract(zip_path, raw_dir):
    section("1. EXTRACTION AND HASHES")
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_abs = zip_path.resolve()  # project-relative path if inside the project, else the file name only
    out(f"zip: {zip_abs.relative_to(ROOT) if zip_abs.is_relative_to(ROOT) else zip_path.name}")
    out(f"  sha256 {sha256_file(zip_path)}  size {zip_path.stat().st_size:,}")
    with zipfile.ZipFile(zip_path) as z:
        for member in list(MODULES.values()) + DOCS:
            info = z.getinfo(member)  # KeyError if the expected path is absent
            target = raw_dir / Path(member).name
            data = z.read(member)  # zipfile verifies the stored CRC-32 on read
            new_hash = hashlib.sha256(data).hexdigest()
            if target.exists() and sha256_file(target) == new_hash:
                status = "already present, hash verified"
            else:
                target.write_bytes(data)
                status = "extracted"
            out(f"  {target.relative_to(ROOT)}")
            out(f"    sha256 {new_hash}  size {info.file_size:,}  ({status})")


def hash_definitions(defs_pdf):
    out(f"definitions PDF: {defs_pdf.relative_to(ROOT)}")
    out(f"  sha256 {sha256_file(defs_pdf)}  size {defs_pdf.stat().st_size:,}")


# ---------------------------------------------------------------- reading
def decode(raw):
    """Return (text, encoding, note). Strict decoding, fixed fallback order."""
    try:
        return raw.decode("utf-8-sig"), "utf-8-sig", ""
    except UnicodeDecodeError as e:
        utf8_err = f"utf-8 failed at byte {e.start} (0x{raw[e.start]:02x})"
    try:
        return raw.decode("cp1252"), "cp1252", utf8_err
    except UnicodeDecodeError as e:
        note = f"{utf8_err}; cp1252 failed at byte {e.start} (0x{raw[e.start]:02x})"
        return raw.decode("latin-1"), "latin-1", note


def read_module(path):
    raw = path.read_bytes()
    text, enc, note = decode(raw)
    stats = {
        "bytes": len(raw),
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "encoding": enc,
        "note": note,
        "newlines": text.count("\n"),
        "crlf": text.count("\r\n"),
        "ends_with_newline": text.endswith("\n"),
        "blank_lines": sum(1 for ln in text.splitlines() if ln.strip() == ""),
    }
    # csv-module pass: record count, field-count distribution, quoted newlines
    records = list(csv.reader(io.StringIO(text, newline="")))
    stats["csv_records"] = len(records)
    stats["csv_empty_records"] = sum(1 for r in records if len(r) == 0 or all(f.strip() == "" for f in r))
    stats["field_counts"] = Counter(len(r) for r in records)
    stats["fields_with_newline"] = sum(1 for r in records for f in r if "\n" in f or "\r" in f)
    stats["records_with_newline_examples"] = [
        (i, [f for f in r if "\n" in f or "\r" in f][0][:80])
        for i, r in enumerate(records) if any("\n" in f or "\r" in f for f in r)][:5]
    nonascii = Counter(ch for ch in text if ord(ch) > 127)
    stats["nonascii"] = nonascii

    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False,
                     na_filter=False)
    before = df.copy()
    df = df.apply(lambda s: s.str.strip())
    stats["strip_changed"] = {c: int((before[c] != df[c]).sum())
                              for c in df.columns if (before[c] != df[c]).any()}
    stats["empty_rows"] = int((df == "").all(axis=1).sum())
    return df, stats, records[0] if records else []


def report_read(key, path, df, stats, header):
    section(f"2.{key} FILE: {MODULE_NAMES[key]}  ({path.relative_to(ROOT)})")
    out(f"bytes {stats['bytes']:,}; BOM {stats['bom']}; encoding used: {stats['encoding']}"
        + (f"  [{stats['note']}]" if stats["note"] else ""))
    if stats["nonascii"]:
        top = ", ".join(f"{ch!r} U+{ord(ch):04X} x{n}" for ch, n in stats["nonascii"].most_common(12))
        out(f"non-ASCII characters after decoding ({sum(stats['nonascii'].values()):,} total, "
            f"{len(stats['nonascii'])} distinct): {top}")
    else:
        out("non-ASCII characters after decoding: none")
    out(f"raw: newline chars {stats['newlines']:,} (CRLF {stats['crlf']:,}); ends with newline "
        f"{stats['ends_with_newline']}; blank lines {stats['blank_lines']:,}")
    out(f"csv module: records incl. header {stats['csv_records']:,}; empty records "
        f"{stats['csv_empty_records']:,}; fields containing a line break "
        f"{stats['fields_with_newline']:,}")
    out(f"csv field-count distribution: {dict(stats['field_counts'])}")
    for i, frag in stats["records_with_newline_examples"]:
        out(f"  quoted line break, csv record #{i} (0 = header): {frag!r}")
    out(f"pandas: {len(df):,} rows x {df.shape[1]} cols; fully empty rows after strip "
        f"{stats['empty_rows']:,}")
    out(f"whitespace stripped (cells changed per column): {stats['strip_changed'] or 'none'}")
    dup_cols = [c for c, n in Counter(header).items() if n > 1]
    out(f"duplicate header names: {dup_cols or 'none'}")
    out(f"header ({len(df.columns)}): " + ", ".join(df.columns))


# ---------------------------------------------------------------- IDs
def id_profile(key, df):
    out(f"ID checks ({MODULE_NAMES[key]}):")
    valid = {}
    for col, n in ID_LEN.items():
        if col not in df.columns:
            out(f"  {col}: (column absent)")
            continue
        s = df[col]
        blank = s == ""
        nondigit = ~blank & ~s.str.fullmatch(r"\d+")
        toolong = ~blank & ~nondigit & (s.str.len() > n)
        lens = dict(sorted(Counter(s[~blank & ~nondigit].str.len()).items()))
        out(f"  {col}: blank {int(blank.sum())}, non-digit {int(nondigit.sum())}, "
            f"too long (>{n}) {int(toolong.sum())}; raw length distribution {lens}")
        if nondigit.any():
            out(f"    non-digit examples: {s[nondigit].unique()[:5].tolist()}")
        valid[col] = ~blank & ~nondigit & ~toolong
    if "COMBOKEY" in df.columns:
        ck = df["COMBOKEY"]
        dups = ck[ck.duplicated(keep=False)]
        out(f"  duplicate COMBOKEY: {dups.nunique()} keys on {len(dups)} rows")
    if "LEAID" in df.columns and key == "L":
        dups = df["LEAID"][df["LEAID"].duplicated(keep=False)]
        out(f"  duplicate LEAID: {dups.nunique()} keys on {len(dups)} rows")
    if all(c in df.columns for c in ID_LEN):
        ok = valid["LEAID"] & valid["SCHID"] & valid["COMBOKEY"]
        built = df["LEAID"].str.zfill(7) + df["SCHID"].str.zfill(5)
        ck12 = df["COMBOKEY"].str.zfill(12)
        mism = ok & (built != ck12)
        lea_part = ok & (df["LEAID"].str.zfill(7) != ck12.str[:7])
        sch_part = ok & (df["SCHID"].str.zfill(5) != ck12.str[7:])
        out(f"  COMBOKEY == LEAID.zfill(7)+SCHID.zfill(5): checked {int(ok.sum()):,}, "
            f"mismatches {int(mism.sum()):,} (LEAID part {int(lea_part.sum()):,}, "
            f"SCHID part {int(sch_part.sum()):,})")
        if mism.any():
            ex = df.loc[mism, ["COMBOKEY", "LEAID", "SCHID"]].head(5)
            for _, r in ex.iterrows():
                out(f"    e.g. COMBOKEY {r.COMBOKEY} LEAID {r.LEAID} SCHID {r.SCHID}")


def cross_module(dfs):
    section("3. CROSS-MODULE KEYS AND IDENTITY FIELDS")
    c = dfs["C"].set_index("COMBOKEY")
    keys_c = set(c.index)
    for key in ["E", "R", "S"]:
        d = dfs[key]
        keys = set(d["COMBOKEY"])
        out(f"{MODULE_NAMES[key]} vs Characteristics: shared {len(keys & keys_c):,}; "
            f"only in Characteristics {len(keys_c - keys):,}; only in {MODULE_NAMES[key]} "
            f"{len(keys - keys_c):,}")
        m = d.set_index("COMBOKEY")
        common = sorted(keys & keys_c)
        for col in ["LEAID", "SCHID", "LEA_STATE", "LEA_NAME", "SCH_NAME", "JJ"]:
            if col in m.columns and col in c.columns:
                a, b = m.loc[common, col], c.loc[common, col]
                diff = a != b
                out(f"  {col} disagreements on shared keys: {int(diff.sum()):,}")
                if diff.any():
                    ex = pd.DataFrame({"char": b[diff], key: a[diff]}).head(5)
                    for k, r in ex.iterrows():
                        out(f"    {k}: Characteristics {r['char']!r} vs {key} {r[key]!r}")
        if key == "R":
            rs = m.loc[common, "SCHID"]
            out(f"  R.SCHID == COMBOKEY[-5:]: {int((rs.str.zfill(5) == pd.Index(common).str[-5:]).sum()):,} "
                f"of {len(common):,}")

    section("4. SCHOOL -> LEA")
    lea = dfs["L"]
    lea_keys = set(lea["LEAID"])
    sch_leas = set(dfs["C"]["LEAID"])
    rows_found = dfs["C"]["LEAID"].isin(lea_keys)
    out(f"distinct school LEAIDs (Characteristics) {len(sch_leas):,}; found in LEA file "
        f"{len(sch_leas & lea_keys):,}; not found {len(sch_leas - lea_keys):,}")
    out(f"school rows whose LEAID is in LEA file: {int(rows_found.sum()):,} of {len(dfs['C']):,}")
    if (~rows_found).any():
        out(f"  unmatched LEAID examples: {sorted(sch_leas - lea_keys)[:10]}")
    out(f"LEA rows with no school in Characteristics: {len(lea_keys - sch_leas):,}")
    li = lea.set_index("LEAID")
    m = dfs["C"][rows_found]
    for col in ["LEA_STATE", "LEA_NAME"]:
        sch_v = m[col].values
        lea_v = li.loc[m["LEAID"], col].values
        exact = sch_v != lea_v
        norm = pd.Series(sch_v).str.upper().str.split().str.join(" ").values != \
            pd.Series(lea_v).str.upper().str.split().str.join(" ").values
        out(f"{col} school vs LEA: exact-string disagreements {int(exact.sum()):,} rows "
            f"({m.loc[exact, 'LEAID'].nunique():,} LEAIDs); after case/space normalization "
            f"{int(norm.sum()):,} rows ({m.loc[norm, 'LEAID'].nunique():,} LEAIDs)")
        shown = set()
        for i in range(len(m)):
            if exact[i] and m["LEAID"].iat[i] not in shown:
                shown.add(m["LEAID"].iat[i])
                out(f"  LEAID {m['LEAID'].iat[i]}: school {sch_v[i]!r} vs LEA {lea_v[i]!r}")
                if len(shown) == 5:
                    break
    for name, d in [("Characteristics", dfs["C"]), ("LEA", lea)]:
        st = d["LEA_STATE"].value_counts()
        out(f"LEA_STATE distinct in {name}: {len(st)}; PR present {'PR' in st.index}; "
            f"values {sorted(st.index)}")


# ---------------------------------------------------------------- numerics
def numeric_profile(df, col, is_count, label_cols):
    s = df[col]
    blank = s == ""
    isnum = s.str.fullmatch(NUMERIC_RE.pattern)
    nonnum = ~blank & ~isnum
    v = pd.to_numeric(s.where(isnum), errors="coerce")
    neg = v < 0
    valid = v >= 0
    neg_codes = dict(sorted(Counter(s[neg]).items(), key=lambda kv: float(kv[0]), reverse=True))
    frac = valid & (v % 1 != 0)
    line = (f"  {col}: n {len(s):,}; valid>=0 {int(valid.sum()):,}; zero {int((v == 0).sum()):,}; "
            f">0 {int((v > 0).sum()):,}; blank {int(blank.sum())}; non-numeric {int(nonnum.sum())}; "
            f"negative codes {neg_codes}; "
            f"{'non-integer' if is_count else 'fractional'} {int(frac.sum()):,}; "
            f"min {v[valid].min() if valid.any() else 'NA'}; max {v[valid].max() if valid.any() else 'NA'}")
    out(line)
    if nonnum.any():
        out(f"    non-numeric values: {Counter(s[nonnum]).most_common(10)}")
    if is_count and frac.any():
        out(f"    non-integer examples: {s[frac].head(5).tolist()}")
    if not is_count and valid.any():
        top = df.loc[v[valid].sort_values(ascending=False).index[:3], label_cols]
        for idx, r in top.iterrows():
            out(f"    top: {s[idx]} | " + " | ".join(str(r[c]) for c in label_cols))
    return v


def numerics(dfs):
    section("5. COUNT AND FTE FIELDS (valid = parses as a number and >= 0)")
    vals = {}
    for key in ["E", "R", "L"]:
        out(f"{MODULE_NAMES[key]}:")
        for col in COUNT_FIELDS[key]:
            vals[col] = numeric_profile(dfs[key], col, True, [])
    out("School Support (FTE):")
    for col in FTE_FIELDS:
        vals[col] = numeric_profile(dfs["S"], col, False, ["COMBOKEY", "SCH_NAME", "LEA_NAME", "LEA_STATE"])

    out("")
    out("Seclusion instance triple (Restraint and Seclusion):")
    r = dfs["R"]
    v = pd.DataFrame({c: vals[c] for c in SECL})
    all_valid = (v >= 0).all(axis=1)
    out(f"  rows {len(r):,}; all three >= 0: {int(all_valid.sum()):,}; any negative: "
        f"{int((v < 0).any(axis=1).sum()):,}")
    any9 = (r[SECL] == "-9").any(axis=1)
    out(f"  rows with -9 on any instance field: {int(any9.sum()):,}; all three -9: "
        f"{int((r[SECL] == '-9').all(axis=1).sum()):,}")
    out(f"  WODIS > 0: {int((v[SECL[0]] > 0).sum()):,}; IDEA > 0: {int((v[SECL[1]] > 0).sum()):,}; "
        f"504 > 0: {int((v[SECL[2]] > 0).sum()):,}; triple-valid with sum > 0: "
        f"{int((all_valid & (v.sum(axis=1) > 0)).sum()):,}")
    pat = r[SECL].apply(lambda row: tuple(x if x.startswith("-") else ">=0" for x in row), axis=1)
    out("  code patterns (WODIS, IDEA, 504) -> rows:")
    for p, n in Counter(pat).most_common():
        out(f"    {p}: {n:,}")
    jj = dfs["C"].set_index("COMBOKEY")["JJ"].reindex(r["COMBOKEY"]).values
    ct = pd.crosstab(pd.Series(jj, name="JJ"),
                     pd.Series(r[SECL[0]].where(~r[SECL[0]].str.startswith("-"), r[SECL[0]])
                               .where(r[SECL[0]].str.startswith("-"), ">=0").values, name="WODIS"))
    out("  JJ x WODIS code:")
    for line in ct.to_string().splitlines():
        out("    " + line)

    out("")
    e = dfs["E"]
    m, f = vals["TOT_ENR_M"], vals["TOT_ENR_F"]
    both = (m >= 0) & (f >= 0)
    tot = m + f
    out(f"Enrollment: TOT_ENR_M usable {int((m >= 0).sum()):,}; TOT_ENR_F usable "
        f"{int((f >= 0).sum()):,}; both usable {int(both.sum()):,}; M+F == 0 "
        f"{int((both & (tot == 0)).sum()):,}; 0 < M+F < 10 {int((both & (tot > 0) & (tot < 10)).sum()):,}")
    for sub in ["IDEA", "504", "LEP"]:
        sm, sf = vals[f"SCH_ENR_{sub}_M"], vals[f"SCH_ENR_{sub}_F"]
        sb = (sm >= 0) & (sf >= 0)
        over = sb & both & (sm + sf > tot)
        out(f"  {sub}: M and F both usable {int(sb.sum()):,}; subgroup > total (both totals usable) "
            f"{int(over.sum()):,}")
        if over.any():
            ex = e.loc[over, ["COMBOKEY", "TOT_ENR_M", "TOT_ENR_F", f"SCH_ENR_{sub}_M", f"SCH_ENR_{sub}_F"]].head(3)
            for _, rr in ex.iterrows():
                out("    e.g. " + ", ".join(f"{k}={rr[k]}" for k in ex.columns))

    out("")
    out("FTE review triggers (teachers > 2,000; other core FTE > 200), every triggering row:")
    s = dfs["S"]
    for col in FTE_FIELDS:
        cut = 2000 if col == "SCH_FTETEACH_TOT" else 200
        hit = vals[col] > cut
        out(f"  {col} > {cut}: {int(hit.sum())}")
        for idx in vals[col][hit].sort_values(ascending=False).index:
            out(f"    {s.at[idx, col]} | {s.at[idx, 'COMBOKEY']} | {s.at[idx, 'SCH_NAME']} | "
                f"{s.at[idx, 'LEA_NAME']} | {s.at[idx, 'LEA_STATE']}")
    return vals


# ---------------------------------------------------------------- string fields
def string_profile(dfs):
    section("6b. STRING FIELDS (playbook 2.1: lea_state, sch_name from C; lea_name from L)")
    for key, cols in [("C", ["LEA_STATE", "SCH_NAME", "LEA_NAME"]), ("L", ["LEA_STATE", "LEA_NAME"])]:
        for col in cols:
            s = dfs[key][col]
            ctrl = s.str.contains(r"[\x00-\x1f\x7f-\x9f]", regex=True)
            nonascii = s.str.contains(r"[^\x00-\x7f]", regex=True)
            line = (f"  {MODULE_NAMES[key]}.{col}: blank {int((s == '').sum())}; distinct {s.nunique():,}; "
                    f"length min {s.str.len().min()} max {s.str.len().max()}; "
                    f"rows with non-ASCII {int(nonascii.sum())}; rows with control chars {int(ctrl.sum())}; "
                    f"internal double spaces {int(s.str.contains('  ', regex=False).sum())}")
            if col == "LEA_STATE":
                line += (f"; not 2 uppercase letters {int((~s.str.fullmatch(r'[A-Z]{2}')).sum())}")
            out(line)
            if nonascii.any():
                for v in s[nonascii].unique()[:6]:
                    out(f"    non-ASCII value: {v!r}")
    c = dfs["C"]
    out(f"  duplicate (LEAID, SCH_NAME) pairs in Characteristics: "
        f"{int(c.duplicated(['LEAID', 'SCH_NAME'], keep=False).sum())} rows "
        f"(names are not keys; FYI only)")


# ---------------------------------------------------------------- follow-ups
def follow_ups(dfs, vals):
    section("7. FOLLOW-UP CHECKS")
    c = dfs["C"]

    out("Non-digit IDs (Characteristics):")
    nd = ~c["LEAID"].str.fullmatch(r"\d+")
    shape = c.loc[nd, "LEAID"].str.replace(r"\d", "9", regex=True).str.replace(r"[A-Z]", "A", regex=True)
    out(f"  rows {int(nd.sum())}; distinct LEAIDs {c.loc[nd, 'LEAID'].nunique()}; LEAID shapes "
        f"{dict(Counter(shape))}; states {dict(Counter(c.loc[nd, 'LEA_STATE']))}")
    out(f"  SCHID values on these rows: {dict(Counter(c.loc[nd, 'SCHID']).most_common(5))}")
    for _, r in c[nd].head(5).iterrows():
        out(f"    {r.COMBOKEY} | LEAID {r.LEAID} | SCHID {r.SCHID} | {r.SCH_NAME} | {r.LEA_NAME}")
    cat = c["LEAID"] + c["SCHID"]
    out(f"  COMBOKEY == LEAID + SCHID as plain strings, ALL rows: mismatches "
        f"{int((cat != c['COMBOKEY']).sum())} of {len(c):,}")
    lea_nd = ~dfs["L"]["LEAID"].str.fullmatch(r"\d+")
    out(f"  LEA file: non-digit LEAIDs {int(lea_nd.sum())}; states {dict(Counter(dfs['L'].loc[lea_nd, 'LEA_STATE']))}")
    rkeys = set(c.loc[nd, "COMBOKEY"])
    r = dfs["R"]
    in_r = r["COMBOKEY"].isin(rkeys)
    triple_ok = pd.DataFrame({k: vals[k] for k in SECL})[in_r.values].ge(0).all(axis=1)
    e_in = dfs["E"]["COMBOKEY"].isin(rkeys)
    out(f"  these schools: seclusion triple valid {int(triple_ok.sum())} of {int(in_r.sum())}; "
        f"TOT_ENR_M and F valid {int(((vals['TOT_ENR_M'] >= 0) & (vals['TOT_ENR_F'] >= 0))[e_in].sum())}")

    out("")
    out("Rows with a negative code on TOT_ENR_M or TOT_ENR_F:")
    e = dfs["E"]
    neg = e["TOT_ENR_M"].str.startswith("-") | e["TOT_ENR_F"].str.startswith("-")
    for _, rr in e[neg].iterrows():
        out(f"  {rr.COMBOKEY} | {rr.SCH_NAME} | {rr.LEA_STATE} | M {rr.TOT_ENR_M} F {rr.TOT_ENR_F} | "
            f"IDEA_M {rr.SCH_ENR_IDEA_M} LEP_M {rr.SCH_ENR_LEP_M}")

    out("")
    out("Seclusion code pattern x SCH_STATUS_SPED (patterns containing -5):")
    pat = r[SECL].apply(lambda row: "/".join(x if x.startswith("-") else "ok" for x in row), axis=1)
    sped = c.set_index("COMBOKEY")["SCH_STATUS_SPED"].reindex(r["COMBOKEY"]).values
    jj = c.set_index("COMBOKEY")["JJ"].reindex(r["COMBOKEY"]).values
    has5 = pat.str.contains("-5")
    ct = pd.crosstab(pd.Series(pat[has5].values, name="pattern WODIS/IDEA/504"), pd.Series(sped[has5.values], name="SPED"))
    for line in ct.to_string().splitlines():
        out("    " + line)
    ct = pd.crosstab(pd.Series(pat[has5].values, name="pattern WODIS/IDEA/504"), pd.Series(jj[has5.values], name="JJ"))
    for line in ct.to_string().splitlines():
        out("    " + line)
    # Non-IDEA enrollment for schools coded -5 on WODIS but valid on IDEA
    target = r.loc[pat == "-5/ok/-5", "COMBOKEY"]
    em = e.set_index("COMBOKEY").loc[target]
    tot = pd.to_numeric(em["TOT_ENR_M"]) + pd.to_numeric(em["TOT_ENR_F"])
    idea = pd.to_numeric(em["SCH_ENR_IDEA_M"]) + pd.to_numeric(em["SCH_ENR_IDEA_F"])
    nonidea = tot - idea
    out(f"  pattern -5/ok/-5 ({len(target)} schools): total enrollment - IDEA enrollment: "
        f"==0 {int((nonidea == 0).sum())}, <0 {int((nonidea < 0).sum())}, >0 {int((nonidea > 0).sum())}; "
        f"max {nonidea.max()}")

    out("")
    out("Security FTE reserved codes x JJ:")
    s = dfs["S"]
    for col in ["SCH_FTESECURITY_LEO", "SCH_FTESECURITY_GUA", "SCH_FTETEACH_TOT"]:
        code = s[col].where(s[col].str.startswith("-"), "ok")
        ct = pd.crosstab(code.rename(col), s["JJ"])
        for line in ct.to_string().splitlines():
            out("    " + line)

    out("")
    out("Rows with negative codes on all core FTE fields simultaneously:")
    allneg = pd.DataFrame({k: vals[k] for k in FTE_FIELDS}).lt(0).all(axis=1)
    out(f"  {int(allneg.sum())}; codes: {dict(Counter(s.loc[allneg, 'SCH_FTETEACH_TOT']))}")

    out("")
    lea = dfs["L"]
    zero = lea[lea["LEA_SCHOOLS"] == "0"]
    nsch = c["LEAID"].value_counts()
    out(f"LEA_SCHOOLS == 0 ({len(zero)} LEAs) vs number of roster schools with that LEAID:")
    for _, rr in zero.iterrows():
        out(f"  {rr.LEAID} | {rr.LEA_NAME} | {rr.LEA_STATE} | LEA_ENR {rr.LEA_ENR} | roster schools {nsch.get(rr.LEAID, 0)}")
    neg = lea[lea["LEA_ENR"].str.startswith("-")]
    for _, rr in neg.iterrows():
        out(f"LEA_ENR negative: {rr.LEAID} | {rr.LEA_NAME} | {rr.LEA_STATE} | LEA_ENR {rr.LEA_ENR} | "
            f"LEA_SCHOOLS {rr.LEA_SCHOOLS} | roster schools {nsch.get(rr.LEAID, 0)}")
    out(f"LEA_SCHOOLS vs roster school count: equal {int((lea['LEA_SCHOOLS'] == lea['LEAID'].map(nsch).astype(str)).sum()):,} "
        f"of {len(lea):,}")


# ---------------------------------------------------------------- categories
def categories(dfs, grade_cols):
    section("6. CATEGORY FIELDS (raw values, repr shows spacing/case)")
    c = dfs["C"]
    cols = ["JJ", "SCH_STATUS_SPED", "SCH_STATUS_CHARTER", "SCH_STATUS_ALT",
            "SCH_STATUS_MAGNET"] + grade_cols
    for col in cols:
        vc = c[col].value_counts(dropna=False)
        out(f"  {col}: " + ", ".join(f"{k!r}: {v:,}" for k, v in vc.items()))
    known = c[grade_cols].isin(["Yes", "No"])
    out(f"  rows with any KG/G01-G12 flag not exactly 'Yes'/'No': {int((~known).any(axis=1).sum()):,}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--zip", type=Path, default=ROOT / "Data_Files" / "2017-18-crdc-data.zip")
    p.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw_extracted" / "2017-18")
    p.add_argument("--definitions", type=Path, default=ROOT / "Data_Files" /
                   "Documentation_Data_Definitions" / "2017-18_Master_List_of_CRDC_Definitions.pdf")
    p.add_argument("--report", type=Path, default=ROOT / "docs" / "cleaning" / "profile_201718.txt")
    args = p.parse_args()

    out(f"pandas {pd.__version__}")
    extract(args.zip, args.raw_dir)
    hash_definitions(args.definitions)

    dfs = {}
    for key, member in MODULES.items():
        path = args.raw_dir / Path(member).name
        df, stats, header = read_module(path)
        report_read(key, path, df, stats, header)
        dfs[key] = df

    section("2.X REQUIRED FIELDS (playbook 2.1, 2017-18 column)")
    grade_re = re.compile(r"^SCH_GRADE_G0?(\d{1,2})$")
    grade_cols = sorted([c for c in dfs["C"].columns if grade_re.match(c)],
                        key=lambda c: int(grade_re.match(c).group(1)))
    out(f"all SCH_GRADE_* headers: {[c for c in dfs['C'].columns if c.startswith('SCH_GRADE_')]}")
    out(f"grade 1-12 headers resolved: {grade_cols}")
    missing_any = False
    for key, cols in REQUIRED.items():
        miss = [c for c in cols if c not in dfs[key].columns]
        missing_any |= bool(miss)
        out(f"  {MODULE_NAMES[key]}: {len(cols) - len(miss)}/{len(cols)} present; missing {miss or 'none'}")
    if len(grade_cols) != 12:
        missing_any = True
        out(f"  grade 1-12 flags: expected 12, found {len(grade_cols)}")
    for key, cols in PRESENCE_CHECKS.items():
        out(f"  presence check {MODULE_NAMES[key]}: " +
            ", ".join(f"{c}={'present' if c in dfs[key].columns else 'absent'}" for c in cols))
    if missing_any:
        out("STOP: an expected column is missing (rule 7). Remaining checks skipped.")
    else:
        for key in ["C", "E", "R", "S", "L"]:
            section(f"2.ID {MODULE_NAMES[key]}")
            id_profile(key, dfs[key])
        cross_module(dfs)
        vals = numerics(dfs)
        categories(dfs, ["SCH_GRADE_KG"] + grade_cols)
        string_profile(dfs)
        follow_ups(dfs, vals)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    print(f"\nreport written to {args.report}")


if __name__ == "__main__":
    main()
