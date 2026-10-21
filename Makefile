# Every target runs inside the dev container, locally and in CI, so both make the same claim.
# Inside the container IN_DEV_CONTAINER is set and targets execute directly.
ifdef IN_DEV_CONTAINER
RUN :=
else
RUN := docker compose run --rm dev
endif

.PHONY: setup lint test secrets up down

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

secrets:
	$(RUN) gitleaks git --redact --verbose .

up:
	docker compose up -d

down:
	docker compose down
