from app.config import settings
from app.logging import configure_logging, get_logger


def test_settings_loads():
    assert settings.chat_model.startswith("gpt-")
    assert settings.embedding_model == "text-embedding-3-large"
    assert settings.embedding_dim == 1024


def test_logger_emits(capsys):
    configure_logging()
    log = get_logger("smoke")
    log.info("hello", layer="v1")
    captured = capsys.readouterr()
    assert "hello" in captured.out
