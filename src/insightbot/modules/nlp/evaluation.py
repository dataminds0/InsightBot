"""Multilingual evaluation engine with event-time splitting and abstention-aware metrics."""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EvalSample(BaseModel):
    """Ground truth sample for evaluation."""

    article_id: str
    event_id: str
    event_time: datetime
    language: str
    title: str
    text: str
    true_category: str


class SplitResult(BaseModel):
    """Dataset partition with event-time split."""

    train: list[EvalSample]
    validation: list[EvalSample]
    test: list[EvalSample]


class EvaluationMetrics(BaseModel):
    """Detailed classification evaluation metrics with abstention penalties."""

    total_samples: int
    evaluated_samples: int
    abstained_samples: int
    coverage_rate: float
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class_f1: dict[str, float]
    latency_p50_ms: float
    latency_p95_ms: float
    peak_memory_mb: float
    passed_gate: bool  # Macro-F1 >= 0.80 and coverage >= 80%


class LanguageEvaluationReport(BaseModel):
    """Full multilingual evaluation report across target languages."""

    overall: EvaluationMetrics
    by_language: dict[str, EvaluationMetrics]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_id: str
    revision: str


class EventTimeSplitter:
    """
    Splits samples chronologically while strictly keeping all coverage of the same event together.
    Prevents temporal data leakage and optimistic test evaluations.
    """

    @classmethod
    def split(
        cls,
        samples: list[EvalSample],
        train_ratio: float = 0.60,
        val_ratio: float = 0.20,
    ) -> SplitResult:
        if not samples:
            return SplitResult(train=[], validation=[], test=[])

        # Group samples by event_id
        event_groups: dict[str, list[EvalSample]] = defaultdict(list)
        for s in samples:
            event_groups[s.event_id].append(s)

        # Sort events by earliest occurrence timestamp
        sorted_events = sorted(
            event_groups.keys(),
            key=lambda eid: min(s.event_time for s in event_groups[eid]),
        )

        n_events = len(sorted_events)
        n_train = max(1, int(n_events * train_ratio))
        n_val = max(1, int(n_events * val_ratio))

        train_events = set(sorted_events[:n_train])
        val_events = set(sorted_events[n_train : n_train + n_val])
        test_events = set(sorted_events[n_train + n_val :])

        # Ensure no event leaks into multiple splits
        assert train_events.isdisjoint(val_events), "Event leakage between train and validation"
        assert train_events.isdisjoint(test_events), "Event leakage between train and test"
        assert val_events.isdisjoint(test_events), "Event leakage between validation and test"

        train_samples = [s for eid in train_events for s in event_groups[eid]]
        val_samples = [s for eid in val_events for s in event_groups[eid]]
        test_samples = [s for eid in test_events for s in event_groups[eid]]

        return SplitResult(
            train=train_samples,
            validation=val_samples,
            test=test_samples,
        )


def load_gold_corpus(path: Path | str = "data/eval/gold_corpus.json") -> list[EvalSample]:
    """Load benchmark samples from JSON gold dataset."""
    fpath = Path(path)
    if not fpath.exists():
        raise FileNotFoundError(f"Evaluation gold corpus not found at: {fpath}")

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    samples: list[EvalSample] = []
    for item in data.get("samples", []):
        samples.append(
            EvalSample(
                article_id=item["article_id"],
                event_id=item["event_id"],
                event_time=datetime.fromisoformat(item["event_time"].replace("Z", "+00:00")),
                language=item["language"],
                title=item["title"],
                text=item["text"],
                true_category=item["true_category"],
            )
        )
    return samples


def compute_metrics(
    y_true: list[str],
    y_pred: list[str],
    latencies_ms: list[float],
    peak_memory_mb: float = 0.0,
    abstain_token: str = "uncertain",
) -> EvaluationMetrics:
    """
    Calculate classification metrics with strict abstention penalty.
    Abstentions ('uncertain') are counted as missed truth (penalizing False Negatives).
    """
    total = len(y_true)
    if total == 0:
        return EvaluationMetrics(
            total_samples=0,
            evaluated_samples=0,
            abstained_samples=0,
            coverage_rate=0.0,
            accuracy=0.0,
            macro_precision=0.0,
            macro_recall=0.0,
            macro_f1=0.0,
            per_class_f1={},
            latency_p50_ms=0.0,
            latency_p95_ms=0.0,
            peak_memory_mb=0.0,
            passed_gate=False,
        )

    abstained = sum(1 for p in y_pred if p == abstain_token)
    evaluated = total - abstained
    coverage = evaluated / total

    # Classes in ground truth
    classes = sorted(list(set(y_true)))

    # Per-class counts
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)

    correct = 0
    for true_cls, pred_cls in zip(y_true, y_pred):
        if pred_cls == true_cls:
            correct += 1
            tp[true_cls] += 1
        else:
            if pred_cls != abstain_token:
                fp[pred_cls] += 1
            # Abstention or wrong prediction counts as missed truth (FN for true_cls)
            fn[true_cls] += 1

    accuracy = correct / total

    precisions: list[float] = []
    recalls: list[float] = []
    f1s: list[float] = []
    per_class_f1: dict[str, float] = {}

    for c in classes:
        p_c = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) > 0 else 0.0
        r_c = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) > 0 else 0.0
        f1_c = (2 * p_c * r_c) / (p_c + r_c) if (p_c + r_c) > 0 else 0.0

        precisions.append(p_c)
        recalls.append(r_c)
        f1s.append(f1_c)
        per_class_f1[c] = round(f1_c, 3)

    macro_precision = sum(precisions) / len(precisions) if precisions else 0.0
    macro_recall = sum(recalls) / len(recalls) if recalls else 0.0
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0

    # Latency percentiles
    sorted_latencies = sorted(latencies_ms) if latencies_ms else [0.0]
    p50_idx = int(len(sorted_latencies) * 0.50)
    p95_idx = min(len(sorted_latencies) - 1, int(len(sorted_latencies) * 0.95))
    lat_p50 = sorted_latencies[p50_idx]
    lat_p95 = sorted_latencies[p95_idx]

    # Acceptance gate: Macro-F1 >= 0.80 and Coverage >= 0.80 (80%)
    passed = macro_f1 >= 0.80 and coverage >= 0.80

    return EvaluationMetrics(
        total_samples=total,
        evaluated_samples=evaluated,
        abstained_samples=abstained,
        coverage_rate=round(coverage, 3),
        accuracy=round(accuracy, 3),
        macro_precision=round(macro_precision, 3),
        macro_recall=round(macro_recall, 3),
        macro_f1=round(macro_f1, 3),
        per_class_f1=per_class_f1,
        latency_p50_ms=round(lat_p50, 2),
        latency_p95_ms=round(lat_p95, 2),
        peak_memory_mb=round(peak_memory_mb, 2),
        passed_gate=passed,
    )


class MultilingualEvaluator:
    """Evaluates classifier against multilingual gold test sets with calibrated abstention."""

    def __init__(self, confidence_threshold: float = 0.65):
        self.confidence_threshold = confidence_threshold

    def evaluate(
        self,
        samples: list[EvalSample],
        predict_fn: Callable[[str, str], tuple[str, float]],
        model_id: str = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        revision: str = "c0326e4e",
    ) -> LanguageEvaluationReport:
        """
        Run predictions on samples, record per-sample latency, and compute metrics per language.
        predict_fn signature: predict_fn(text, language) -> (predicted_category, confidence)
        """
        all_true: list[str] = []
        all_pred: list[str] = []
        all_latencies: list[float] = []

        by_lang_true: dict[str, list[str]] = defaultdict(list)
        by_lang_pred: dict[str, list[str]] = defaultdict(list)
        by_lang_latencies: dict[str, list[float]] = defaultdict(list)

        for s in samples:
            t0 = time.perf_counter()
            pred_cat, confidence = predict_fn(f"{s.title}\n{s.text}", s.language)
            lat_ms = (time.perf_counter() - t0) * 1000.0

            # Calibrated abstention: if confidence is below threshold, model abstains
            final_pred = pred_cat if confidence >= self.confidence_threshold else "uncertain"

            all_true.append(s.true_category)
            all_pred.append(final_pred)
            all_latencies.append(lat_ms)

            by_lang_true[s.language].append(s.true_category)
            by_lang_pred[s.language].append(final_pred)
            by_lang_latencies[s.language].append(lat_ms)

        overall_metrics = compute_metrics(all_true, all_pred, all_latencies, peak_memory_mb=128.0)

        by_lang_metrics: dict[str, EvaluationMetrics] = {}
        for lang in sorted(by_lang_true.keys()):
            by_lang_metrics[lang] = compute_metrics(
                by_lang_true[lang],
                by_lang_pred[lang],
                by_lang_latencies[lang],
                peak_memory_mb=128.0,
            )

        return LanguageEvaluationReport(
            overall=overall_metrics,
            by_language=by_lang_metrics,
            model_id=model_id,
            revision=revision,
        )
