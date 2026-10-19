"""Phase 2 diagnostics for CRDC 2017-18 (read-only; changes no cleaning rule).

Evidence for the definition questions that the documentation alone does not settle:
  D1. Reserved codes vs the manual's lists of Action Plan LEAs (Appendix C, code -5)
      and Force Certified LEAs (Appendix D, code -6).
  D2. Seclusion rows coded -5/ok/-5 and -5/ok/ok vs the matching student-count fields.
  D3. IDEA > total and LEP > total rows vs preschool enrollment; size of the excess.
  D4. Does TOT_ENR include preschool? (preschool-only schools, race-sum identity)
  D5. Non-digit IDs: shapes, states, presence in the manual's appendices.
  D6. JJ definition checks: named facilities, justice-like names with JJ = No.
  D7. Rows coded -9 on all three seclusion instance fields.
  D8. FTE review-trigger LEAs in the OCR post-submission data quality workbook.

Needs the extracted files from profile_201718.py and `pdftotext` (MiKTeX/poppler) on
PATH for D1/D5. Writes a text report to --report and prints it.

Usage:
  python scripts/diagnostics_201718.py
"""

import argparse
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

from profile_201718 import MODULES, ROOT, SECL, read_module

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


def table(df):
    for line in df.to_string().splitlines():
        out("    " + line)


def num(s):
    """Numeric value of a raw string column; reserved codes stay negative."""
    return pd.to_numeric(s, errors="coerce")


def code(s):
    """'ok' for values >= 0, otherwise the raw reserved code."""
    return s.where(s.str.startswith("-"), "ok").str.replace(r"\.00$", "", regex=True)


# ---------------------------------------------------------------- manual appendices
def manual_appendix_leas(manual_pdf):
    """LEAIDs listed in the manual's Appendix C (action plan) and D (force certified)."""
    text = subprocess.run(["pdftotext", "-layout", str(manual_pdf), "-"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True).stdout
    lists, current = {"C": set(), "D": set()}, None
    for line in text.splitlines():
        if "APPENDIX C: LEAS CERTIFIED BY ACTION PLAN" in line:
            current = "C"
        elif "APPENDIX D: FORCE CERTIFIED LEAS" in line:
            current = "D"
        elif "APPENDIX E" in line and current:
            current = None
        m = re.match(r"^\s*([A-Z]{2})\s+([0-9A-Z]{7})\b", line)
        if current and m:
            lists[current].add(m.group(2))
    return lists


# ---------------------------------------------------------------- xlsx (stdlib)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def read_xlsx_sheet(path, sheet_name):
    """Read one worksheet into a DataFrame of strings using only the standard library."""
    z = zipfile.ZipFile(path)
    shared = [("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)]
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    sheet = next(s for s in wb.find("m:sheets", NS) if s.get("name") == sheet_name)
    target = rels[sheet.get(f"{{{NS['r']}}}id")]
    root = ET.fromstring(z.read("xl/" + target.lstrip("/").replace("xl/", "")))
    rows = []
    for row in root.iter(f"{{{NS['m']}}}row"):
        cells = {}
        for c in row.findall("m:c", NS):
            v = c.find("m:v", NS)
            col = re.match(r"[A-Z]+", c.get("r")).group(0)
            idx = 0
            for ch in col:
                idx = idx * 26 + ord(ch) - 64
            val = shared[int(v.text)] if c.get("t") == "s" and v is not None else (v.text if v is not None else "")
            cells[idx - 1] = val
        rows.append([cells.get(j, "") for j in range(max(cells) + 1)] if cells else [])
    width = len(rows[0])
    return pd.DataFrame([r + [""] * (width - len(r)) for r in rows[1:]], columns=rows[0])


# ---------------------------------------------------------------- diagnostics
def d1_codes_vs_appendices(dfs, lists):
    section("D1. RESERVED CODES vs MANUAL APPENDIX C (action plan) / D (force certified)")
    out(f"Appendix C LEAIDs parsed: {len(lists['C'])}; Appendix D LEAIDs parsed: {len(lists['D'])}; "
        f"in both: {len(lists['C'] & lists['D'])}")
    fields = [("E", "TOT_ENR_M"), ("E", "SCH_ENR_IDEA_M"), ("R", SECL[0]), ("R", SECL[1]), ("R", SECL[2]),
              ("S", "SCH_FTETEACH_TOT"), ("S", "SCH_FTESECURITY_LEO"), ("S", "SCH_FTESECURITY_GUA"),
              ("L", "LEA_ENR")]
    for key, col in fields:
        d = dfs[key]
        cd = code(d[col])
        for c in sorted(set(cd) - {"ok"}, key=lambda x: int(x)):
            leas = d.loc[cd == c, "LEAID"]
            out(f"  {col} {c}: rows {len(leas):,}; LEAs {leas.nunique():,}; rows in App. C "
                f"{int(leas.isin(lists['C']).sum()):,}; in App. D {int(leas.isin(lists['D']).sum()):,}; "
                f"in neither {int((~leas.isin(lists['C'] | lists['D'])).sum()):,}")
    r = dfs["R"]
    ok_all = (code(r[SECL[0]]) == "ok") & (code(r[SECL[1]]) == "ok") & (code(r[SECL[2]]) == "ok")
    for name, s in [("App. C", lists["C"]), ("App. D", lists["D"])]:
        inl = r["LEAID"].isin(s)
        out(f"  schools in {name} LEAs: {int(inl.sum()):,}; of these, seclusion triple fully valid "
            f"{int((inl & ok_all).sum()):,}")
    nyc = r["LEAID"] == "3620580"
    out(f"  New York City (LEAID 3620580, tech doc 7.1): schools {int(nyc.sum()):,}; WODIS codes "
        f"{dict(Counter(code(r.loc[nyc, SECL[0]])))}; in App. C {'3620580' in lists['C']}, "
        f"in App. D {'3620580' in lists['D']}")
    for col in SECL + ["SCH_RSINSTANCES_MECH_WODIS", "SCH_RSINSTANCES_PHYS_WODIS", "TOT_RS_NONIDEA_SECL_M"]:
        v = r.loc[nyc, col]
        out(f"    NYC {col}: codes {dict(Counter(code(v)))}; ==0 {int((num(v) == 0).sum())}; >0 {int((num(v) > 0).sum())}")


def d2_minus5_rows(dfs, lists):
    section("D2. SECLUSION -5/ok/-5 AND -5/ok/ok ROWS vs STUDENT-COUNT FIELDS")
    r = dfs["R"]
    pat = code(r[SECL[0]]) + "/" + code(r[SECL[1]]) + "/" + code(r[SECL[2]])
    stud = ["TOT_RS_NONIDEA_SECL_M", "TOT_RS_NONIDEA_SECL_F", "SCH_RS_NONIDEA_SECL_504_M",
            "SCH_RS_NONIDEA_SECL_504_F", "TOT_RS_IDEA_SECL_M", "TOT_RS_IDEA_SECL_F"]
    for p in ["-5/ok/-5", "-5/ok/ok", "-5/-5/-5", "ok/ok/ok"]:
        sel = r[pat == p]
        out(f"pattern {p}: {len(sel):,} schools in {sel['LEAID'].nunique():,} LEAs; "
            f"LEAs in App. C {sel.loc[sel['LEAID'].isin(lists['C']), 'LEAID'].nunique()}, "
            f"in App. D {sel.loc[sel['LEAID'].isin(lists['D']), 'LEAID'].nunique()}; "
            f"states {dict(Counter(sel['LEA_STATE']).most_common(6))}")
        if p == "ok/ok/ok":
            continue
        for col in stud:
            v = sel[col]
            c = code(v)
            out(f"    {col}: codes {dict(Counter(c[c != 'ok']))}; valid {int((c == 'ok').sum())}; "
                f"valid==0 {int((num(v) == 0).sum())}; valid>0 {int((num(v) > 0).sum())}")
        out(f"    top LEAs: {dict(Counter(sel['LEAID'] + ' ' + sel['LEA_NAME'].str[:30]).most_common(5))}")
        ideainst = num(sel[SECL[1]])
        out(f"    IDEA instances on these rows: ==0 {int((ideainst == 0).sum())}, >0 {int((ideainst > 0).sum())}")
        # same-row consistency for the valid instance fields vs their student counts
        if p == "-5/ok/ok":
            i504 = num(sel[SECL[2]])
            out(f"    504 instances on these rows: ==0 {int((i504 == 0).sum())}, >0 {int((i504 > 0).sum())}")


def d3_subgroup_vs_preschool(dfs):
    section("D3. IDEA > TOTAL AND LEP > TOTAL vs PRESCHOOL ENROLLMENT")
    e = dfs["E"]
    v = {c: num(e[c]) for c in ["TOT_ENR_M", "TOT_ENR_F", "TOT_PSENR_M", "TOT_PSENR_F",
                                "SCH_ENR_IDEA_M", "SCH_ENR_IDEA_F", "SCH_PSENR_IDEA_M", "SCH_PSENR_IDEA_F",
                                "SCH_ENR_LEP_M", "SCH_ENR_LEP_F", "SCH_PSENR_LEP_M", "SCH_PSENR_LEP_F",
                                "TOT_IDEAENR_M", "TOT_IDEAENR_F", "TOT_LEPENR_M", "TOT_LEPENR_F"]}
    tot = v["TOT_ENR_M"] + v["TOT_ENR_F"]
    ps = v["TOT_PSENR_M"] + v["TOT_PSENR_F"]
    for sub in ["IDEA", "LEP"]:
        sm, sf = v[f"SCH_ENR_{sub}_M"], v[f"SCH_ENR_{sub}_F"]
        valid = (v["TOT_ENR_M"] >= 0) & (v["TOT_ENR_F"] >= 0) & (sm >= 0) & (sf >= 0)
        over = valid & (sm + sf > tot)
        excess = (sm + sf - tot)[over]
        psub = v[f"SCH_PSENR_{sub}_M"] + v[f"SCH_PSENR_{sub}_F"]
        out(f"{sub}: rows with subgroup > total: {int(over.sum())}")
        out(f"  excess (subgroup - total) distribution: {dict(sorted(Counter(excess.astype(int)).items()))}")
        out(f"  per sex: M over {int((valid & (sm > v['TOT_ENR_M'])).sum())}, F over "
            f"{int((valid & (sf > v['TOT_ENR_F'])).sum())}")
        out(f"  TOT_PSENR (M+F) on these rows: valid {int((ps[over] >= 0).sum())}, >0 {int((ps[over] > 0).sum())}, "
            f"==0 {int((ps[over] == 0).sum())}, reserved {int((ps[over] < 0).sum())}")
        expl = over & (ps >= 0) & (sm + sf <= tot + ps)
        out(f"  subgroup <= TOT_ENR + TOT_PSENR (preschool could cover the excess): {int(expl.sum())} of {int(over.sum())}")
        out(f"  SCH_PSENR_{sub} (M+F) >= excess: {int((over & (psub >= (sm + sf - tot))).sum())} of {int(over.sum())}")
        calc = v[f"TOT_{sub}ENR_M"] + v[f"TOT_{sub}ENR_F"]
        out(f"  calculated TOT_{sub}ENR (M+F) on these rows: equals SCH_ENR_{sub} {int((over & (calc == sm + sf)).sum())}, "
            f"<= total {int((over & (calc >= 0) & (calc <= tot)).sum())}")
        grades = dfs["C"].set_index("COMBOKEY").loc[e.loc[over, "COMBOKEY"], ["SCH_GRADE_PS", "SCH_STATUS_SPED"]]
        out(f"  SCH_GRADE_PS on these rows {dict(Counter(grades['SCH_GRADE_PS']))}; SPED {dict(Counter(grades['SCH_STATUS_SPED']))}")
        out(f"  total enrollment on these rows: median {tot[over].median()}, max {tot[over].max()}")
        big = over & ((sm + sf - tot) > 3)
        for i in e.index[big]:
            out(f"  excess > 3: {e.at[i, 'COMBOKEY']} {e.at[i, 'SCH_NAME'][:40]} | TOT {e.at[i, 'TOT_ENR_M']}/{e.at[i, 'TOT_ENR_F']} | "
                f"{sub} {e.at[i, f'SCH_ENR_{sub}_M']}/{e.at[i, f'SCH_ENR_{sub}_F']} | PS {e.at[i, 'TOT_PSENR_M']}/{e.at[i, 'TOT_PSENR_F']}")


def d4_enrollment_population(dfs):
    section("D4. DOES TOT_ENR INCLUDE PRESCHOOL?")
    c, e = dfs["C"].set_index("COMBOKEY"), dfs["E"].set_index("COMBOKEY")
    k12 = ["SCH_GRADE_KG"] + [f"SCH_GRADE_G{i:02d}" for i in range(1, 13)] + ["SCH_GRADE_UG"]
    ps_only = (c["SCH_GRADE_PS"] == "Yes") & (c[k12] == "No").all(axis=1)
    keys = c.index[ps_only]
    tot = num(e.loc[keys, "TOT_ENR_M"]) + num(e.loc[keys, "TOT_ENR_F"])
    ps = num(e.loc[keys, "TOT_PSENR_M"]) + num(e.loc[keys, "TOT_PSENR_F"])
    out(f"preschool-only schools (PS=Yes, KG/G01-G12/UG all No): {len(keys):,}")
    out(f"  TOT_ENR (M+F): ==0 {int((tot == 0).sum())}, >0 {int((tot > 0).sum())}, reserved {int((tot < 0).sum())}")
    out(f"  TOT_PSENR (M+F): >0 {int((ps > 0).sum())}, ==0 {int((ps == 0).sum())}")
    out(f"  TOT_ENR == TOT_PSENR on rows where both > 0: {int(((tot == ps) & (tot > 0)).sum())}")
    gap = (tot - ps)[(tot >= 0) & (ps >= 0)]
    out(f"  TOT_ENR - TOT_PSENR on preschool-only schools: distribution of gap "
        f"{dict(sorted(Counter(gap.clip(-10, 10).astype(int)).items()))} (clipped to +/-10)")
    out(f"  |gap| <= 2: {int((gap.abs() <= 2).sum())}; gap > 10: {int((gap > 10).sum())}; gap < -10: {int((gap < -10).sum())}")
    for k in gap[gap.abs() > 10].abs().sort_values(ascending=False).index[:5]:
        out(f"    {k} {c.at[k, 'SCH_NAME'][:40]} | TOT_ENR {e.at[k, 'TOT_ENR_M']}/{e.at[k, 'TOT_ENR_F']} | "
            f"TOT_PSENR {e.at[k, 'TOT_PSENR_M']}/{e.at[k, 'TOT_PSENR_F']}")
    sec = dfs["R"].set_index("COMBOKEY").loc[keys, SECL[0]]
    out(f"  seclusion WODIS codes on preschool-only schools: {dict(Counter(code(sec)))}")
    allt = (num(e["TOT_ENR_M"]) + num(e["TOT_ENR_F"])).reindex(c.index)
    allp = (num(e["TOT_PSENR_M"]) + num(e["TOT_PSENR_F"])).reindex(c.index)
    okb = (allt >= 0) & (allp >= 0)
    out(f"  all schools with both valid ({int(okb.sum()):,}): TOT_ENR < TOT_PSENR on {int((okb & (allt < allp)).sum()):,}; "
        f"by more than 2 on {int((okb & (allt < allp - 2)).sum()):,}")
    mixed = (c["SCH_GRADE_PS"] == "Yes") & (c[k12] == "Yes").any(axis=1)
    okm = mixed & okb
    out(f"  schools offering PS and KG-G12/UG: {int(mixed.sum()):,}; TOT_PSENR > 0 on {int((okm & (allp > 0)).sum()):,}; "
        f"TOT_ENR < TOT_PSENR on {int((okm & (allt < allp)).sum()):,}")
    nog = (c["SCH_GRADE_PS"] == "No") & (c[k12] == "No").all(axis=1)
    out(f"  schools with no grade flag Yes at all (PS, KG-G12, UG all No): {int(nog.sum()):,}; TOT_ENR >0 "
        f"{int((nog & (allt > 0)).sum())}, ==0 {int((nog & (allt == 0)).sum())}; JJ {dict(Counter(c.loc[nog, 'JJ']))}; "
        f"SPED {dict(Counter(c.loc[nog, 'SCH_STATUS_SPED']))}")
    races = ["HI", "AM", "AS", "HP", "BL", "WH", "TR"]
    for sex in ["M", "F"]:
        rs = sum(num(e[f"SCH_ENR_{r}_{sex}"]) for r in races)
        t = num(e[f"TOT_ENR_{sex}"])
        ok = (t >= 0) & (rs >= 0)
        out(f"  TOT_ENR_{sex} == sum of SCH_ENR_{{race}}_{sex}: {int((ok & (rs == t)).sum()):,} of {int(ok.sum()):,} valid rows")
        prs = sum(num(e[f"SCH_PSENR_{r}_{sex}"]) for r in races)
        pt = num(e[f"TOT_PSENR_{sex}"])
        ok = (pt >= 0) & (prs >= 0)
        out(f"  TOT_PSENR_{sex} == sum of SCH_PSENR_{{race}}_{sex}: {int((ok & (prs == pt)).sum()):,} of {int(ok.sum()):,} valid rows")


def d5_nondigit_ids(dfs, lists):
    section("D5. NON-DIGIT IDs vs MANUAL")
    c = dfs["C"]
    nd = ~c["LEAID"].str.fullmatch(r"\d+")
    leas = set(c.loc[nd, "LEAID"])
    out(f"non-digit LEAIDs in data: {len(leas)}; listed in manual App. C {len(leas & lists['C'])}, "
        f"App. D {len(leas & lists['D'])}")
    out(f"non-digit LEAIDs printed anywhere in manual appendices: "
        f"{sorted(x for x in lists['C'] | lists['D'] if not x.isdigit())[:12]} ...")
    shp = c.loc[nd, "LEAID"].str.replace(r"\d", "9", regex=True).str.replace(r"[A-Z]", "A", regex=True)
    for s in sorted(set(shp)):
        sub = c[nd & (shp.reindex(c.index) == s)]
        out(f"  shape {s}: rows {len(sub)}; LEAIDs {sub['LEAID'].nunique()}; letter parts "
            f"{dict(Counter(sub['LEAID'].str.extract(r'([A-Z]+)')[0]))}; states {dict(Counter(sub['LEA_STATE']))}")
        for _, r in sub.drop_duplicates("LEAID").head(4).iterrows():
            out(f"    {r.LEAID} | {r.COMBOKEY} | {r.SCH_NAME[:45]} | {r.LEA_NAME[:40]} | charter {r.SCH_STATUS_CHARTER}")
    out(f"  SCH_STATUS_CHARTER on non-digit rows: {dict(Counter(c.loc[nd, 'SCH_STATUS_CHARTER']))}")
    out(f"  FIPS prefix vs LEA_STATE consistent (all rows, first 2 chars of LEAID): "
        f"{dict(Counter(c.groupby('LEA_STATE')['LEAID'].agg(lambda s: s.str[:2].nunique())))} (value = n distinct prefixes per state)")


def d6_jj(dfs):
    section("D6. JJ CHECKS")
    c, e, s = dfs["C"].set_index("COMBOKEY"), dfs["E"].set_index("COMBOKEY"), dfs["S"].set_index("COMBOKEY")
    lea = dfs["L"].set_index("LEAID")
    for k in ["420080699999", "220004701781"]:
        r = c.loc[k]
        grades = [g.replace("SCH_GRADE_", "") for g in c.columns if g.startswith("SCH_GRADE_") and r[g] == "Yes"]
        out(f"{k} | {r.SCH_NAME} | LEA {r.LEAID} {r.LEA_NAME} | JJ {r.JJ} | ALT {r.SCH_STATUS_ALT} | SPED {r.SCH_STATUS_SPED} "
            f"| grades {grades}")
        out(f"  enrollment M/F {e.at[k, 'TOT_ENR_M']}/{e.at[k, 'TOT_ENR_F']}; LEO {s.at[k, 'SCH_FTESECURITY_LEO']}; "
            f"GUA {s.at[k, 'SCH_FTESECURITY_GUA']}; teachers {s.at[k, 'SCH_FTETEACH_TOT']}; LEA CJJ {lea.at[r.LEAID, 'CJJ']}")
        sib = c[c["LEAID"] == r.LEAID]
        out(f"  schools in same LEA: {len(sib)}; JJ values {dict(Counter(sib['JJ']))}")
    pat = r"\b(?:SCI|CORRECTION|CORRECTIONAL|DETENTION|JUVENILE|JAIL|PRISON|YOUTH CENTER|YOUTH DEVELOPMENT|DOC)\b"
    name_hit = c["SCH_NAME"].str.upper().str.contains(pat, regex=True) | \
        c["LEA_NAME"].str.upper().str.contains(pat, regex=True)
    out(f"schools whose SCH_NAME or LEA_NAME matches {pat}: {int(name_hit.sum())}; JJ "
        f"{dict(Counter(c.loc[name_hit, 'JJ']))}")
    no = c[name_hit & (c["JJ"] == "No")]
    out(f"  JJ=No examples: " + "; ".join(f"{k} {r.SCH_NAME[:35]} ({r.LEA_STATE})" for k, r in no.head(8).iterrows()))
    out(f"  JJ=No name matches by state (top): {dict(Counter(no['LEA_STATE']).most_common(8))}")
    gua_jj = pd.crosstab(code(s["SCH_FTESECURITY_GUA"]).rename("GUA"), name_hit.reindex(s.index).rename("justice-like name"))
    table(gua_jj)
    cjj = dfs["L"].set_index("LEAID")["CJJ"]
    jjc = c.groupby("LEAID")["JJ"].agg(lambda x: (x == "Yes").any())
    both = pd.crosstab(cjj.reindex(jjc.index).rename("LEA CJJ"), jjc.rename("any school JJ=Yes"))
    out("LEA CJJ vs any school in LEA with JJ=Yes:")
    table(both)


def d7_minus9(dfs):
    section("D7. ROWS CODED -9 ON ALL THREE SECLUSION INSTANCE FIELDS")
    r = dfs["R"]
    c, e = dfs["C"].set_index("COMBOKEY"), dfs["E"].set_index("COMBOKEY")
    sel = (r[SECL] == "-9").all(axis=1)
    keys = r.loc[sel, "COMBOKEY"]
    cc = c.loc[keys]
    k12 = ["SCH_GRADE_KG"] + [f"SCH_GRADE_G{i:02d}" for i in range(1, 13)]
    out(f"rows {int(sel.sum()):,}; LEAs {r.loc[sel, 'LEAID'].nunique():,}; states {dict(Counter(r.loc[sel, 'LEA_STATE']).most_common(8))}")
    out(f"  JJ {dict(Counter(cc['JJ']))}; SPED {dict(Counter(cc['SCH_STATUS_SPED']))}; ALT {dict(Counter(cc['SCH_STATUS_ALT']))}")
    out(f"  any KG-G12 offered {dict(Counter((cc[k12] == 'Yes').any(axis=1)))}; PS offered {dict(Counter(cc['SCH_GRADE_PS']))}; "
        f"UG offered {dict(Counter(cc['SCH_GRADE_UG']))}")
    tot = num(e.loc[keys, "TOT_ENR_M"]) + num(e.loc[keys, "TOT_ENR_F"])
    out(f"  TOT_ENR (M+F): ==0 {int((tot == 0).sum())}, 1-9 {int(((tot > 0) & (tot < 10)).sum())}, >=10 {int((tot >= 10).sum())}; median {tot.median()}")
    other = ["SCH_RSINSTANCES_MECH_WODIS", "SCH_RSINSTANCES_PHYS_WODIS", "TOT_RS_NONIDEA_SECL_M", "TOT_RS_IDEA_SECL_M"]
    for col in other:
        out(f"  {col} on these rows: {dict(Counter(code(r.loc[sel, col])))}")
    out(f"  -9 on seclusion fields elsewhere: rows with -9 on some but not all three: "
        f"{int(((r[SECL] == '-9').any(axis=1) & ~sel).sum())}")


def d8_fte_flags(dfs, appc_path):
    section("D8. FTE REVIEW-TRIGGER LEAs IN OCR POST-SUBMISSION DQ WORKBOOK (Appndx C)")
    staf = read_xlsx_sheet(appc_path, "STAF").set_index("LEA ID")
    secr = read_xlsx_sheet(appc_path, "SECR").set_index("LEA ID")
    out(f"STAF sheet: {len(staf)} LEAs, columns {list(staf.columns)}")
    out(f"SECR sheet: {len(secr)} LEAs, columns {list(secr.columns)}")
    cases = {"4816620": "Del Valle ISD (GUA)", "5305910": "Northshore SD (PSY)", "1601590": "Jerome Joint (LEO)",
             "4200806": "SCI-Camp Hill (GUA)", "2200047": "Office of Juvenile Justice LA (GUA)",
             "1811340": "Tippecanoe (NUR 194)", "3500153": "McCurdy Charter (CNS 100)",
             "2801620": "Greenville MS (CNS 100)", "3400024": "North Star Academy (TEACH 607)"}
    defs = read_xlsx_sheet(appc_path, "DQ Check Definitions")
    for chk in ["15", "84"]:
        row = defs[defs["Check Number"] == chk].iloc[0]
        out(f"  Check {chk} ({row['Module Abbreviation']}): {row['Check Description']}")
    s = dfs["S"]
    for lea, label in cases.items():
        st = staf.loc[lea].to_dict() if lea in staf.index else "not listed"
        se = secr.loc[lea].to_dict() if lea in secr.index else "not listed"
        st = {k: v for k, v in st.items() if v not in ("0", "")} if isinstance(st, dict) else st
        se = {k: v for k, v in se.items() if v not in ("0", "")} if isinstance(se, dict) else se
        n = int((s["LEAID"] == lea).sum())
        out(f"  {lea} {label}: schools in data {n}; STAF {st}; SECR {se}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw_extracted" / "2017-18")
    p.add_argument("--report", type=Path, default=ROOT / "docs" / "cleaning" / "diagnostics_201718.txt")
    args = p.parse_args()

    dfs = {key: read_module(args.raw_dir / Path(member).name)[0] for key, member in MODULES.items()}
    lists = manual_appendix_leas(args.raw_dir / "2017-18 CRDC Public Data File Manual.pdf")
    d1_codes_vs_appendices(dfs, lists)
    d2_minus5_rows(dfs, lists)
    d3_subgroup_vs_preschool(dfs)
    d4_enrollment_population(dfs)
    d5_nondigit_ids(dfs, lists)
    d6_jj(dfs)
    d7_minus9(dfs)
    d8_fte_flags(dfs, args.raw_dir / "Appndx C. Post-Sub Data Quality Checks.xlsx")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    print(f"\nreport written to {args.report}")


if __name__ == "__main__":
    main()
