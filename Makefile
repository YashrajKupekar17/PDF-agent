.PHONY: test ingest api ui eval

test:
	uv run pytest -v

ingest:
	uv run python -m app.pipeline data/sample.pdf

api:
	uv run uvicorn app.api:app --reload --port 8000

ui:
	cd ui && npm run dev

eval:
	uv run python -m evals.run_eval
