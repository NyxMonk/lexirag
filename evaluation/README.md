# Evaluation

Tools for measuring retrieval and answer quality per language pair. **Only report numbers produced by an actual run.**

## Layout

```
evaluation/
├── datasets/
│   └── synthetic_v1.jsonl   20 synthetic questions over the synthetic test PDFs
├── benchmarks/
│   └── run_eval.py          ingest → search (→ answer) → metrics
└── results/                 one folder per run (report.json, report.md); git-ignored
```

## Dataset format (JSONL, one item per line)

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `id` | yes | Stable identifier |
| `document` | yes | PDF path, relative to the dataset file |
| `document_language` | yes | `en`, `hi`, `bn`, `mr`, `pa`, `fr` |
| `query_language` | yes | Language the question is written in |
| `question` | yes | The question |
| `relevant_pages` | yes | 1-based PDF pages that contain the answer |
| `relevant_text` | no | Substring that identifies the relevant chunk (in the document's language) |
| `key_facts` | no | Strings an answer should contain (rough check) |
| `scope` | no | `document` (default: search only this PDF) or `workspace` (search every PDF in the run) |
| `synthetic` | no | `true` for invented test content |
| `validated` | no | `true` once a person has checked the question, pages and facts |

`synthetic_v1.jsonl` is **synthetic**. The documents are invented, and the Indic-language questions were written for testing and have **not** been reviewed by native speakers (`validated: false`). Treat its results as a smoke test, not as a quality claim.

### Adding real documents

1. Use public-domain sources such as bare acts, gazette notifications and published judgments. Do not add confidential or client documents.
2. Put the PDFs in `evaluation/datasets/<name>/`, and write questions with the pages and passages verified by hand. Set `validated: true` only after a fluent reviewer has checked the question and the expected answer.
3. Cover each document language with questions in several query languages.

## FIR parser evaluation

`benchmarks/fir_eval.py` checks the FIR explainer's section and offence-date parser (`backend/app/rag/fir.py`). It runs offline, with no server, models or LLM.

- `datasets/fir_sections_synthetic_v1.jsonl` contains 25 **synthetic** FIR snippets in English, Hindi, Marathi, Bengali and Punjabi, with gold `(section, code)` pairs, offence date and code. Two items are hard negatives (house, phone and amount numbers). Its scores are a regression check, not a quality claim.
- `--icdar path/to/FIR_details.json` also reports coverage on the statute strings of the [ICDAR 2023 FIR dataset](https://github.com/legaldocumentprocessing/fir_dataset_icdar2023) (MIT licence).
  - That dataset holds **real, non-anonymised FIRs** (West Bengal, 2017–2021, English and IPC only), and some involve sexual offences.
  - Keep it outside the repo or under `datasets/private/` (git-ignored). Never commit, display or demo its images or names.
  - It has no gold labels, so only aggregate coverage is reported.

```bash
backend/.venv/Scripts/python evaluation/benchmarks/fir_eval.py [--icdar evaluation/datasets/private/FIR_details.json]
```

## Running

The backend must be running with models downloaded. Answer metrics also need an LLM provider.

```bash
backend/.venv/Scripts/python evaluation/benchmarks/run_eval.py            # Windows
backend/.venv/bin/python evaluation/benchmarks/run_eval.py                # macOS
# options: --k 1 3 5 --with-answers --answer-delay 15 --no-rerank --keep-workspace
```

The script creates a temporary workspace, ingests the PDFs, runs every question and deletes the workspace afterwards (`--keep-workspace` keeps it).

## Metrics

| Metric | Definition |
| ------ | ---------- |
| Recall@K | Relevant chunks in the top K ÷ all relevant chunks for the item |
| Precision@K | Relevant chunks in the top K ÷ K |
| MRR | Mean of 1 / rank of the first relevant chunk (0 if none) |
| nDCG@K | Binary-gain DCG of the top K ÷ ideal DCG |
| Citation accuracy | Share of answer citations that point to a relevant chunk |
| Citation page accuracy | Share of citations whose page (exact quote page when available) is a relevant page |
| Key-fact recall | Share of `key_facts` found verbatim in the answer (rough; numbers may be written differently) |

All metrics are reported overall, for cross-lingual items only, and per `document→question` language pair.
