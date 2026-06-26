from pathlib import Path

from codex_observe.parser import CodexIngestor


def test_ingestor_constructs(tmp_path: Path):
    db = tmp_path / "test.sqlite"
    ing = CodexIngestor(db)
    ing.close()
    assert db.exists()
