"""Tests for Multilingual Evaluation, Event-Time Split Purity, and Abstention Metrics."""

from insightbot.modules.nlp.evaluation import (
    EventTimeSplitter,
    MultilingualEvaluator,
    compute_metrics,
    load_gold_corpus,
)


def test_gold_corpus_loading():
    """Verify gold corpus JSON contains samples across all three target languages."""
    samples = load_gold_corpus("data/eval/gold_corpus.json")
    assert len(samples) >= 20

    languages = set(s.language for s in samples)
    assert "ar" in languages
    assert "en" in languages
    assert "ru" in languages


def test_event_time_split_purity():
    """
    CRITICAL ACCEPTANCE GATE:
    Verify that coverage of the same event NEVER leaks across train, validation, and test splits.
    """
    samples = load_gold_corpus("data/eval/gold_corpus.json")
    split = EventTimeSplitter.split(samples, train_ratio=0.60, val_ratio=0.20)

    train_events = set(s.event_id for s in split.train)
    val_events = set(s.event_id for s in split.validation)
    test_events = set(s.event_id for s in split.test)

    # Event sets must be strictly mutually disjoint
    assert train_events.isdisjoint(val_events)
    assert train_events.isdisjoint(test_events)
    assert val_events.isdisjoint(test_events)

    # Verification: total samples preserved
    assert len(split.train) + len(split.validation) + len(split.test) == len(samples)


def test_abstention_penalties_in_metrics():
    """
    Verify that abstaining ('uncertain') counts as missed truth and lowers recall/F1.
    """
    y_true = ["politics", "politics", "business", "conflict"]

    # Case 1: 100% correct predictions
    y_pred_perfect = ["politics", "politics", "business", "conflict"]
    m_perfect = compute_metrics(y_true, y_pred_perfect, [10.0, 12.0, 11.0, 9.0])
    assert m_perfect.accuracy == 1.0
    assert m_perfect.macro_f1 == 1.0
    assert m_perfect.coverage_rate == 1.0
    assert m_perfect.passed_gate is True

    # Case 2: One sample abstains ('uncertain')
    y_pred_with_abstain = ["politics", "uncertain", "business", "conflict"]
    m_abstain = compute_metrics(y_true, y_pred_with_abstain, [10.0, 12.0, 11.0, 9.0])
    assert m_abstain.coverage_rate == 0.75  # 3 of 4 evaluated
    assert m_abstain.abstained_samples == 1
    # Macro-F1 should drop because abstained sample is penalized as FN
    assert m_abstain.macro_f1 < 1.0


def test_multilingual_evaluator_runner():
    """Test full evaluation pipeline on gold corpus."""
    samples = load_gold_corpus("data/eval/gold_corpus.json")
    evaluator = MultilingualEvaluator(confidence_threshold=0.65)

    # Simulated predictor with known ground truth
    def mock_predict(text: str, lang: str) -> tuple[str, float]:
        # Return exact category with high confidence for test simulation
        for s in samples:
            if s.title in text:
                return s.true_category, 0.90
        return "uncertain", 0.30

    report = evaluator.evaluate(samples, mock_predict)
    assert report.overall.total_samples == len(samples)
    assert report.overall.coverage_rate >= 0.80
    assert report.overall.macro_f1 >= 0.80
    assert report.overall.passed_gate is True
    assert "ar" in report.by_language
    assert "en" in report.by_language
    assert "ru" in report.by_language
