"""LexiRAG maintenance commands.

    python -m app.cli download-models      # fetch embedding + reranker models (explicit, one-time)
    python -m app.cli models-status        # are the models downloaded? (exit code 1 if not)
    python -m app.cli check-models         # load both models and report device / dimension
    python -m app.cli ocr-status           # Tesseract availability and language packs
    python -m app.cli process <document-id> [--force]   # (re)process one document synchronously
"""

import argparse
import logging
import sys
import time
import uuid

from app.core.config import get_settings
from app.core.logging import configure_logging


def _download(args: argparse.Namespace) -> int:
    from app.rag.model_store import download_model, model_disk_size

    settings = get_settings()
    models = [settings.embedding_model]
    if settings.reranker_enabled or args.include_reranker:
        models.append(settings.reranker_model)
    for model_id in models:
        started = time.perf_counter()
        print(f"> {model_id}")
        path = download_model(model_id, settings)
        size = model_disk_size(path) / 1024**3
        print(f"  stored in {path} ({size:.2f} GB, {time.perf_counter() - started:.0f}s)")
    return 0


def _status(_: argparse.Namespace) -> int:
    from app.rag.model_store import model_is_downloaded

    settings = get_settings()
    wanted = [settings.embedding_model] + ([settings.reranker_model] if settings.reranker_enabled else [])
    missing = [m for m in wanted if not model_is_downloaded(m, settings)]
    for model_id in wanted:
        print(f"{model_id}: {'missing' if model_id in missing else 'downloaded'}")
    return 1 if missing else 0


def _check(_: argparse.Namespace) -> int:
    from app.rag.embeddings import get_embedding_model
    from app.rag.reranking import get_reranker

    embedder = get_embedding_model()
    vector = embedder.embed_query("What are the termination conditions?")
    print(f"embedding: {embedder.model_id} on {embedder.device}, dim={len(vector)}, load {embedder.load_seconds:.1f}s")
    reranker = get_reranker()
    if reranker is None:
        print("reranker: disabled")
    else:
        scores = reranker.score("termination", ["The agreement may be terminated.", "Rent is due monthly."])
        print(f"reranker: {reranker.model_id} scores={['%.3f' % s for s in scores]}")
    return 0


def _ocr(_: argparse.Namespace) -> int:
    from app.rag.ocr import ocr_status

    settings = get_settings()
    status = ocr_status(settings.tesseract_cmd, settings.ocr_languages)
    print(f"available: {status.available}")
    print(f"version:   {status.version}")
    print(f"installed: {', '.join(status.installed_languages) or '-'}")
    print(f"missing:   {', '.join(status.missing_languages) or '-'}")
    if status.message:
        print(f"note:      {status.message}")
    return 0


def _process(args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.services import processing

    document_id = uuid.UUID(args.document_id)
    with SessionLocal() as db:
        processing.claim_for_processing(db, document_id, force=args.force)
    processing.run_pipeline(document_id)
    with SessionLocal() as db:
        from app.models import Document

        doc = db.get(Document, document_id)
        print(f"status={doc.processing_status} chunks={doc.chunk_count} language={doc.detected_language}")
        if doc.processing_error:
            print(f"error: {doc.processing_error}")
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging(get_settings().log_level)
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    dl = sub.add_parser("download-models", help="download the embedding and reranker models")
    dl.add_argument("--include-reranker", action="store_true", help="download the reranker even if disabled")
    dl.set_defaults(func=_download)
    sub.add_parser("models-status", help="report whether models are downloaded").set_defaults(func=_status)
    sub.add_parser("check-models", help="load the models and run a smoke test").set_defaults(func=_check)
    sub.add_parser("ocr-status", help="show Tesseract status").set_defaults(func=_ocr)
    pr = sub.add_parser("process", help="process one document synchronously")
    pr.add_argument("document_id")
    pr.add_argument("--force", action="store_true", help="re-index even if already completed")
    pr.set_defaults(func=_process)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        message = getattr(exc, "message", None) or str(exc)
        print(f"error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
