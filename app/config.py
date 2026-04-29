from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = Field(default="", description="OpenAI API key")
    chat_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-large"
    embedding_dim: int = 1024  # Matryoshka truncation; native is 3072

    # Pinecone
    pinecone_api_key: str = Field(default="", description="Pinecone API key")
    pinecone_index: str = "pdf-agent"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # Cohere (reranker; optional — if missing we skip rerank)
    cohere_api_key: str = Field(default="", description="Cohere API key")
    rerank_model: str = "rerank-v3.5"

    # Retrieval knobs
    fetch_top_k: int = 20  # initial dense fetch
    rerank_top_k: int = 5  # what we send to the LLM

    # Optional: LangSmith for observability
    langsmith_api_key: str = ""
    langsmith_project: str = "pdf-agent"

    # Paths
    data_dir: Path = PROJECT_ROOT / "data"

    # Runtime
    log_level: str = "INFO"
    env: str = "dev"


settings = Settings()
