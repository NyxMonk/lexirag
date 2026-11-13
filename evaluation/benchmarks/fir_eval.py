"""Evaluate the FIR section and offence-date parser (backend/app/rag/fir.py). Offline: no server, models or LLM.

1. Synthetic gold set (default): precision/recall of (section, code) pairs, offence-date and code accuracy.
       backend/.venv/Scripts/python evaluation/benchmarks/fir_eval.py
2. Optional, local only: coverage on the statute strings of the ICDAR 2023 FIR dataset
   (github.com/legaldocumentprocessing/fir_dataset_icdar2023, MIT). It contains real, non-anonymised FIRs,
   so keep it outside the repository (or under evaluation/datasets/private/, which is git-ignored) and
   never commit or display its names or images. It has no gold labels, so only coverage is reported.
       ... fir_eval.py --icdar path/to/FIR_details.json

Only report numbers produced by an actual run, and say that the gold set is synthetic.
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag.fir import analyse_fir, lookup_offence, normalise_text  # noqa: E402

DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "fir_sections_synthetic_v1.jsonl"


def evaluate_gold(path: Path) -> dict:
    tp = fp = fn = 0
    date_ok = code_ok = n = 0
    failures = []
    by_lang: Counter = Counter()
    by_lang_ok: Counter = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        n += 1
        result = analyse_fir(item["text"])
        got = {(s.section, s.code) for s in result.sections}
        want = {tuple(p) for p in item["expected_sections"]}
        tp += len(got & want)
        fp += len(got - want)
        fn += len(want - got)
        d_ok = (result.offence_date.isoformat() if result.offence_date else None) == item["expected_offence_date"]
        c_ok = result.applicable_code == item["expected_code"]
        date_ok += d_ok
        code_ok += c_ok
        exact = got == want and d_ok and c_ok
        by_lang[item["language"]] += 1
        by_lang_ok[item["language"]] += exact
        if not exact:
            failures.append({
                "id": item["id"],
                "missing": sorted(want - got),
                "extra": sorted(got - want),
                "date": result.offence_date.isoformat() if result.offence_date else None,
                "expected_date": item["expected_offence_date"],
            })
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "items": n,
        "section_precision": round(precision, 3),
        "section_recall": round(recall, 3),
        "offence_date_accuracy": round(date_ok / n, 3) if n else None,
        "code_accuracy": round(code_ok / n, 3) if n else None,
        "exact_items_by_language": {k: f"{by_lang_ok[k]}/{v}" for k, v in sorted(by_lang.items())},
        "failures": failures,
    }


def evaluate_icdar(path: Path) -> dict:
    """Coverage on category-2 ('Statutes') strings. Real data: only aggregate numbers are printed."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    statutes = [r["text"] for r in rows if r.get("category_id") == 2 and r.get("text")]
    with_any = with_ipc = mentions_ipc = 0
    sections = Counter()
    other_acts = Counter()
    numbers_total = numbers_captured = 0
    for text in statutes:
        result = analyse_fir(text, offence_date=date(2020, 1, 1))  # dataset years are 2017-2021 (IPC era)
        if result.sections:
            with_any += 1
        ipc = [s for s in result.sections if s.code == "IPC" and s.label_source == "explicit"]
        if re.search(r"i\s*\.?\s*p\s*\.?\s*c", text, re.I):
            mentions_ipc += 1
            with_ipc += bool(ipc)
        for s in result.sections:
            if s.label_source == "other_act":
                other_acts[s.code] += 1
            else:
                sections[(s.section, s.code)] += 1
        # Proxy for recall: 1-3 digit numbers in the string that ended up inside a detected section.
        norm = normalise_text(text)
        nums = re.findall(r"(?<!\d)\d{1,3}(?!\d)", norm)
        numbers_total += len(nums)
        captured = {re.match(r"\d+", s.section).group(0) for s in result.sections}  # type: ignore[union-attr]
        numbers_captured += sum(1 for x in nums if x in captured)
    n = len(statutes)
    ipc_mentions = {k: v for k, v in sections.items() if k[1] == "IPC"}
    in_table = sum(v for (s, _), v in ipc_mentions.items() if lookup_offence("IPC", s)[1] is not None)
    missing = Counter({s: v for (s, _), v in ipc_mentions.items() if lookup_offence("IPC", s)[1] is None})
    return {
        "ipc_section_mentions_in_reference_table": f"{in_table}/{sum(ipc_mentions.values())}",
        "most_frequent_missing_from_table": [f"{s}: {k}" for s, k in missing.most_common(10)],
        "statute_strings": n,
        "with_any_section": f"{with_any}/{n}",
        "ipc_strings_with_ipc_sections": f"{with_ipc}/{mentions_ipc}",
        "number_capture_rate": round(numbers_captured / numbers_total, 3) if numbers_total else None,
        "top_sections": [f"{s} {c}: {k}" for (s, c), k in sections.most_common(10)],
        "top_other_acts": [f"{a}: {k}" for a, k in other_acts.most_common(5)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--icdar", type=Path, help="FIR_details.json from the ICDAR 2023 FIR dataset (local only)")
    args = parser.parse_args()

    report = {"synthetic_gold": evaluate_gold(args.dataset)}
    if args.icdar:
        report["icdar2023_coverage"] = evaluate_icdar(args.icdar)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\nNote: the gold set is synthetic (validated: false); treat it as a regression check, not a quality claim.")


if __name__ == "__main__":
    main()
