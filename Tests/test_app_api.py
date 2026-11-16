import pandas as pd

from app import app as application


def test_analyze_news_returns_class_probabilities_and_thresholded_labels(monkeypatch):
    labels = [
        "Acceso_a_servicios",
        "Empleo_y_economía",
        "Politica_migratoria",
        "Seguridad",
        "Transito_migratorio",
    ]
    checkpoint = {
        "sent_map": {"Negativo": 0, "Neutro": 1, "Positivo": 2},
        "label_cols": labels,
        "thresholds": {label: 0.4 for label in labels},
    }
    prediction = {
        "sentimiento": "Neutro",
        "p_Negativo": 0.1,
        "p_Neutro": 0.7,
        "p_Positivo": 0.2,
    }
    prediction.update({label: 0 for label in labels})
    prediction.update({f"p_{label}": 0.2 for label in labels})
    prediction[labels[0]] = 1
    prediction[f"p_{labels[0]}"] = 0.8

    monkeypatch.setattr(
        application,
        "_get_classifier",
        lambda: (object(), object(), checkpoint),
    )
    monkeypatch.setattr(
        application,
        "predict_texts",
        lambda *args, **kwargs: pd.DataFrame([prediction]),
    )

    rendered, result = application.analyze_news(
        "Esta noticia de prueba contiene suficientes palabras para analizar."
    )

    assert result["sentiment"] == "Neutro"
    assert result["sentiment_probabilities"]["Neutro"] == 0.7
    assert result["labels"][0]["name"] == labels[0]
    assert result["labels"][0]["detected"] is True
    assert "CLASE PREDICHA" in rendered


def test_scrape_limit_requires_integer_between_one_and_thirty():
    assert application._validate_scrape_limit(10) == 10
    for invalid in (0, 31, 1.5, "5", True):
        try:
            application._validate_scrape_limit(invalid)
        except ValueError:
            continue
        raise AssertionError(f"Se aceptó un límite inválido: {invalid}")
