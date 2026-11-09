"""LexiRAG retrieval and answer evaluation.

Runs a JSONL dataset against a running LexiRAG API: ingests the referenced PDFs
into a fresh workspace, waits for processing, then for every question measures
retrieval (via /search) and optionally answers (via /chat/query).

    python evaluation/benchmarks/run_eval.py --dataset evaluation/datasets/synthetic_v1.jsonl
    python evaluation/benchmarks/run_eval.py --dataset ... --k 1 3 5 --with-answers

Metrics (binary relevance; a retrieved chunk is relevant when it belongs to the
item's document, overlaps one of ``relevant_pages`` and, if given, contains
``relevant_text``):

    Recall@K, Precision@K, MRR, nDCG@K  - overall and per (document -> question) language pair
    citation accuracy                   - share of answer citations that point to a relevant chunk
    citation page accuracy              - share of citations whose (quote) page is a relevant page
    key-fact recall                     - share of key_facts that appear in the answer (rough, string match)

Results are written to evaluation/results/<timestamp>/ as JSON and Markdown.
Only numbers produced by an actual run should ever be reported.
"""

import argparse
import datetime as dt
import json
import math
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def load_dataset(path: Path) -> list[dict]:
    items = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            item = json.loads(line)
            for key in ("id", "document", "question", "query_language", "document_language", "relevant_pages"):
                if key not in item:
                    raise SystemExit(f"{path}:{n} is missing '{key}'")
            item["_document_path"] = (path.parent / item["document"]).resolve()
            items.append(item)
    return items


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def is_relevant(passage: dict, item: dict, doc_id: str, content: str | None) -> bool:
    if passage["document_id"] != doc_id:
        return False
    pages = set(range(passage["page_start"], passage["page_end"] + 1))
    if not pages & set(item["relevant_pages"]):
        return False
    needle = item.get("relevant_text")
    return not needle or (content is not None and norm(needle) in norm(content))


def dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ingest(client: httpx.Client, workspace_id: str, paths: set[Path]) -> dict[Path, dict]:
    docs = {}
    for path in sorted(paths):
        r = client.post(
            "/documents/upload",
            data={"workspace_id": workspace_id},
            files={"file": (path.name, path.read_bytes(), "application/pdf")},
        )
        r.raise_for_status()
        doc = r.json()
        if doc["processing_status"] == "uploaded":
            client.post(f"/documents/{doc['id']}/process").raise_for_status()
        docs[path] = doc
    deadline = time.time() + 1800
    while time.time() < deadline:
        statuses = {p: client.get(f"/documents/{d['id']}/status").json() for p, d in docs.items()}
        if all(s["processing_status"] in ("completed", "failed") for s in statuses.values()):
            failed = {p.name: s["processing_error"] for p, s in statuses.items() if s["processing_status"] == "failed"}
            if failed:
                raise SystemExit(f"Processing failed: {failed}")
            return docs
        time.sleep(2)
    raise SystemExit("Timed out waiting for documents to process.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/datasets/synthetic_v1.jsonl")
    parser.add_argument("--k", type=int, nargs="+", default=[1, 3, 5])
    parser.add_argument("--with-answers", action="store_true", help="also call /chat/query (needs an LLM provider)")
    parser.add_argument("--answer-delay", type=float, default=0.0, help="seconds between answer calls (rate limits)")
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--keep-workspace", action="store_true")
    args = parser.parse_args()

    items = load_dataset(args.dataset)
    max_k = max(args.k)
    client = httpx.Client(base_url=args.api.rstrip("/"), timeout=300)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    workspace = client.post(
        "/workspaces", json={"name": f"Evaluation {stamp}", "description": f"Dataset {args.dataset.name}"}
    ).json()
    print(f"Workspace {workspace['id']}: ingesting {len({i['_document_path'] for i in items})} document(s)...")
    started = time.time()
    docs = ingest(client, workspace["id"], {i["_document_path"] for i in items})
    print(f"Processed in {time.time() - started:.0f}s")

    # Count relevant chunks per item (denominator for recall and ideal DCG).
    chunk_cache: dict[str, list[dict]] = {}
    per_item = []
    for item in items:
        doc = docs[item["_document_path"]]
        if doc["id"] not in chunk_cache:
            chunk_cache[doc["id"]] = client.get(f"/documents/{doc['id']}/chunks", params={"limit": 200}).json()["items"]
        n_relevant = sum(
            is_relevant({**c, "document_id": doc["id"]}, item, doc["id"], c["content"]) for c in chunk_cache[doc["id"]]
        )
        payload = {"workspace_id": workspace["id"], "query": item["question"], "top_k": max_k, "rerank": not args.no_rerank}
        if item.get("scope", "document") == "document":
            payload["document_ids"] = [doc["id"]]
        t0 = time.perf_counter()
        r = client.post("/search", json=payload)
        latency = time.perf_counter() - t0
        r.raise_for_status()
        body = r.json()
        passages = body["retrieval"]["passages"]
        rel = [int(is_relevant(p, item, doc["id"], p.get("content"))) for p in passages]
        result = {
            "id": item["id"],
            "pair": f"{item['document_language']}->{item['query_language']}",
            "scope": item.get("scope", "document"),
            "detected_query_language": body["query_language"],
            "relevant_chunks": n_relevant,
            "relevance": rel,
            "top1": {k: passages[0][k] for k in ("document_name", "page_start", "page_end")} if passages else None,
            "search_seconds": round(latency, 2),
            "reranked": body["retrieval"]["reranked"],
        }
        first = next((i for i, r_ in enumerate(rel) if r_), None)
        result["rr"] = 0.0 if first is None else 1.0 / (first + 1)
        for k in args.k:
            hits = sum(rel[:k])
            result[f"recall@{k}"] = hits / n_relevant if n_relevant else 0.0
            result[f"precision@{k}"] = hits / k
            ideal = dcg([1] * min(n_relevant, k))
            result[f"ndcg@{k}"] = dcg(rel[:k]) / ideal if ideal else 0.0

        if args.with_answers:
            if args.answer_delay and per_item:
                time.sleep(args.answer_delay)
            q = {"workspace_id": workspace["id"], "question": item["question"]}
            if "document_ids" in payload:
                q["document_ids"] = payload["document_ids"]
            a = client.post("/chat/query", json=q)
            if a.status_code == 200:
                answer = a.json()
                cites = answer["citations"]
                content = {c["id"]: c["content"] for c in chunk_cache[doc["id"]]}
                ok = [
                    is_relevant(c, item, doc["id"], content.get(c["chunk_id"])) for c in cites
                ]
                page_ok = [(c.get("quote_page") or c["page_start"]) in item["relevant_pages"] for c in cites]
                facts = item.get("key_facts") or []
                result["answer"] = {
                    "status": 200,
                    "language": answer["language"],
                    "evidence_sufficient": answer["evidence_sufficient"],
                    "citations": len(cites),
                    "citation_accuracy": sum(ok) / len(cites) if cites else None,
                    "citation_page_accuracy": sum(page_ok) / len(cites) if cites else None,
                    "key_fact_recall": (sum(norm(f) in norm(answer["answer"]) for f in facts) / len(facts)) if facts else None,
                    "text": answer["answer"],
                }
            else:
                result["answer"] = {"status": a.status_code, "error": a.json().get("error")}
        per_item.append(result)
        marker = "✓" if result["rr"] == 1.0 else ("~" if result["rr"] else "✗")
        print(f"  {marker} {item['id']:<18} {result['pair']:<7} RR={result['rr']:.2f}")

    def summarise(rows: list[dict]) -> dict:
        out = {"n": len(rows), "mrr": statistics.fmean(r["rr"] for r in rows)}
        for k in args.k:
            for m in ("recall", "precision", "ndcg"):
                out[f"{m}@{k}"] = statistics.fmean(r[f"{m}@{k}"] for r in rows)
        answered = [r["answer"] for r in rows if r.get("answer", {}).get("status") == 200]
        if answered:
            for m in ("citation_accuracy", "citation_page_accuracy", "key_fact_recall"):
                vals = [a[m] for a in answered if a[m] is not None]
                out[m] = statistics.fmean(vals) if vals else None
            out["answers"] = len(answered)
        return out

    by_pair: dict[str, list[dict]] = defaultdict(list)
    for r in per_item:
        by_pair[r["pair"]].append(r)
    report = {
        "dataset": str(args.dataset.relative_to(ROOT)) if args.dataset.is_relative_to(ROOT) else str(args.dataset),
        "synthetic": all(i.get("synthetic") for i in items),
        "validated": all(i.get("validated") for i in items),
        "timestamp": stamp,
        "settings": client.get("/settings/models").json()["retrieval"],
        "overall": summarise(per_item),
        "cross_lingual": summarise([r for r in per_item if r["pair"].split("->")[0] != r["pair"].split("->")[1]]),
        "by_language_pair": {pair: summarise(rows) for pair, rows in sorted(by_pair.items())},
        "items": per_item,
    }

    out_dir = ROOT / "evaluation" / "results" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    cols = ["n", "mrr"] + [f"{m}@{k}" for k in args.k for m in ("recall", "precision", "ndcg")]
    lines = [
        f"# LexiRAG evaluation {stamp}",
        "",
        f"Dataset: `{report['dataset']}` (synthetic: {report['synthetic']}, manually validated: {report['validated']})",
        "",
        "| Slice | " + " | ".join(cols) + " |",
        "|---" * (len(cols) + 1) + "|",
    ]
    for name, summary in [("overall", report["overall"]), ("cross-lingual", report["cross_lingual"])] + list(
        report["by_language_pair"].items()
    ):
        lines.append(f"| {name} | " + " | ".join(
            str(summary[c]) if c == "n" else f"{summary[c]:.3f}" for c in cols) + " |")
    if args.with_answers and report["overall"].get("answers"):
        o = report["overall"]
        lines += ["", f"Answers: {o['answers']}/{o['n']}, citation accuracy {o['citation_accuracy']}, "
                      f"citation page accuracy {o['citation_page_accuracy']}, key-fact recall {o['key_fact_recall']}"]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nSaved {out_dir}")

    if not args.keep_workspace:
        client.delete(f"/workspaces/{workspace['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
