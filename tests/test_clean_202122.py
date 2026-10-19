"""Tests for scripts/clean_202122.py.

Unit tests use tiny frames. The pipeline tests build a small fake CRDC folder in a temporary
directory and run the whole cleaning on it.
"""

from __future__ import annotations

from pathlib import Path

import clean_202122 as clean
import numpy as np
import pandas as pd
import pytest

NA = pd.NA

# The five schools in good_schools(), named by their combokey (LEAID + SCHID).
SCHOOL_ALPHA = "010000100001"  # partial enrollment total, fractional FTE
SCHOOL_BRAVO = "010000100002"  # female count reserved, no enrollment total
SCHOOL_CHARLIE = "010000200003"  # reported zero enrollment
SCHOOL_DELTA = "010000200004"  # seclusion not applicable, nurse FTE missing
SCHOOL_STATE_PROGRAM = "24SOP0299985"  # state-operated program ID with letters


def strings(values: list) -> pd.Series:
    return pd.Series(values, dtype="string")


def floats(values: list) -> pd.Series:
    return pd.Series(values, dtype="Float64")


# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "width", "expected", "issue"),
    [
        ("1234", 7, "0001234", "padded_id"),
        ("0100002", 7, "0100002", ""),
        ("24SOP02", 7, "24SOP02", "non_digit_id"),
        ("nan", 7, "nan", "invalid_id_characters"),
        ("NAN", 7, "NAN", "invalid_id_characters"),
        ("12 34", 7, "12 34", "invalid_id_characters"),
        ("12345678", 7, "12345678", "id_too_long"),
        ("AB1", 7, "AB1", "bad_id_length"),
        (None, 7, None, "blank_id"),
    ],
)
def test_clean_id_column(raw, width, expected, issue):
    cleaned, labels = clean.clean_id_column(strings([raw]), width)
    assert labels.iloc[0] == issue
    if expected is None:
        assert pd.isna(cleaned.iloc[0])
    else:
        assert cleaned.iloc[0] == expected


def test_clean_id_column_never_turns_nan_into_padded_text():
    cleaned, labels = clean.clean_id_column(strings(["nan", None]), 5)
    assert labels.tolist() == ["invalid_id_characters", "blank_id"]
    assert "00nan" not in cleaned.dropna().tolist()


def school_ids_frame(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_row": range(1, len(rows) + 1),
            "LEAID": strings([r[0] for r in rows]),
            "SCHID": strings([r[1] for r in rows]),
            "COMBOKEY": strings([r[2] for r in rows]),
        }
    )


def id_spec() -> clean.ModuleSpec:
    return clean.ModuleSpec("test", "SCH/Test.csv", ("LEAID", "SCHID", "COMBOKEY"))


def test_clean_module_ids_pads_and_checks_components():
    frame = school_ids_frame([("0100002", "1", "010000200001")])
    result = clean.clean_module_ids(frame, spec=id_spec(), log=clean.QualityLog())
    assert result.loc[0, "schid"] == "00001"
    assert result.loc[0, "combokey"] == "010000200001"


def test_clean_module_ids_rejects_component_mismatch():
    frame = school_ids_frame([("0100002", "00001", "010000200002")])
    with pytest.raises(clean.IdValidationError):
        clean.clean_module_ids(frame, spec=id_spec(), log=clean.QualityLog())


def test_clean_module_ids_rejects_duplicates_and_logs_them():
    frame = school_ids_frame(
        [("0100002", "00001", "010000200001"), ("0100002", "00001", "010000200001")]
    )
    log = clean.QualityLog()
    with pytest.raises(clean.IdValidationError):
        clean.clean_module_ids(frame, spec=id_spec(), log=log)
    assert set(log.to_frame()["issue"]) == {"duplicate_id"}


def test_clean_module_ids_keeps_state_program_ids_and_logs_them():
    frame = school_ids_frame([("24SOP02", "99985", "24SOP0299985")])
    log = clean.QualityLog()
    result = clean.clean_module_ids(frame, spec=id_spec(), log=log)
    assert result.loc[0, "combokey"] == "24SOP0299985"
    assert "non_digit_id" in set(log.to_frame()["issue"])


# ---------------------------------------------------------------------------
# Counts and FTEs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "issue", "is_na"),
    [
        ("5", "", False),
        ("0", "", False),  # a reported zero stays zero
        ("-9", "reserved_code", True),
        ("-2", "unexpected_negative", True),
        ("abc", "parse_failure", True),
        ("inf", "non_finite", True),
        ("2.5", "fractional_count", True),
        (None, "blank_value", True),
        ("7", "", False),
    ],
)
def test_parse_numeric_handles_each_kind_of_bad_value(raw, issue, is_na):
    parsed = clean.parse_numeric(strings([raw]), whole_number=True)
    assert parsed.issue.iloc[0] == issue
    assert parsed.values.isna().iloc[0] == is_na


def test_parse_numeric_keeps_a_reported_zero():
    assert clean.parse_numeric(strings(["0"]), whole_number=True).values.iloc[0] == 0


def test_parse_numeric_names_the_reserved_code_in_the_evidence():
    parsed = clean.parse_numeric(strings(["-9"]), whole_number=True)
    assert "Skip logic" not in parsed.evidence.iloc[0]
    assert "Not applicable" in parsed.evidence.iloc[0]


def test_parse_numeric_keeps_fractional_fte():
    parsed = clean.parse_numeric(strings(["1.5", "-6"]), whole_number=False)
    assert parsed.values.iloc[0] == 1.5
    assert pd.isna(parsed.values.iloc[1])


def test_reserved_codes_match_the_2021_22_manual():
    assert set(clean.RESERVED_CODES) == {-3, -4, -5, -6, -9, -12, -13}


# ---------------------------------------------------------------------------
# Categories and grade band
# ---------------------------------------------------------------------------


def test_normalize_yes_no():
    cleaned, issue = clean.normalize_yes_no(strings([" yes ", "NO", "Maybe", None, "1"]))
    assert cleaned.tolist()[:2] == ["Yes", "No"]
    assert cleaned.isna().tolist() == [False, False, True, True, True]
    assert issue.tolist() == ["", "", "unexpected_category", "blank_value", "unexpected_category"]


def grades(yes: list[str], unknown: list[str] | None = None) -> pd.DataFrame:
    row = {column: "No" for column in clean.GRADE_COLUMNS}
    row.update({column: "Yes" for column in yes})
    row.update({column: NA for column in unknown or []})
    return pd.DataFrame([row], dtype="string")


@pytest.mark.parametrize(
    ("yes", "unknown", "expected"),
    [
        (["SCH_GRADE_KG", "SCH_GRADE_G05"], [], "elementary"),
        (["SCH_GRADE_G06", "SCH_GRADE_G08"], [], "middle"),
        (["SCH_GRADE_G09", "SCH_GRADE_G12"], [], "high"),
        (clean.GRADE_COLUMNS[:9], [], "span"),  # KG to grade 8
        (clean.GRADE_COLUMNS, [], "span"),  # KG to grade 12
        (["SCH_GRADE_G05", "SCH_GRADE_G06"], [], "span"),
        ([], [], "other"),
        (["SCH_GRADE_G09"], ["SCH_GRADE_G03"], None),
    ],
)
def test_derive_grade_band(yes, unknown, expected):
    band = clean.derive_grade_band(grades(yes, unknown))
    if expected is None:
        assert pd.isna(band.iloc[0])
    else:
        assert band.iloc[0] == expected


# ---------------------------------------------------------------------------
# Enrollment, seclusion and rates
# ---------------------------------------------------------------------------


def test_component_total_rules():
    male = floats([50, NA, 50, 0, 50])
    female = floats([50, 10, NA, 0, 50])
    nonbinary = floats([NA, NA, 3, 0, 4])
    total, partial = clean.component_total(male, female, nonbinary)
    assert total.isna().tolist() == [False, True, True, False, False]
    assert total.iloc[0] == 100, "missing X is not added"
    assert total.iloc[3] == 0, "a reported zero stays zero"
    assert total.iloc[4] == 104, "valid X is added"
    assert partial.tolist() == [True, True, False, False, False]


def test_strict_sum_is_na_when_any_part_is_missing():
    frame = pd.DataFrame(
        {"a": floats([1, 1, NA]), "b": floats([2, NA, NA]), "c": floats([3, 3, 3])}
    )
    result = clean.strict_sum(frame)
    assert result.iloc[0] == 6
    assert result.isna().tolist() == [False, True, True]


def test_rate_per_100_needs_valid_numerator_and_positive_denominator():
    rate = clean.rate_per_100(floats([5, 5, NA, 0]), floats([100, 0, 100, 50]))
    assert rate.iloc[0] == 5
    assert rate.isna().tolist() == [False, True, True, False]
    assert rate.iloc[3] == 0
    assert np.isfinite(rate.dropna().astype("float64")).all()


def test_derive_percentage_sets_na_when_subgroup_exceeds_total():
    subgroup, total = floats([10, 120, NA]), floats([100, 100, 100])
    share = clean.derive_percentage(subgroup, total)
    assert share.iloc[0] == 10
    assert pd.isna(share.iloc[1])
    assert clean.subgroup_exceeds_total(subgroup, total).tolist() == [False, True, False]


def test_fte_review_mask_uses_playbook_thresholds():
    table = pd.DataFrame({name: floats([1, 1, 1, 1]) for name in clean.FTE_COLUMNS})
    table["fte_teachers"] = floats([2001, 2000, 5, NA])
    table["fte_guards"] = floats([1, 1, 201, 200])
    assert clean.fte_review_mask(table).tolist() == [True, False, True, False]


def test_analysis_ready_mask_needs_a_rate_and_positive_enrollment():
    table = pd.DataFrame(
        {
            "seclusion_rate": floats([5, NA, 0, 5]),
            "enrollment_total": floats([100, 100, 50, 0]),
        }
    )
    assert clean.analysis_ready_mask(table).tolist() == [True, False, True, False]


# ---------------------------------------------------------------------------
# Joins
# ---------------------------------------------------------------------------


def join_roster() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "combokey": ["a", "b", "c"],
            "leaid": ["l1", "l1", "l2"],
            "src_row_char": [1, 2, 3],
        }
    )


def join(other: pd.DataFrame, log: clean.QualityLog | None = None, **overrides):
    """Run left_join_validated on join_roster() with test defaults. Override any argument."""
    arguments = {
        "key": "combokey",
        "validate": "one_to_one",
        "name": "x",
        "source_file": "X.csv",
        "other_row_column": "src_row_x",
        "roster_row_column": "src_row_char",
        "roster_file": "Roster.csv",
        "log": log or clean.QualityLog(),
        **overrides,
    }
    return clean.left_join_validated(join_roster(), other, **arguments)


def test_left_join_keeps_roster_rows_and_marks_missing_modules():
    other = pd.DataFrame(
        {"combokey": ["a", "b", "zzz"], "src_row_x": [1, 2, 3], "value": [1, 2, 3]}
    )
    log = clean.QualityLog()
    merged, report = join(other, log)
    assert len(merged) == 3
    assert merged["has_x"].tolist() == [True, True, False]
    assert (report.missing_keys, report.extra_keys) == (1, 1)
    assert {"missing_key_in_module", "extra_key_in_module"} <= set(log.to_frame()["issue"])


def test_left_join_rejects_duplicate_module_keys():
    other = pd.DataFrame({"combokey": ["a", "a"], "src_row_x": [1, 2]})
    with pytest.raises(clean.JoinValidationError):
        join(other)


def test_left_join_rejects_overlapping_columns():
    other = pd.DataFrame({"combokey": ["a"], "leaid": ["l1"], "src_row_x": [1]})
    with pytest.raises(clean.JoinValidationError):
        join(other)


def lea_roster() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "leaid": ["l1", "l2", "l3", "l4"],
            "LEA_NAME": ["Same", "Other", "Same", "Same"],
            "LEA_STATE": ["al", "AL", "al", "AL"],
            "lea_state": ["AL", "AL", "AL", "AL"],
            "has_lea": [True, True, True, False],
            "src_row_lea": [1, 2, 3, pd.NA],
            "lea_name": ["Same", "Renamed", "Same", pd.NA],
            "lea_state_file": ["AL", "AL", "GA", pd.NA],
        }
    )


def test_log_lea_conflicts_ignores_case_and_flags_real_differences():
    log = clean.QualityLog()
    clean.log_lea_conflicts(lea_roster(), source_file="LEA.csv", log=log)
    quality = log.to_frame().set_index("issue")
    assert quality.loc["lea_name_conflict", "cleaned_value"] == "Renamed"
    # "al" vs "AL" is not a conflict. Only l3 (AL vs GA) is.
    assert len(quality.loc[["lea_state_conflict"]]) == 1
    assert quality.loc["lea_state_conflict", "raw_value"] == "al"
    assert len(quality) == 2, "a school without an LEA row has nothing to compare"


# ---------------------------------------------------------------------------
# Reading files
# ---------------------------------------------------------------------------


def read_spec() -> clean.ModuleSpec:
    return clean.ModuleSpec("test", "SCH/Test.csv", ("LEAID", "SCHID", "COMBOKEY", "SCH_NAME"))


def write_bytes(raw_dir: Path, content: bytes) -> None:
    path = raw_dir / read_spec().relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(content)


def test_read_module_drops_empty_rows_but_keeps_row_numbers(tmp_path):
    header = b"LEAID,SCHID,COMBOKEY,SCH_NAME\n"
    rows = b"0100001,1,010000100001,A\n\n,,,\n0100002,2,010000200002,B\n"
    write_bytes(tmp_path, header + rows)
    log = clean.QualityLog()
    frame, info = clean.read_module(tmp_path, read_spec(), log)
    assert frame["source_row"].tolist() == [1, 4]
    assert (info.rows_parsed, info.rows_kept) == (4, 2)
    dropped = log.to_frame()
    assert dropped["issue"].tolist() == ["empty_row", "empty_row"]
    assert dropped["source_row"].tolist() == [2, 3]


def test_read_module_falls_back_to_cp1252_and_keeps_text_ids(tmp_path):
    header = b"LEAID,SCHID,COMBOKEY,SCH_NAME\n"
    write_bytes(tmp_path, header + "nan,00001,x,Caf\u00e9\n".encode("cp1252"))
    frame, info = clean.read_module(tmp_path, read_spec(), clean.QualityLog())
    assert info.encoding == "cp1252"
    assert frame.loc[0, "SCH_NAME"] == "Caf\u00e9"
    assert frame.loc[0, "LEAID"] == "nan", "the text nan must not become a missing value"
    with pytest.raises(clean.IdValidationError):
        clean.clean_module_ids(frame, spec=read_spec(), log=clean.QualityLog())


def test_read_module_reports_missing_file(tmp_path):
    with pytest.raises(clean.MissingFileError):
        clean.read_module(tmp_path, read_spec(), clean.QualityLog())


# ---------------------------------------------------------------------------
# Whole pipeline on a small fake CRDC folder
# ---------------------------------------------------------------------------


def default_value(column: str) -> str:
    is_category = column in clean.CATEGORY_COLUMNS.values() or column in clean.GRADE_COLUMNS
    return "No" if is_category or column == clean.JUSTICE_COLUMN else "0"


def make_row(spec: clean.ModuleSpec, **overrides: str) -> dict[str, str]:
    row = {column: default_value(column) for column in spec.columns}
    row.update(overrides)
    return row


def write_module(raw_dir: Path, key: str, rows: list[dict[str, str]]) -> None:
    spec = clean.MODULES[key]
    path = raw_dir / spec.relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(spec.columns), dtype=str).to_csv(path, index=False)


def school(leaid: str, schid: str, **by_module: dict[str, str]) -> dict[str, dict[str, str]]:
    ids = {"LEAID": leaid, "SCHID": schid, "COMBOKEY": leaid + schid}
    return {key: {**ids, **by_module.get(key, {})} for key in ("char", *clean.SCHOOL_MODULE_KEYS)}


def build_raw_dir(raw_dir: Path, schools: list[dict[str, dict[str, str]]]) -> None:
    for key in ("char", *clean.SCHOOL_MODULE_KEYS):
        spec = clean.MODULES[key]
        write_module(raw_dir, key, [make_row(spec, **s[key]) for s in schools])
    lea_spec = clean.MODULES["lea"]
    leaids = sorted({s["char"]["LEAID"] for s in schools})
    leas = [
        make_row(lea_spec, LEAID=leaid, LEA_NAME=f"District {leaid}", LEA_STATE="AL", LEA_ENR="500")
        for leaid in leaids
    ]
    write_module(raw_dir, "lea", leas)


def good_schools() -> list[dict[str, dict[str, str]]]:
    elementary = {"SCH_GRADE_KG": "Yes", "SCH_GRADE_G01": "Yes"}
    everything = {column: "Yes" for column in clean.GRADE_COLUMNS}
    return [
        # Alpha: X reserved, so the total is partial. Fractional FTE must survive.
        school(
            "0100001",
            "00001",
            char={**elementary, "LEA_STATE": "al", "SCH_NAME": " Alpha "},
            enrollment={"TOT_ENR_M": "50", "TOT_ENR_F": "50", "TOT_ENR_X": "-9"},
            restraint={
                "SCH_RSINSTANCES_SECL_WODIS": "1",
                "SCH_RSINSTANCES_SECL_IDEA": "2",
                "SCH_RSINSTANCES_SECL_504": "3",
            },
            support={
                "SCH_FTECOUNSELORS": "1.5",
                "SCH_FTETEACH_TOT": "5.5",
                "SCH_FTESERVICES_NUR": "1",
                "SCH_FTESERVICES_PSY": "0.5",
            },
        ),
        # Bravo: female count reserved, so there is no enrollment total.
        school("0100001", "00002", enrollment={"TOT_ENR_M": "10", "TOT_ENR_F": "-9"}),
        # Charlie: reported zero enrollment.
        school("0100002", "00003"),
        # Delta: seclusion not applicable, nurse FTE missing, valid X, all grades.
        school(
            "0100002",
            "00004",
            char=everything,
            enrollment={"TOT_ENR_M": "40", "TOT_ENR_F": "40", "TOT_ENR_X": "2"},
            restraint={
                "SCH_RSINSTANCES_SECL_WODIS": "-9",
                "SCH_RSINSTANCES_SECL_IDEA": "-9",
                "SCH_RSINSTANCES_SECL_504": "-9",
            },
            support={"SCH_FTESERVICES_NUR": "-3"},
        ),
        # State program: ID with letters.
        school(
            "24SOP02",
            "99985",
            enrollment={"TOT_ENR_M": "20", "TOT_ENR_F": "20", "TOT_ENR_X": "0"},
        ),
    ]


@pytest.fixture
def cleaned(tmp_path: Path):
    raw_dir, out_dir, docs_dir = tmp_path / "raw", tmp_path / "out", tmp_path / "docs"
    build_raw_dir(raw_dir, good_schools())
    # Module files store SCHID without leading zeros, as the real 2021-22 files do.
    path = raw_dir / clean.MODULES["enrollment"].relative_path
    frame = pd.read_csv(path, dtype=str)
    frame["SCHID"] = frame["SCHID"].str.lstrip("0")
    frame.to_csv(path, index=False)
    result = clean.run(raw_dir, out_dir, docs_dir)
    return result, out_dir, docs_dir


def test_pipeline_keeps_every_roster_school(cleaned):
    result, _, _ = cleaned
    assert len(result.full) == len(good_schools())
    assert list(result.full.columns) == clean.OUTPUT_COLUMNS
    assert result.full["combokey"].is_unique
    assert result.full["combokey"].is_monotonic_increasing


def test_pipeline_school_with_partial_enrollment_and_fractional_fte(cleaned):
    result, _, _ = cleaned
    alpha = result.full.set_index("combokey").loc[SCHOOL_ALPHA]
    assert alpha["lea_state"] == "AL"
    assert alpha["sch_name"] == "Alpha"
    assert alpha["lea_name"] == "District 0100001"
    assert alpha["enrollment_total"] == 100
    assert pd.isna(alpha["enr_nonbinary"])
    assert alpha["flag_partial_enrollment"]
    assert alpha["seclusion_instances"] == 6
    assert alpha["seclusion_rate"] == 6
    assert alpha["grade_band"] == "elementary"
    assert alpha["fte_teachers"] == 5.5
    assert alpha["counselors_per_100"] == 1.5
    assert alpha["support_fte_per_100"] == 1.5
    assert alpha["flag_analysis_ready"]


def test_pipeline_reserved_female_count_gives_no_enrollment_total(cleaned):
    result, _, _ = cleaned
    bravo = result.full.set_index("combokey").loc[SCHOOL_BRAVO]
    assert pd.isna(bravo["enrollment_total"])
    assert bravo["flag_missing_enrollment"]
    assert not bravo["flag_analysis_ready"]


def test_pipeline_zero_enrollment_stays_zero_and_gives_no_rate(cleaned):
    result, _, _ = cleaned
    charlie = result.full.set_index("combokey").loc[SCHOOL_CHARLIE]
    assert charlie["enrollment_total"] == 0
    assert charlie["flag_missing_enrollment"] and charlie["flag_small_enrollment"]
    assert pd.isna(charlie["seclusion_rate"]), "zero enrollment gives no rate"
    assert not charlie["flag_analysis_ready"]


def test_pipeline_missing_seclusion_and_nurse_fte_give_na_not_zero(cleaned):
    result, _, _ = cleaned
    delta = result.full.set_index("combokey").loc[SCHOOL_DELTA]
    assert pd.isna(delta["seclusion_instances"]) and delta["flag_missing_seclusion"]
    assert pd.isna(delta["support_fte_per_100"]), "missing nurse FTE gives no support rate"
    assert delta["enrollment_total"] == 82 and not delta["flag_partial_enrollment"]
    assert delta["grade_band"] == "span"
    assert not delta["flag_analysis_ready"]


def test_pipeline_analysis_is_the_filtered_full_table(cleaned):
    result, out_dir, _ = cleaned
    expected = result.full[result.full["flag_analysis_ready"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(result.analysis, expected)
    reloaded = clean.read_clean_csv(out_dir / f"schools_{clean.YEAR_CODE}_analysis.csv")
    assert reloaded["combokey"].tolist() == expected["combokey"].tolist()


def test_pipeline_state_program_id_is_kept_and_logged(cleaned):
    result, _, _ = cleaned
    assert SCHOOL_STATE_PROGRAM in result.full["combokey"].tolist()
    assert (result.quality["issue"] == "non_digit_id").any()


def test_pipeline_logs_reserved_codes_with_original_values(cleaned):
    result, _, _ = cleaned
    reserved = result.quality[result.quality["issue"] == "reserved_code"]
    assert {"-9", "-3"} <= set(reserved["raw_value"])
    assert reserved["cleaned_value"].isna().all()
    assert list(result.quality.columns) == clean.QUALITY_COLUMNS


def test_pipeline_writes_all_files_with_expected_formats(cleaned):
    _, out_dir, docs_dir = cleaned
    code = clean.YEAR_CODE
    for name in (
        f"schools_{code}.csv",
        f"schools_{code}_analysis.csv",
        f"quality_detail_{code}.csv",
    ):
        assert (out_dir / name).is_file()
    assert (docs_dir / f"mapping_{code}.csv").is_file()
    assert (docs_dir / f"qa_{code}.md").is_file()
    reloaded = clean.read_clean_csv(out_dir / f"schools_{code}.csv")
    assert reloaded["leaid"].str.len().eq(7).all()
    assert reloaded["combokey"].iloc[0].startswith("0")
    assert str(reloaded["enrollment_total"].dtype) == "Float64"
    assert str(reloaded["flag_analysis_ready"].dtype) == "boolean"


def test_pipeline_rerun_gives_identical_files(cleaned, tmp_path):
    _, out_dir, docs_dir = cleaned
    first = {p.name: p.read_bytes() for p in [*out_dir.iterdir(), *docs_dir.iterdir()]}
    clean.run(tmp_path / "raw", out_dir, docs_dir)
    second = {p.name: p.read_bytes() for p in [*out_dir.iterdir(), *docs_dir.iterdir()]}
    assert first == second


def test_pipeline_stops_on_duplicate_roster_key(tmp_path):
    schools = good_schools()
    schools.append(school("0100001", "00001"))
    build_raw_dir(tmp_path / "raw", schools)
    with pytest.raises(clean.IdValidationError):
        clean.run(tmp_path / "raw", tmp_path / "out", tmp_path / "docs")
    assert (tmp_path / "out" / f"quality_detail_{clean.YEAR_CODE}.csv").is_file()


def test_pipeline_reports_missing_columns(tmp_path):
    build_raw_dir(tmp_path / "raw", good_schools())
    path = tmp_path / "raw" / clean.MODULES["support"].relative_path
    pd.read_csv(path, dtype=str).drop(columns=["SCH_FTECOUNSELORS"]).to_csv(path, index=False)
    with pytest.raises(clean.MissingColumnError):
        clean.run(tmp_path / "raw", tmp_path / "out", tmp_path / "docs")


def test_pipeline_logs_padded_module_school_ids_as_a_summary(cleaned):
    result, _, _ = cleaned
    assert result.summaries, "unpadded SCHID values in a module file are counted"
    file, column, issue, rows = result.summaries[0]
    assert (file, column, issue) == (clean.MODULES["enrollment"].file_name, "SCHID", "padded_id")
    assert rows == len(good_schools()) - 1, "all but the state program SCHID lost leading zeros"
    assert "padded_id" not in set(result.quality["issue"])


def test_pipeline_subgroup_percentages_and_partial_flags(tmp_path):
    enrollment = {
        "TOT_ENR_M": "50",
        "TOT_ENR_F": "50",
        "TOT_ENR_X": "0",
        "SCH_ENR_IDEA_M": "5",
        "SCH_ENR_IDEA_F": "5",
        "SCH_ENR_IDEA_X": "-9",  # partial: X unavailable
        "SCH_ENR_504_M": "60",
        "SCH_ENR_504_F": "60",  # 120 is more than 100 students
        "SCH_ENR_504_X": "0",
        "SCH_ENR_EL_M": "1",
        "SCH_ENR_EL_F": "1",
        "SCH_ENR_EL_X": "1",
    }
    build_raw_dir(tmp_path / "raw", [school("0100001", "00001", enrollment=enrollment)])
    result = clean.run(tmp_path / "raw", tmp_path / "out", tmp_path / "docs")
    row = result.full.iloc[0]
    assert row["enrollment_total"] == 100
    assert (row["enr_idea"], row["pct_idea"], row["flag_partial_idea"]) == (10, 10, True)
    assert row["enr_504"] == 120 and pd.isna(row["pct_504"]) and not row["flag_partial_504"]
    assert (row["enr_el"], row["pct_el"], row["flag_partial_el"]) == (3, 3, False)
    exceeded = result.quality[result.quality["issue"] == "subgroup_exceeds_total"]
    assert exceeded["raw_column"].tolist() == ["enr_504"]


def drop_rows(raw_dir: Path, key: str, column: str, value: str) -> None:
    """Remove the rows of one module file where `column` equals `value`."""
    path = raw_dir / clean.MODULES[key].relative_path
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame[frame[column] != value].to_csv(path, index=False)


def test_pipeline_flags_missing_module_and_missing_lea(tmp_path):
    raw_dir = tmp_path / "raw"
    first_key, second_key = "010000100001", "010000900009"
    build_raw_dir(raw_dir, [school("0100001", "00001"), school("0100009", "00009")])
    drop_rows(raw_dir, "restraint", "COMBOKEY", first_key)
    drop_rows(raw_dir, "lea", "LEAID", "0100009")
    result = clean.run(raw_dir, tmp_path / "out", tmp_path / "docs")
    table = result.full.set_index("combokey")
    first, second = table.loc[first_key], table.loc[second_key]
    assert first["flag_missing_module"] and not first["flag_missing_lea"]
    assert pd.isna(first["seclusion_instances"]) and not first["flag_analysis_ready"]
    assert second["flag_missing_lea"] and not second["flag_missing_module"]
    assert pd.isna(second["lea_name"])
    assert "missing_key_in_module" in set(result.quality["issue"])


def test_pipeline_removes_stale_outputs_when_it_stops(cleaned, tmp_path):
    _, out_dir, docs_dir = cleaned
    code = clean.YEAR_CODE
    raw_dir = tmp_path / "raw"
    path = raw_dir / clean.MODULES["char"].relative_path
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    pd.concat([frame, frame.iloc[[0]]]).to_csv(path, index=False)
    with pytest.raises(clean.IdValidationError):
        clean.run(raw_dir, out_dir, docs_dir)
    assert not (out_dir / f"schools_{code}.csv").exists()
    assert not (out_dir / f"schools_{code}_analysis.csv").exists()
    assert not (docs_dir / f"qa_{code}.md").exists()
    assert (out_dir / f"quality_detail_{code}.csv").is_file()


def test_validate_tables_rejects_missing_ids_and_stray_rates(cleaned):
    result, _, _ = cleaned
    broken = result.full.copy()
    broken.loc[0, "schid"] = pd.NA
    with pytest.raises(clean.OutputValidationError, match="schid"):
        clean.validate_tables(broken, result.analysis, len(broken))
    stray = result.full.copy()
    zero_enrollment = stray["enrollment_total"].eq(0).idxmax()
    stray.loc[zero_enrollment, "teachers_per_100"] = 5.0
    with pytest.raises(clean.OutputValidationError, match="teachers_per_100"):
        clean.validate_tables(stray, result.analysis, len(stray))


# ---------------------------------------------------------------------------
# Mapping file and output schema
# ---------------------------------------------------------------------------


def test_mapping_has_the_documented_columns_and_statuses():
    mapping = clean.build_mapping()
    assert list(mapping.columns) == clean.MAPPING_COLUMNS
    assert set(mapping["verification_status"]) <= {"verified", "unresolved"}
    used = set(mapping["source_column"])
    for raw_columns in (clean.SECLUSION_COLUMNS.values(), clean.FTE_COLUMNS.values()):
        assert set(raw_columns) <= used


def test_output_schema_has_no_overlap_between_type_groups():
    groups = [set(clean.STRING_COLUMNS), set(clean.FLOAT_COLUMNS), set(clean.BOOLEAN_COLUMNS)]
    assert sum(len(g) for g in groups) == len(clean.OUTPUT_COLUMNS) == len(set().union(*groups))
