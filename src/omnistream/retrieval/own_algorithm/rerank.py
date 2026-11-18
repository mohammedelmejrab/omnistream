"""Stable cross-encoder ordering of a bounded prefix of candidates."""

from threading import Lock

MODEL = "BAAI/bge-reranker-base"
WINDOW = 30
_encoder = None
_encoder_lock = Lock()


def local_encoder():
    global _encoder
    with _encoder_lock:
        if _encoder is None:
            from sentence_transformers import CrossEncoder

            _encoder = CrossEncoder(MODEL, device="cpu", local_files_only=True)
        return _encoder


def rerank(question, candidates, text, encoder):
    head = candidates[:WINDOW]
    if len(head) < 2:
        return candidates
    pairs = [(question, text(candidate)) for candidate in head]
    scores = encoder().predict(pairs, batch_size=8, show_progress_bar=False)
    ranked = sorted(
        zip(scores, head, strict=True), key=lambda pair: pair[0], reverse=True
    )
    return [candidate for _, candidate in ranked] + candidates[WINDOW:]
