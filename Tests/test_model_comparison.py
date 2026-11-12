import pytest

from modelling.compare_models import build_comparison


def _result(model, seed=44):
    return {
        "model_label": model,
        "model_name": model,
        "data_path": "dataset.csv",
        "seed": seed,
        "n_folds": 5,
        "max_len": 512,
        "cv_seconds": 10.0,
        "metrics": [
            {"task": "sent", "average": "macro", "f1": 0.6},
            {"task": "sent", "average": "micro", "f1": 0.7},
            {"task": "label", "average": "macro", "f1": 0.5},
            {"task": "label", "average": "micro", "f1": 0.8},
        ],
    }


def test_build_comparison_orders_by_topics_macro_f1():
    weaker = _result("BETO")
    stronger = _result("RoBERTa")
    stronger["metrics"][2]["f1"] = 0.75

    comparison = build_comparison([("BETO", weaker), ("RoBERTa", stronger)])

    assert comparison["modelo"].tolist() == ["RoBERTa", "BETO"]
    assert comparison.iloc[0]["topics_macro_f1"] == 0.75


def test_build_comparison_rejects_different_validation_setup():
    with pytest.raises(ValueError, match="seed no coincide"):
        build_comparison(
            [("BETO", _result("BETO")), ("RoBERTa", _result("RoBERTa", seed=17))]
        )
