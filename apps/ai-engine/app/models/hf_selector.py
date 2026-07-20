"""
Hugging Face model discovery + benchmarking harness.

Per spec: don't hardcode one model. Query the Hub for candidates in relevant
categories, score them on the criteria that actually matter for a production forex
service, and let the ranking decide — with the reasoning visible, not a black box.

Two things this deliberately does NOT do:
1. Silently pick a general-purpose multilingual NLP model (e.g. mT5) for numeric
   time-series forecasting just because it's popular — the scoring model penalizes
   task/domain mismatch explicitly (see `_task_relevance_score`).
2. Trust the Hub's "downloads" number as a quality signal on its own — it's one
   input among several, weighted modestly, since download count reflects popularity
   more than fitness for *this* task.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from huggingface_hub import HfApi, ModelInfo

# Task categories relevant to forex market analysis, in the Hub's own tag vocabulary.
RELEVANT_PIPELINE_TAGS = [
    "time-series-forecasting",
    "text-classification",  # financial sentiment/news classification
    "reinforcement-learning",
]

# Keywords that indicate genuine finance/trading relevance vs. a generic NLP model
# that merely *could* be repurposed. Used to penalize domain mismatch.
FINANCE_KEYWORDS = {
    "finance", "financial", "stock", "trading", "forex", "market", "economic",
    "quant", "time-series", "timeseries", "forecasting",
}

# Licenses considered safe for a production commercial deployment without extra
# legal review. Anything outside this set is flagged, not auto-rejected.
PRODUCTION_SAFE_LICENSES = {
    "apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause", "openrail",
}


@dataclass
class ModelCandidate:
    model_id: str
    pipeline_tag: str | None
    downloads: int
    likes: int
    license: str | None
    tags: list[str] = field(default_factory=list)
    last_modified: str | None = None

    # Filled in during benchmarking (best-effort; some fields require actually
    # loading the model, which is only done for the shortlist, not every candidate).
    approx_param_count: float | None = None  # in millions
    measured_latency_ms: float | None = None
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def composite_score(self) -> float:
        return sum(self.scores.values())


def _task_relevance_score(candidate: ModelCandidate) -> float:
    """0-30 points: does this model's tags/id actually indicate finance/time-series fit?"""
    text = f"{candidate.model_id} {' '.join(candidate.tags)}".lower()
    hits = sum(1 for kw in FINANCE_KEYWORDS if kw in text)
    score = min(hits * 6, 24)
    if candidate.pipeline_tag == "time-series-forecasting":
        score += 6
    return min(score, 30)


def _license_score(candidate: ModelCandidate) -> float:
    """0-15 points: production-safe license required for a commercial platform."""
    if candidate.license and candidate.license.lower() in PRODUCTION_SAFE_LICENSES:
        return 15
    if candidate.license:
        return 3  # exists but needs legal review before commercial use
    return 0


def _adoption_score(candidate: ModelCandidate) -> float:
    """0-15 points, log-scaled so a handful of huge outlier models don't dominate."""
    import math

    if candidate.downloads <= 0:
        return 0.0
    return min(math.log10(candidate.downloads + 1) * 2.5, 15)


def _size_score(candidate: ModelCandidate) -> float:
    """
    0-15 points: prefer models small enough to serve with reasonable inference
    latency/GPU cost. This is a production platform, not a research benchmark —
    a 70B model with marginally better accuracy is a worse choice than a 1B model
    that fits a single consumer GPU and meets latency SLAs.
    """
    if candidate.approx_param_count is None:
        return 5.0  # unknown -> neutral, not penalized/rewarded
    if candidate.approx_param_count <= 500:
        return 15.0
    if candidate.approx_param_count <= 3000:
        return 10.0
    if candidate.approx_param_count <= 13000:
        return 4.0
    return 0.0


def _latency_score(candidate: ModelCandidate) -> float:
    """0-25 points: measured inference latency, the highest-weighted criterion for a
    live trading service where a slow signal is a stale, worthless signal."""
    if candidate.measured_latency_ms is None:
        return 0.0
    if candidate.measured_latency_ms <= 50:
        return 25.0
    if candidate.measured_latency_ms <= 200:
        return 18.0
    if candidate.measured_latency_ms <= 500:
        return 10.0
    if candidate.measured_latency_ms <= 1500:
        return 4.0
    return 0.0


def discover_candidates(api: HfApi, limit_per_tag: int = 15) -> list[ModelCandidate]:
    candidates: dict[str, ModelCandidate] = {}
    for tag in RELEVANT_PIPELINE_TAGS:
        for info in api.list_models(pipeline_tag=tag, sort="downloads", direction=-1, limit=limit_per_tag):
            info: ModelInfo
            candidates[info.id] = ModelCandidate(
                model_id=info.id,
                pipeline_tag=info.pipeline_tag,
                downloads=info.downloads or 0,
                likes=info.likes or 0,
                license=(info.card_data or {}).get("license") if info.card_data else None,
                tags=info.tags or [],
                last_modified=str(info.last_modified) if info.last_modified else None,
            )

    # Also explicitly search finance-keyword models outside the three pipeline tags
    # above (e.g. finance-tuned encoder models used for sentiment/classification
    # feature inputs rather than end-to-end forecasting).
    for query in ["financial sentiment", "stock forecasting", "forex", "time series transformer"]:
        for info in api.list_models(search=query, sort="downloads", direction=-1, limit=limit_per_tag):
            if info.id not in candidates:
                candidates[info.id] = ModelCandidate(
                    model_id=info.id,
                    pipeline_tag=info.pipeline_tag,
                    downloads=info.downloads or 0,
                    likes=info.likes or 0,
                    license=(info.card_data or {}).get("license") if info.card_data else None,
                    tags=info.tags or [],
                    last_modified=str(info.last_modified) if info.last_modified else None,
                )

    return list(candidates.values())


def score_candidates(candidates: list[ModelCandidate]) -> list[ModelCandidate]:
    for c in candidates:
        c.scores = {
            "task_relevance": _task_relevance_score(c),
            "license": _license_score(c),
            "adoption": _adoption_score(c),
            "size": _size_score(c),
            "latency": _latency_score(c),
        }
    return sorted(candidates, key=lambda c: c.composite_score, reverse=True)


def measure_latency_ms(model_id: str, n_runs: int = 5) -> float | None:
    """
    Loads the shortlisted model and measures real single-inference wall-clock latency
    on a representative input. Only run this against your shortlist (top ~5), not
    every discovered candidate — downloading/loading every model on the Hub is
    neither fast nor a responsible use of shared bandwidth.
    """
    try:
        from transformers import AutoModel, AutoTokenizer
    except ImportError:
        return None

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModel.from_pretrained(model_id)
        model.eval()

        sample_text = "EURUSD broke above the 1.0850 resistance level on strong US jobs data."
        inputs = tokenizer(sample_text, return_tensors="pt")

        import torch

        with torch.no_grad():
            model(**inputs)  # warmup
            start = time.perf_counter()
            for _ in range(n_runs):
                model(**inputs)
            elapsed = time.perf_counter() - start

        return (elapsed / n_runs) * 1000
    except Exception:
        return None


def select_best_model(hf_token: str | None = None, benchmark_top_n: int = 5) -> tuple[ModelCandidate, list[ModelCandidate]]:
    """
    Full pipeline: discover -> score on static criteria -> benchmark real latency on
    the top N -> re-score including latency -> return the winner plus full ranking
    for transparency (log/display this, don't just silently swap models).
    """
    api = HfApi(token=hf_token)
    candidates = discover_candidates(api)
    ranked = score_candidates(candidates)

    for c in ranked[:benchmark_top_n]:
        c.measured_latency_ms = measure_latency_ms(c.model_id)

    ranked = score_candidates(ranked)  # re-rank with latency scores now populated
    if not ranked:
        raise RuntimeError("No candidate models discovered — check network/HF token.")
    return ranked[0], ranked
