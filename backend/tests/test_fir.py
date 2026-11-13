"""FIR explainer: section and date parsing (pure) and the /fir/analyze API.

All FIR text here is synthetic (invented names, places and case numbers).
"""

from datetime import date

import pytest

from app.rag import fir


def _pairs(text: str, default_code: str | None = None) -> list[tuple[str, str | None]]:
    return [(s.section, s.code) for s in fir.detect_sections(text, default_code)]


# ── sections ──
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("498A/406/34 Ipc", [("498A", "IPC"), ("406", "IPC"), ("34", "IPC")]),
        ("u/s 379 IPC. Ph: 9876543210, amount Rs 50,000", [("379", "IPC")]),
        ("IPC Sec 323/504/506", [("323", "IPC"), ("504", "IPC"), ("506", "IPC")]),
        ("Section 302 of the Indian Penal Code, 1860", [("302", "IPC")]),
        ("354 B IPC and 376(2)(n) I.P.C.", [("354B", "IPC"), ("376(2)(n)", "IPC")]),
        (
            "under sections 115(2), 352 and 351(2) BNS read with 3(5)",
            [("115(2)", "BNS"), ("352", "BNS"), ("351(2)", "BNS"), ("3(5)", "BNS")],
        ),
        ("Section 103(1) of the Bharatiya Nyaya Sanhita, 2023", [("103(1)", "BNS")]),
        ("धारा ३०२, ३४ भा.दं.सं. के अंतर्गत", [("302", "IPC"), ("34", "IPC")]),
        ("भारतीय न्याय संहिता की धारा 303(2)", [("303(2)", "BNS")]),
        ("भादंवि कलम 420, 406 अन्वये", [("420", "IPC"), ("406", "IPC")]),
        ("धारा 498ए, 354बी भादवि", [("498A", "IPC"), ("354B", "IPC")]),
        ("धारा 34 एवं 302 भा.दं.सं.", [("34", "IPC"), ("302", "IPC")]),
        ("ধারা ৪২০/৪০৬ ভারতীয় দণ্ডবিধি", [("420", "IPC"), ("406", "IPC")]),
        ("ਧਾਰਾ 379 ਆਈ.ਪੀ.ਸੀ", [("379", "IPC")]),
        ("188/269 Ipc &Amp; 51 Disaster Management Act-2005.",
         [("188", "IPC"), ("269", "IPC"), ("51", "Disaster Management Act, 2005")]),
    ],
)
def test_detect_sections(text, expected) -> None:
    assert _pairs(text) == expected


def test_procedure_code_sections_are_not_offences() -> None:
    assert _pairs("arrested u/s 41 CrPC; charge sheet u/s 173 BNSS; offence u/s 379 IPC") == [("379", "IPC")]
    assert _pairs("धारा 154 दं.प्र.सं.") == []


def test_numbers_without_a_section_anchor_are_ignored() -> None:
    assert _pairs("Mobile 98765 43210, vehicle MH 12 AB 1234, Rs 302 paid on 12/07/2024") == []


def test_unlabelled_sections_follow_the_offence_date() -> None:
    assert _pairs("u/s 302", None) == [("302", None)]
    assert _pairs("धारा 302", "BNS") == [("302", "BNS")]


def test_canonical_section() -> None:
    assert fir.canonical_section("498 a") == "498A"
    assert fir.canonical_section("103 (1)") == "103(1)"
    assert fir.canonical_section("125 (B)") == "125(b)"


# ── dates and code selection ──
def test_occurrence_date_wins_over_report_date() -> None:
    a = fir.analyse_fir("FIR registered on 05/08/2024. Date of occurrence: 02/08/2024. Offence u/s 303(2), 3(5) BNS")
    assert a.offence_date == date(2024, 8, 2)
    assert a.offence_date_source == "occurrence"
    assert a.applicable_code == "BNS"
    assert a.warnings == []


def test_native_digit_dates_and_inferred_code() -> None:
    a = fir.analyse_fir("घटना की तारीख: १२.०३.२०२३  सूचना दर्ज: 14.03.2023  धारा 379 के तहत")
    assert a.offence_date == date(2023, 3, 12)
    assert [(s.section, s.code, s.label_source) for s in a.sections] == [("379", "IPC", "offence_date")]


def test_earliest_date_is_used_when_unlabelled() -> None:
    a = fir.analyse_fir("Dated 20 July 2024. Incident reported. 18/07/2024 u/s 115(2) BNS")
    assert a.offence_date_source in {"occurrence", "earliest"}
    assert a.offence_date == date(2024, 7, 18)


def test_provided_date_overrides_and_cutoff_is_inclusive() -> None:
    assert fir.analyse_fir("u/s 302", date(2024, 7, 1)).applicable_code == "BNS"
    assert fir.analyse_fir("u/s 302", date(2024, 6, 30)).applicable_code == "IPC"


def test_code_mismatch_is_warned() -> None:
    a = fir.analyse_fir("Date of occurrence: 10/09/2024. Case u/s 420 IPC")
    assert any("IPC sections but the offence date" in w for w in a.warnings)


# ── reference table ──
def test_reference_table_is_consistent() -> None:
    table = fir.load_offence_table()
    assert table["meta"]["validated"] is False  # hand-compiled; never presented as verified
    allowed = {"cognizable", "non-cognizable", "depends"}, {"bailable", "non-bailable", "depends"}
    for code in ("IPC", "BNS"):
        for key, entry in table[code].items():
            assert fir.canonical_section(key) == key
            assert entry["cognizable"] in allowed[0] and entry["bailable"] in allowed[1], (code, key)
            assert entry["kind"] in {"offence", "liability"}
    # Every BNS -> IPC link points to an IPC entry and back.
    for key, entry in table["BNS"].items():
        for ipc in entry["corresponds_to"]:
            assert key in table["IPC"][ipc]["corresponds_to"], (key, ipc)


def test_lookup_falls_back_to_listed_sub_section() -> None:
    assert fir.lookup_offence("BNS", "103(1)")[0] == "103(1)"
    assert fir.lookup_offence("BNS", "103")[0] == "103(1)"
    assert fir.lookup_offence("IPC", "999") == (None, None)


# ── API ──
def test_analyze_text(client) -> None:
    text = "Date of occurrence: 03/02/2022. FIR u/s 498A/406/34 IPC and u/s 41 CrPC."
    r = client.post("/api/v1/fir/analyze", json={"text": text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applicable_code"] == "IPC"
    assert body["offence_date"] == "2022-02-03"
    assert [c["section"] for c in body["charges"]] == ["498A", "406", "34"]
    cruelty = body["charges"][0]
    assert cruelty["in_reference"] and cruelty["bailable"] == "non-bailable"
    assert cruelty["corresponds_to"][0] == {"code": "BNS", "section": "85", "title": cruelty["title"]}
    assert body["charges"][2]["kind"] == "liability"
    assert body["reference"]["validated"] is False
    assert "Not legal advice" in body["disclaimer"]


def test_analyze_unknown_section_and_date_override(client) -> None:
    r = client.post("/api/v1/fir/analyze", json={"text": "u/s 999 and u/s 302", "offence_date": "2024-08-01"})
    body = r.json()
    assert body["offence_date_source"] == "provided" and body["applicable_code"] == "BNS"
    charges = {c["section"]: c for c in body["charges"]}
    assert charges["999"]["in_reference"] is False and charges["999"]["title"] is None
    # "302" under the BNS is not murder; it must not borrow the IPC entry.
    assert charges["302"]["code"] == "BNS" and charges["302"]["in_reference"] is False


def test_analyze_validation(client) -> None:
    assert client.post("/api/v1/fir/analyze", json={}).status_code == 422
    r = client.post("/api/v1/fir/analyze", json={"text": "x", "document_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 422
    r = client.post("/api/v1/fir/analyze", json={"document_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 404


@pytest.fixture
def sync_queue(monkeypatch):
    from app.services import processing

    monkeypatch.setattr(processing.queue, "submit", processing.run_pipeline)


def _fir_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    lines = [
        "FIRST INFORMATION REPORT (SYNTHETIC SAMPLE)",
        "Police Station: Example Nagar   FIR No. 0000/2024",
        "Date and time of report: 14/08/2024 18:30",
        "Date of occurrence: 12/08/2024",
        "Acts and sections: Bharatiya Nyaya Sanhita, 2023 - 318(4), 316(2), 3(5)",
        "Brief facts: The complainant states that the accused persons took an advance",
        "for supplying goods, issued a false receipt and did not deliver the goods.",
    ]
    for i, line in enumerate(lines):
        page.insert_text((50, 72 + i * 20), line, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def test_analyze_document_and_workspace_isolation(client, workspace, fake_models, sync_queue) -> None:
    up = client.post(
        "/api/v1/documents/upload",
        data={"workspace_id": workspace["id"]},
        files={"file": ("fir.pdf", _fir_pdf(), "application/pdf")},
    )
    assert up.status_code == 201, up.text
    doc_id = up.json()["id"]
    r = client.post("/api/v1/fir/analyze", json={"document_id": doc_id, "workspace_id": workspace["id"]})
    assert r.status_code == 422  # not processed yet

    assert client.post(f"/api/v1/documents/{doc_id}/process").status_code == 202
    r = client.post("/api/v1/fir/analyze", json={"document_id": doc_id, "workspace_id": workspace["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == {"kind": "document", "document_id": doc_id, "document_name": "fir.pdf",
                              "characters": body["source"]["characters"]}
    assert body["offence_date"] == "2024-08-12" and body["offence_date_source"] == "occurrence"
    assert [(c["section"], c["code"]) for c in body["charges"]] == [("318(4)", "BNS"), ("316(2)", "BNS"), ("3(5)", "BNS")]

    other = client.post("/api/v1/workspaces", json={"name": "Other"}).json()
    r = client.post("/api/v1/fir/analyze", json={"document_id": doc_id, "workspace_id": other["id"]})
    assert r.status_code == 404
