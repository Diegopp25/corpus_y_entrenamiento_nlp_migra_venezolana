"""Pruebas del repositorio SQLite."""

from __future__ import annotations

from app.services.store import Store


def _payload(analysis_id: str = "analisis-1", sentiment: str = "Negativo") -> dict:
    return {
        "id": analysis_id,
        "dateAnalyzed": "2026-11-09T12:00:00+00:00",
        "text": "texto de la noticia",
        "title": "Titular",
        "mediaName": "El Tiempo",
        "country": "Colombia",
        "sentiment": {
            "prediction": sentiment,
            "confidence": 82.0,
            "scores": {"negativo": 82.0, "neutro": 12.0, "positivo": 6.0},
        },
        "tokensCount": 120,
        "readingTimeSeconds": 36,
        "sourceUrl": "https://eltiempo.com/x",
        "meta": {"truncated": False, "engine": "fake"},
    }


def _frames(active: str = "seguridad") -> list[dict]:
    return [
        {
            "id": "seguridad",
            "label": "Seguridad",
            "score": 91.0,
            "isActive": active == "seguridad",
        },
        {
            "id": "empleo_economia",
            "label": "Empleo y economía",
            "score": 30.0,
            "isActive": active == "empleo_economia",
        },
    ]


def test_save_and_get(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.init_schema()
    assert store.save_analysis(
        _payload(), _frames(), engine="fake", latency_ms=12.5
    )
    stored = store.get_analysis("analisis-1")
    assert stored["sentiment"]["prediction"] == "Negativo"
    assert store.count_analyses() == 1
    assert store.sentiment_counts()["Negativo"] == 1
    frames = store.frame_counts()
    assert frames[0]["frame"] == "Seguridad"
    assert frames[0]["percentage"] == 100.0
    assert store.latency_stats()["p50"] == 12.5


def test_list_filters(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.init_schema()
    store.save_analysis(_payload("a1", "Negativo"), _frames())
    store.save_analysis(_payload("a2", "Positivo"), _frames("empleo_economia"))
    assert len(store.list_analyses()) == 2
    assert [row["id"] for row in store.list_analyses(sentiment="Positivo")] == ["a2"]
    assert store.count_analyses(sentiment="Negativo") == 1


def test_jobs(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.init_schema()
    store.create_job("job-1", "https://eltiempo.com", "eltiempo.com", {"url": "x"})
    store.update_job(
        "job-1",
        status="completed",
        current_step=5,
        articles_found=3,
        articles_analyzed=3,
        summary_json={"siteName": "El Tiempo"},
        steps_json=[{"step": 1, "message": "ok"}],
    )
    job = store.get_job("job-1")
    assert job["status"] == "completed"
    assert job["summary"]["siteName"] == "El Tiempo"
    assert job["steps"][0]["message"] == "ok"
    assert store.job_stats()["completed"] == 1
    assert len(store.list_jobs()) == 1


def test_events(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.init_schema()
    store.record_event(
        request_id="r1",
        method="GET",
        path="/v1/health",
        status_code=200,
        latency_ms=3.2,
    )
    stats = store.event_stats()
    assert stats["total"] == 1
    assert stats["by_status"]["200"] == 1
