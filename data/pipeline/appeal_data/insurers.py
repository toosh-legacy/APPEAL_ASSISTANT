"""D3 (P1): CMS Transparency in Coverage PUF -> insurer_stats (issuer level, individual Marketplace QHPs)."""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd

from appeal_data.common import RAW, download, log_blocker, now_iso, sha256_file, update_manifest

PAGE = "https://www.cms.gov/marketplace/resources/data/public-use-files"
URL = "https://download.cms.gov/marketplace-puf/2027/transparency-in-coverage-puf.zip"
DICT_URL = "https://www.cms.gov/files/document/transparency-coverage-datadictionary-py27.pdf"
PATH = RAW / "cms" / "transparency-in-coverage-puf-2027.zip"
SHEET = "Transparency 2027 - Ind QHP"
DATA_PLAN_YEAR = 2025  # the 2027 PUF is derived from plan year 2025 data (CMS disclaimer)
DISCLAIMER = "Claims denials are not necessarily indicative of issuer strength or plan quality."
REQUIRED = [
    "State",
    "Issuer_Name",
    "Issuer_ID",
    "Issuer_Claims_Received_In_Network",
    "Issuer_Claims_Denied_In_Network",
    "Issuer_Claims_Received_Out_Of_Network",
    "Issuer_Claims_Denied_Out_Of_Network",
    "Issuer_Internal_Appeals_Claims_Filed",
    "Issuer_Number_Internal_Appeals_Claims_Overturned",
]


def run(load_db: bool = True, force: bool = False) -> dict:
    try:
        if not PATH.exists() or force:
            download(URL, PATH, retries=3, timeout=180)
        if not (PATH.parent / "datadictionary.pdf").exists():
            download(DICT_URL, PATH.parent / "datadictionary.pdf", retries=2, timeout=60)
        with zipfile.ZipFile(PATH) as z:
            name = next(n for n in z.namelist() if n.endswith(".xlsx"))
            df = pd.read_excel(io.BytesIO(z.read(name)), sheet_name=SHEET, header=2)
    except Exception as e:
        log_blocker("D3 CMS Transparency in Coverage PUF unavailable", str(e), "F9 insurer insights hidden behind FEATURE_INSURER_INSIGHTS=false")
        return {"rows": 0, "source": "missing"}
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        log_blocker("D3 PUF schema changed", f"missing columns {missing}", "F9 hidden")
        return {"rows": 0, "source": "schema_mismatch"}
    iss = df[REQUIRED].drop_duplicates(["Issuer_ID", "State"]).copy()

    def num(c):
        return pd.to_numeric(iss[c], errors="coerce")

    out = pd.DataFrame(
        {
            "plan_year": DATA_PLAN_YEAR,
            "state": iss.State.astype(str).str.strip(),
            "issuer": iss.Issuer_Name.astype(str).str.strip(),
            "claims_received": num("Issuer_Claims_Received_In_Network").fillna(0) + num("Issuer_Claims_Received_Out_Of_Network").fillna(0),
            "claims_denied": num("Issuer_Claims_Denied_In_Network").fillna(0) + num("Issuer_Claims_Denied_Out_Of_Network").fillna(0),
            "appeals_filed": num("Issuer_Internal_Appeals_Claims_Filed"),
            "appeals_overturned": num("Issuer_Number_Internal_Appeals_Claims_Overturned"),
        }
    )
    reported = num("Issuer_Claims_Received_In_Network").notna() | num("Issuer_Claims_Received_Out_Of_Network").notna()
    out = out[reported.values & (out.claims_received > 0)].reset_index(drop=True)
    sha = sha256_file(PATH)
    update_manifest("insurers", url=URL, page=PAGE, sha256=sha, rows=len(out), downloaded_at=now_iso(), schema_ok=True, source="real", data_plan_year=DATA_PLAN_YEAR, disclaimer=DISCLAIMER)
    if load_db:
        from appeal_core.db import session_scope
        from appeal_core.models import DatasetManifest, InsurerStats
        from sqlalchemy import delete, insert

        recs = out.replace({np.nan: None}).to_dict("records")
        for r in recs:
            for k in ("claims_received", "claims_denied", "appeals_filed", "appeals_overturned"):
                r[k] = int(r[k]) if r[k] is not None else None
        with session_scope() as s:
            s.execute(delete(InsurerStats))
            if recs:
                s.execute(insert(InsurerStats), recs)
            s.merge(DatasetManifest(name="insurers", url=URL, sha256=sha, rows=len(out), downloaded_at=now_iso(), schema_ok=True, source="real"))
        print(f"[insurers] loaded {len(out)} issuer rows (plan year {DATA_PLAN_YEAR})")
    return {"rows": len(out), "source": "real"}
