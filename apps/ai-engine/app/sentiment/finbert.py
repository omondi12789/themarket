"""
Financial news sentiment scoring using FinBERT (ProsusAI/finbert on Hugging Face) —
a BERT model fine-tuned specifically on financial text, chosen over a generic
sentiment model for the same reason app/models/hf_selector.py penalizes
domain-mismatched models: general-purpose sentiment models are tuned on product
reviews/tweets and misread financial-neutral language (e.g. "rates unchanged") as
negative far more often than a finance-tuned model does.

Falls back to a small hand-built financial lexicon scorer if the transformer model
can't be loaded (no network to download weights, no GPU/CPU budget, etc.) — this
fallback is explicitly weaker and every response says so via `method`, rather than
silently returning a number that looks the same either way.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

_FINBERT_MODEL_ID = "ProsusAI/finbert"

# Deliberately small and conservative — a fallback, not a real sentiment model. Only
# used when FinBERT can't be loaded, and every result using it says so explicitly.
_POSITIVE_WORDS = {
    "beat", "beats", "surge", "surged", "rally", "rallied", "gain", "gains", "growth",
    "strong", "strength", "upgrade", "upgraded", "bullish", "outperform", "record",
    "expansion", "recovery", "boost", "boosted", "optimism", "optimistic",
}
_NEGATIVE_WORDS = {
    "miss", "missed", "plunge", "plunged", "slump", "slumped", "loss", "losses",
    "weak", "weakness", "downgrade", "downgraded", "bearish", "underperform",
    "recession", "contraction", "crisis", "cut", "cuts", "cautious", "concern", "concerns",
}


@dataclass(frozen=True)
class SentimentResult:
    label: str  # "positive" | "negative" | "neutral"
    score: float  # -1 (very negative) to +1 (very positive)
    method: str  # "finbert" | "lexicon_fallback"


@lru_cache
def _load_finbert():
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(_FINBERT_MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(_FINBERT_MODEL_ID)
    model.eval()
    return tokenizer, model


def _score_with_finbert(texts: list[str]) -> list[SentimentResult]:
    import torch

    tokenizer, model = _load_finbert()
    # FinBERT's label order for ProsusAI/finbert is [positive, negative, neutral].
    labels = ["positive", "negative", "neutral"]

    inputs = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=128)
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=1).numpy()

    results = []
    for row in probs:
        best_idx = int(row.argmax())
        label = labels[best_idx]
        # Map to a signed -1..+1 score: positive prob minus negative prob.
        score = float(row[0] - row[1])
        results.append(SentimentResult(label=label, score=score, method="finbert"))
    return results


def _score_with_lexicon(texts: list[str]) -> list[SentimentResult]:
    results = []
    for text in texts:
        words = set(text.lower().split())
        pos_hits = len(words & _POSITIVE_WORDS)
        neg_hits = len(words & _NEGATIVE_WORDS)
        total = pos_hits + neg_hits

        if total == 0:
            results.append(SentimentResult(label="neutral", score=0.0, method="lexicon_fallback"))
            continue

        score = (pos_hits - neg_hits) / total
        label = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"
        results.append(SentimentResult(label=label, score=score, method="lexicon_fallback"))
    return results


def score_headlines(texts: list[str]) -> list[SentimentResult]:
    if not texts:
        return []
    try:
        return _score_with_finbert(texts)
    except Exception:
        # Model download/load failure (no network, no cached weights, OOM, etc.) —
        # fall back rather than hard-fail the whole sentiment feature.
        return _score_with_lexicon(texts)


def aggregate_sentiment(results: list[SentimentResult]) -> dict:
    if not results:
        return {"mean_score": 0.0, "n_headlines": 0, "method": "none"}

    mean_score = sum(r.score for r in results) / len(results)
    methods_used = {r.method for r in results}
    return {
        "mean_score": mean_score,
        "n_headlines": len(results),
        "n_positive": sum(1 for r in results if r.label == "positive"),
        "n_negative": sum(1 for r in results if r.label == "negative"),
        "n_neutral": sum(1 for r in results if r.label == "neutral"),
        "method": "finbert" if methods_used == {"finbert"} else "mixed" if len(methods_used) > 1 else "lexicon_fallback",
    }
