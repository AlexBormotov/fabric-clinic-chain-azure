# Every target runs inside the dev container, locally and in CI, so both make the same claim.
# Inside the container IN_DEV_CONTAINER is set and targets execute directly.
ifdef IN_DEV_CONTAINER
RUN :=
else
RUN := docker compose run --rm dev
endif

.PHONY: setup lint test test-slow test-stand synth sources bronze silver mpi mpi-eval secrets up down

setup:
	docker compose build dev
	$(RUN) uv sync --frozen

lint:
	$(RUN) sh -c 'uv sync --frozen --quiet \
		&& uv run ruff check . \
		&& uv run ruff format --check . \
		&& if [ -d sql ]; then uv run sqlfluff lint sql; fi \
		&& actionlint'

test:
	$(RUN) sh -c 'uv sync --frozen --quiet && uv run pytest'

test-slow:
	$(RUN) sh -c 'uv sync --frozen --quiet && uv run pytest -m slow'

# Needs `make up`: reads the stand back and compares it with data/sources/.
test-stand:
	$(RUN) sh -c 'uv sync --frozen --quiet && uv run pytest -m stand'

synth:
	$(RUN) sh -c 'uv sync --frozen --quiet && uv run python scripts/synth.py'

sources:
	$(RUN) sh -c 'uv sync --frozen --quiet && PYTHONPATH=src uv run python scripts/derive_sources.py'

# Needs `make up`: lands the stand into data/lh_bronze/ and runs the Bronze notebook on local Spark.
bronze:
	$(RUN) sh -c 'uv sync --frozen --quiet && PYTHONPATH=src uv run python scripts/bronze.py'

# Needs `make bronze`: builds data/lh_silver/ and prints the Bronze -> Silver reconciliation.
silver:
	$(RUN) sh -c 'uv sync --frozen --quiet && PYTHONPATH=src uv run python scripts/silver.py'

# Needs `make silver`: matches patient records into data/lh_silver/Tables/patient_xref.
mpi:
	$(RUN) sh -c 'uv sync --frozen --quiet && PYTHONPATH=src uv run python scripts/mpi.py'

# Needs `make mpi`: precision and recall against ground truth into docs/evidence/mpi.json.
mpi-eval:
	$(RUN) sh -c 'uv sync --frozen --quiet && PYTHONPATH=src uv run python scripts/mpi.py --eval'

secrets:
	$(RUN) gitleaks git --redact --verbose .

# The SA password is generated once into the git-ignored .env, which compose reads.
.env:
	printf 'MSSQL_SA_PASSWORD=Sa1-%s\n' "$$(head -c 18 /dev/urandom | base64 | tr -d '+/=')" > .env

up: .env
	docker compose up -d --wait sqlserver azurite
	$(RUN) sh -c 'uv sync --frozen --quiet && PYTHONPATH=src uv run python scripts/load_stand.py'

down:
	docker compose down
