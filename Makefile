.PHONY: setup dev backend frontend test check sync clean-generated

setup:
	./scripts/setup_dev.sh

dev:
	@echo "Run in separate terminals: make backend | make frontend"

backend:
	./scripts/start_backend.sh

frontend:
	./scripts/start_frontend.sh

test:
	pytest backend/tests -q

check:
	python3 -m compileall -q backend
	cd frontend && ./node_modules/.bin/tsc --noEmit

sync:
	python3 scripts/sync_all_services.py

clean-generated:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	rm -rf frontend/dist
