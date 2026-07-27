from tools.evaluate_llm_fms import Sample, best_threshold, confusion


def _sample(subject: str, value: float, truth: bool) -> Sample:
    return Sample(
        image=f"{subject}.jpg",
        action="m01",
        subject=subject,
        score=2,
        truth_depth_issue=truth,
        truth_torso_issue=False,
        hip_answer="Higher" if truth else "Lower",
        trunk_answer="Parallel",
        detected=True,
        knee_angle=value,
    )


def test_confusion_metrics() -> None:
    metrics = confusion(
        [True, True, False, False],
        [True, False, True, False],
    )
    assert metrics["tp"] == 1
    assert metrics["tn"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["balanced_accuracy"] == 0.5


def test_best_threshold_separates_values() -> None:
    rows = [
        _sample("1", 80.0, False),
        _sample("2", 90.0, False),
        _sample("3", 110.0, True),
        _sample("4", 120.0, True),
    ]
    threshold, metrics = best_threshold(
        rows,
        value=lambda row: row.knee_angle,
        truth=lambda row: row.truth_depth_issue,
        current=100.0,
    )
    assert threshold == 100.0
    assert metrics["balanced_accuracy"] == 1.0
