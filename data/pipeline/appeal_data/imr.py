"""D1: California DMHC Independent Medical Review determinations.

download -> validate -> clean -> PII scan -> profile -> load (imr_case, imr_stats, precedent_chunk).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from appeal_core.privacy.pii import regex_detect

from appeal_data.common import (
    PROCESSED,
    RAW,
    REPORTS,
    download,
    load_manifest,
    log_blocker,
    now_iso,
    sha256_file,
    update_manifest,
)

URL = (
    "https://data.chhs.ca.gov/dataset/b79b3447-4c10-4ae6-84e2-1076f83bb24e/resource/"
    "3340c5d7-4054-4d03-90e0-5f44290ed095/download/independent-medical-review-imr-determinations-trends.csv"
)
DICT_URL = (
    "https://data.chhs.ca.gov/dataset/b79b3447-4c10-4ae6-84e2-1076f83bb24e/resource/"
    "2c5c2144-138f-4feb-b2af-a1176995e1b1/download/imrdatadictionary.pdf"
)
EXPECTED = [
    "ReferenceID",
    "ReportYear",
    "DiagnosisCategory",
    "DiagnosisSubCategory",
    "TreatmentCategory",
    "TreatmentSubCategory",
    "Determination",
    "Type",
    "AgeRange",
    "PatientGender",
    "IMRType",
    "DaysToReview",
    "DaysToAdopt",
    "Findings",
]
RAW_PATH = RAW / "imr" / "imr_determinations.csv"
SYNTH_PATH = RAW / "imr_synthetic_sample.csv"
DICT_PATH = RAW / "imr" / "imrdatadictionary.pdf"
OUT = PROCESSED / "imr.parquet"


class SchemaError(Exception):
    pass


# ---------------------------------------------------------------- download / fallback
def acquire(force: bool = False) -> tuple[Path, str]:
    """Return (path, source) where source is 'real' or 'synthetic'."""
    if RAW_PATH.exists() and not force:
        return RAW_PATH, "real"
    try:
        download(URL, RAW_PATH, retries=3)
        return RAW_PATH, "real"
    except Exception as e:
        log_blocker(
            "D1 IMR download failed",
            f"3 retries with backoff against the CHHS CSV URL: {e}",
            "Generated data/raw/imr_synthetic_sample.csv (2,000 SYNTHETIC SAMPLE rows); IMR_SOURCE=synthetic",
            "Re-run `make data` when the portal is reachable.",
        )
        make_synthetic_sample(SYNTH_PATH)
        return SYNTH_PATH, "synthetic"


def acquire_dictionary() -> None:
    if not DICT_PATH.exists():
        try:
            download(DICT_URL, DICT_PATH, retries=3, timeout=120)
        except Exception as e:
            log_blocker("D1 data dictionary download failed", str(e), "Dictionary summary written from known columns only")


def make_synthetic_sample(path: Path, n: int = 2000, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    treat = {
        "Diag Imag & Screen": ["MRI", "CT Scan", "PET Scan"],
        "Pharmacy": ["Anti-inflammatory", "Biologic", "Oncology Drug"],
        "Mental Health": ["Residential Treatment", "Partial Hospitalization"],
        "Orthopedic Proc": ["Spinal Surgery", "Knee Surgery"],
        "Rehab/Svc - Outpt": ["Physical Therapy", "Speech Therapy"],
    }
    diag = ["Musculoskeletal", "Mental Disorder", "Cancer", "Neurological", "Digestive System"]
    rows = []
    for i in range(n):
        tc = rng.choice(list(treat))
        rows.append(
            {
                "ReferenceID": f"SYN{i:05d}",
                "ReportYear": int(rng.integers(2005, 2026)),
                "DiagnosisCategory": rng.choice(diag),
                "DiagnosisSubCategory": "Synthetic Subcategory",
                "TreatmentCategory": tc,
                "TreatmentSubCategory": rng.choice(treat[tc]),
                "Determination": rng.choice(["Overturned Decision of Health Plan", "Upheld Decision of Health Plan"]),
                "Type": rng.choice(["Medical Necessity", "Experimental/Investigational", "Urgent Care"], p=[0.74, 0.24, 0.02]),
                "AgeRange": rng.choice(["21 to 30", "31 to 40", "41 to 50", "51 to 64"]),
                "PatientGender": rng.choice(["Female", "Male"]),
                "IMRType": rng.choice(["Standard", "Expedited"]),
                "DaysToReview": int(rng.integers(1, 40)),
                "DaysToAdopt": int(rng.integers(1, 60)),
                "Findings": "SYNTHETIC SAMPLE. This is fake findings text for pipeline testing only.",
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


# ---------------------------------------------------------------- validate + clean
def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    report: dict = {}
    missing = [c for c in EXPECTED if c not in df.columns]
    if missing:
        raise SchemaError(f"missing columns: {missing}")
    years = pd.to_numeric(df["ReportYear"], errors="coerce")
    if years.isna().any():
        raise SchemaError(f"ReportYear has {int(years.isna().sum())} unparseable values")
    for c in ["DaysToReview", "DaysToAdopt"]:
        bad = pd.to_numeric(df[c], errors="coerce").isna() & df[c].notna()
        if bad.any():
            raise SchemaError(f"{c} has {int(bad.sum())} unparseable values")
    exact_dups = int(df.duplicated().sum())
    report["exact_duplicate_rows_dropped"] = exact_dups
    df = df.drop_duplicates().reset_index(drop=True)
    if not df["ReferenceID"].is_unique:
        n = int(df["ReferenceID"].duplicated().sum())
        raise SchemaError(f"ReferenceID not unique after dropping exact duplicates ({n} conflicting)")
    report["rows"] = len(df)
    return df, report


def _norm_label(s: str | None) -> str | None:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s+-\s*|\s*-\s+", " - ", s)
    return s or None


def clean(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["reference_id"] = df["ReferenceID"].str.strip()
    out["year"] = pd.to_numeric(df["ReportYear"]).astype(int)
    for src, dst in [
        ("DiagnosisCategory", "diagnosis_category"),
        ("DiagnosisSubCategory", "diagnosis_subcategory"),
        ("TreatmentCategory", "treatment_category"),
        ("TreatmentSubCategory", "treatment_subcategory"),
        ("Type", "type"),
        ("IMRType", "imr_type"),
        ("AgeRange", "age_range"),
        ("PatientGender", "patient_gender"),
    ]:
        out[dst] = df[src].map(_norm_label)
    out["determination_text"] = df["Determination"].str.strip()
    det = out["determination_text"].str.lower()
    if not det.str.contains("overturned|upheld").all():
        raise SchemaError("Determination has values other than Overturned/Upheld: " + str(det.unique()[:10]))
    out["overturned"] = det.str.contains("overturned")
    out["days_to_review"] = pd.to_numeric(df["DaysToReview"], errors="coerce")
    out["days_to_adopt"] = pd.to_numeric(df["DaysToAdopt"], errors="coerce")
    out["findings_original"] = df["Findings"]  # kept unmodified
    return out


# ---------------------------------------------------------------- PII scan
SCAN_ENTITIES = {"EMAIL", "US_SSN", "PHONE", "MEMBER_ID", "CLAIM_NUMBER", "MRN", "DOB", "ADDRESS", "PERSON"}


def pii_scan(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Regex scan over every Findings value; mask hits. Defense in depth (data is published de-identified)."""
    hits: dict[str, int] = {}
    masked = []
    rows_with_hits = 0
    for text in df["findings_original"].fillna(""):
        spans = [s for s in regex_detect(text) if s.entity in SCAN_ENTITIES]
        if spans:
            rows_with_hits += 1
            for sp in sorted(spans, key=lambda s: s.start, reverse=True):
                hits[sp.entity] = hits.get(sp.entity, 0) + 1
                text = text[: sp.start] + f"[{sp.entity}]" + text[sp.end :]
        masked.append(text)
    df = df.copy()
    df["findings"] = masked
    return df, {"rows_with_hits": rows_with_hits, "hits_by_entity": hits}


# ---------------------------------------------------------------- profile
def profile(df: pd.DataFrame, validation: dict, pii: dict, source: str, sha: str) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    charts = REPORTS / "charts"
    charts.mkdir(exist_ok=True)
    lines = ["# IMR dataset profile (D1)", ""]
    if source == "synthetic":
        lines += ["> **SYNTHETIC SAMPLE DATA** - the real download failed. Numbers below are not real.", ""]
    lines += [
        "Source: California Department of Managed Health Care (DMHC), Independent Medical Review (IMR) Determinations, "
        "via the CHHS Open Data Portal (CC BY).",
        "",
        f"- Rows after cleaning: **{len(df):,}**",
        f"- Exact duplicate rows dropped: {validation.get('exact_duplicate_rows_dropped', 0)}",
        f"- Years: {df.year.min()}-{df.year.max()}",
        f"- Overall overturn rate: {df.overturned.mean():.1%}",
        f"- Raw file SHA-256: `{sha}`",
        "",
        "## PII scan of Findings (regex, defense in depth)",
        f"- Rows with at least one hit: {pii['rows_with_hits']}",
        f"- Hits by entity: {pii['hits_by_entity']}",
        "- All hits are masked as `[ENTITY]` before indexing. Most hits are expected false positives "
        "(e.g. reference-style numbers); see the masked text in `imr_case.findings`.",
        "",
    ]

    def table(series: pd.Series, title: str, top: int | None = None) -> None:
        vc = series.value_counts(dropna=False)
        if top:
            vc = vc.head(top)
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Value | Count | Share |")
        lines.append("|---|---:|---:|")
        for k, v in vc.items():
            lines.append(f"| {k} | {v:,} | {v / len(series):.1%} |")
        lines.append("")

    table(df.year.astype(str), "Rows by year")
    table(df.type, "Type")
    table(df.imr_type, "IMRType")
    table(df.determination_text, "Determination")
    table(df.treatment_category, "Top 20 treatment categories", 20)
    table(df.diagnosis_category, "Top 20 diagnosis categories", 20)
    table(df.age_range, "AgeRange (fairness slices only; not a model feature)")
    table(df.patient_gender, "PatientGender (fairness slices only; not a model feature)")

    lines.append("## Overturn rate by Type")
    lines.append("")
    lines.append("| Type | N | Overturned |")
    lines.append("|---|---:|---:|")
    for t, g in df.groupby("type"):
        lines.append(f"| {t} | {len(g):,} | {g.overturned.mean():.1%} |")
    lines.append("")

    lines.append("## Null rates")
    lines.append("")
    lines.append("| Column | Null rate |")
    lines.append("|---|---:|")
    for c in df.columns:
        lines.append(f"| {c} | {df[c].isna().mean():.2%} |")
    lines.append("")
    lens = df.findings_original.fillna("").str.len()
    lines.append("## Findings text length (characters)")
    lines.append("")
    q = lens.quantile([0, 0.25, 0.5, 0.75, 0.95, 1.0])
    lines.append("| min | p25 | median | p75 | p95 | max |")
    lines.append("|---:|---:|---:|---:|---:|---:|")
    lines.append("| " + " | ".join(f"{int(v):,}" for v in q.values) + " |")
    lines.append("")

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 3.5))
        by_year = df.groupby("year").agg(n=("overturned", "size"), rate=("overturned", "mean"))
        ax.bar(by_year.index, by_year.n, color="#4C78A8")
        ax.set_ylabel("IMR decisions")
        ax2 = ax.twinx()
        ax2.plot(by_year.index, by_year.rate * 100, color="#E45756", marker="o", ms=3)
        ax2.set_ylabel("Overturn rate (%)")
        ax.set_title("DMHC IMR decisions per year and overturn rate")
        fig.tight_layout()
        fig.savefig(charts / "imr_by_year.png", dpi=110)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8, 5))
        df.treatment_category.value_counts().head(15)[::-1].plot.barh(ax=ax, color="#4C78A8")
        ax.set_title("Top 15 treatment categories")
        fig.tight_layout()
        fig.savefig(charts / "imr_treatment_top15.png", dpi=110)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(7, 3.5))
        lens.clip(upper=7000).plot.hist(bins=50, ax=ax, color="#72B7B2")
        ax.set_title("Findings length (characters)")
        fig.tight_layout()
        fig.savefig(charts / "imr_findings_length.png", dpi=110)
        plt.close(fig)
        lines += [
            "## Charts",
            "",
            "![by year](charts/imr_by_year.png)",
            "",
            "![treatments](charts/imr_treatment_top15.png)",
            "",
            "![findings length](charts/imr_findings_length.png)",
            "",
        ]
    except Exception as e:  # charts are P1
        lines.append(f"(charts skipped: {e})")
    (REPORTS / "imr_profile.md").write_text("\n".join(lines), encoding="utf-8")


def write_dictionary_summary() -> None:
    text = ""
    if DICT_PATH.exists():
        try:
            from pypdf import PdfReader

            text = "\n".join(p.extract_text() or "" for p in PdfReader(str(DICT_PATH)).pages)
        except Exception:
            text = ""
    md = [
        "# IMR data dictionary (summary)",
        "",
        "Summarized from the DMHC data dictionary PDF (`imrdatadictionary.pdf`) and checked against the real file.",
        "",
        "| Field | Type (dictionary) | Meaning | Notes from profiling |",
        "|---|---|---|---|",
        "| ReferenceID | Plain text | Unique identifier for the case | 39 exact duplicate rows exist in the file; dropped. Prefix encodes type + year (e.g. MN26-, EI02-) |",
        "| ReportYear | Number | Year the case was reported | 2001-2026; 2001 and the current year are partial |",
        "| DiagnosisCategory | Plain text | Main diagnosis category | ~48 values |",
        "| DiagnosisSubCategory | Plain text | Secondary diagnosis category | |",
        "| TreatmentCategory | Plain text | Main treatment category | ~58 values; abbreviated labels (e.g. 'Diag Imag & Screen') |",
        "| TreatmentSubCategory | Plain text | Secondary treatment category | ~500 values |",
        "| Determination | Plain text | Whether the plan's decision was upheld or overturned | 'Overturned Decision of Health Plan' / 'Upheld Decision of Health Plan' |",
        "| Type | Plain text | Case type: Medical Necessity, Experimental/Investigational, Urgent Care | |",
        "| AgeRange | (dictionary lists 'PaientAge', Number) | Patient age | File has banded ranges ('51 to 64', '65+'), not a number - dictionary is out of date |",
        "| PatientGender | Plain text | Patient gender | Female / Male / Other / blank |",
        "| IMRType | (not in dictionary) | Standard vs Expedited review | Present in the file |",
        "| DaysToReview | (not in dictionary) | Days taken to review | Present in the file |",
        "| DaysToAdopt | (not in dictionary) | Days to adopt the decision | Post-decision: target leakage for M3 |",
        "| Findings | Plain text | Summary of the case findings (physician reviewer) | Free text; states the conclusion (leakage for M3) |",
        "",
        "Discrepancies between the dictionary and the file are recorded above; the pipeline validates against the file's real columns.",
        "",
    ]
    if text:
        md += ["## Raw dictionary text (extracted)", "", "```", text.strip()[:4000], "```", ""]
    (REPORTS / "imr_dictionary.md").write_text("\n".join(md), encoding="utf-8")


# ---------------------------------------------------------------- chunking for precedents
_CRED = re.compile(r"Credentials/Qualifications:.*$", re.S)


def precedent_text(findings: str) -> str:
    """Drop the reviewer-credential boilerplate; keep findings + final result."""
    t = _CRED.sub("", findings or "").strip()
    t = t.replace("Final Result:", " Final Result: ")
    return re.sub(r"\s+", " ", t)


def chunk_words(text: str, max_words: int = 300, overlap: int = 40) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text] if text else []
    out = []
    i = 0
    while i < len(words):
        out.append(" ".join(words[i : i + max_words]))
        if i + max_words >= len(words):
            break
        i += max_words - overlap
    return out


# ---------------------------------------------------------------- main step
def run(load_db: bool = True, force: bool = False) -> dict:
    path, source = acquire(force=force)
    acquire_dictionary()
    sha = sha256_file(path)
    manifest = load_manifest()["datasets"].get("imr", {})
    unchanged = manifest.get("sha256") == sha and OUT.exists() and not force
    if unchanged:
        print(f"[imr] unchanged (sha {sha[:12]}), skipping clean/profile")
        df = pd.read_parquet(OUT)
    else:
        raw = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
        try:
            raw, vreport = validate(raw)
        except SchemaError as e:
            log_blocker("D1 IMR schema validation failed", str(e), "Load stopped; synthetic fallback used")
            make_synthetic_sample(SYNTH_PATH)
            path, source = SYNTH_PATH, "synthetic"
            sha = sha256_file(path)
            raw, vreport = validate(pd.read_csv(path, dtype=str))
        df = clean(raw)
        df, pii = pii_scan(df)
        profile(df, vreport, pii, source, sha)
        write_dictionary_summary()
        PROCESSED.mkdir(parents=True, exist_ok=True)
        df.to_parquet(OUT, index=False)
        update_manifest(
            "imr",
            url=URL,
            sha256=sha,
            size_bytes=path.stat().st_size,
            rows=len(df),
            downloaded_at=now_iso(),
            schema_ok=True,
            source=source,
            raw_file=str(path.relative_to(path.parents[2])).replace("\\", "/"),
            pii_scan=pii,
            exact_duplicates_dropped=vreport.get("exact_duplicate_rows_dropped", 0),
        )
    if load_db:
        load(df, source, sha)
    return {"rows": len(df), "source": source, "sha256": sha}


def load(df: pd.DataFrame, source: str, sha: str) -> None:
    from appeal_core.db import session_scope
    from appeal_core.models import DatasetManifest, ImrCase, ImrStats, PrecedentChunk
    from sqlalchemy import delete, func, select

    with session_scope() as s:
        existing = s.scalar(select(func.count()).select_from(ImrCase))
        m = s.get(DatasetManifest, "imr")
        if existing == len(df) and m is not None and m.sha256 == sha:
            print(f"[imr] DB already loaded ({existing} rows), skipping")
            return
        s.execute(delete(PrecedentChunk))
        s.execute(delete(ImrStats))
        s.execute(delete(ImrCase))
    records = df.replace({np.nan: None}).to_dict("records")
    cases = [
        {
            "reference_id": r["reference_id"],
            "year": int(r["year"]),
            "diagnosis_category": r["diagnosis_category"],
            "diagnosis_subcategory": r["diagnosis_subcategory"],
            "treatment_category": r["treatment_category"],
            "treatment_subcategory": r["treatment_subcategory"],
            "type": r["type"],
            "imr_type": r["imr_type"],
            "age_range": r["age_range"],
            "patient_gender": r["patient_gender"],
            "overturned": bool(r["overturned"]),
            "determination_text": r["determination_text"],
            "findings": r["findings"],
            "days_to_review": r["days_to_review"],
        }
        for r in records
    ]
    chunks = []
    for r in records:
        parts = chunk_words(precedent_text(r["findings"] or ""))
        for i, part in enumerate(parts):
            chunks.append(
                {
                    "id": f"{r['reference_id']}#{i}",
                    "reference_id": r["reference_id"],
                    "text": part,
                    "year": int(r["year"]),
                    "treatment_category": r["treatment_category"],
                    "treatment_subcategory": r["treatment_subcategory"],
                    "diagnosis_category": r["diagnosis_category"],
                    "type": r["type"],
                    "overturned": bool(r["overturned"]),
                }
            )
    stats = (
        df.groupby(
            ["treatment_category", "treatment_subcategory", "diagnosis_category", "type", "year"], dropna=False
        )
        .agg(n=("overturned", "size"), overturned_n=("overturned", "sum"))
        .reset_index()
        .replace({np.nan: None})
        .to_dict("records")
    )
    for st in stats:
        st["n"] = int(st["n"])
        st["overturned_n"] = int(st["overturned_n"])
        st["year"] = int(st["year"])
    from sqlalchemy import insert

    with session_scope() as s:
        for i in range(0, len(cases), 5000):
            s.execute(insert(ImrCase), cases[i : i + 5000])
        for i in range(0, len(chunks), 5000):
            s.execute(insert(PrecedentChunk), chunks[i : i + 5000])
        s.execute(insert(ImrStats), stats)
        s.merge(
            DatasetManifest(
                name="imr", url=URL, sha256=sha, rows=len(df), downloaded_at=now_iso(), schema_ok=True, source=source
            )
        )
    print(f"[imr] loaded {len(cases)} cases, {len(chunks)} precedent chunks, {len(stats)} stats rows")
