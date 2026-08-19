.PHONY: install install-dev lint typecheck test test-cov run-bot run-worker \
        build up down restart logs logs-bot logs-worker ps status uninstall

COMPOSE = docker compose -p media-downloader

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

lint:
	ruff check .

fmt:
	ruff format .

typecheck:
	mypy .

test:
	RUN_EXTERNAL_TESTS=false pytest -q

test-cov:
	RUN_EXTERNAL_TESTS=false pytest -q --cov=. --cov-report=term-missing

run-bot:
	python -m bot.main

run-worker:
	python -m worker.main

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f --tail=200

logs-bot:
	$(COMPOSE) logs -f --tail=200 bot

logs-worker:
	$(COMPOSE) logs -f --tail=200 worker

ps:
	$(COMPOSE) ps

status:
	$(COMPOSE) ps
	@echo "---"
	$(COMPOSE) exec redis redis-cli ping || true

# Removes ONLY this project's containers/network/volumes. Never touches
# anything outside the `media-downloader` compose project (e.g. SadiPrime).
uninstall:
	$(COMPOSE) down -v
