from pathlib import Path

from app.eval import dataset, metrics, runner

FIXTURE = Path(__file__).parents[1] / "fixtures" / "questions_demo.jsonl"


def test_runner_end_to_end_on_stub(tmp_path):
    qs = dataset.load(FIXTURE)
    run_id, m = runner.run(qs, tmp_path)
    assert m.questions == 2
    assert m.path_hit_rate == 1.0
    assert m.answer_accuracy == 1.0
    assert m.citation_coverage == 1.0
    assert (tmp_path / run_id / "records.jsonl").exists()


def test_freeze_check_rejects_modified_file():
    import pytest

    with pytest.raises(ValueError):
        dataset.load(FIXTURE, expected_sha256="0" * 64)


def test_metrics_na_when_no_claims():
    assert metrics.compute([]).citation_coverage is None
