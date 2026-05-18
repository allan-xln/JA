SHELL := /bin/bash

.PHONY: docker-up docker-up-d docker-down docker-logs docker-logs-api docker-logs-whatsapp docker-collector-run docker-shell-api docker-clean demo-up demo-status demo-check demo-collector demo-whatsapp-start demo-whatsapp-status demo-whatsapp-summary demo-logs

docker-up:
	docker compose up --build

docker-up-d:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-logs-api:
	docker compose logs -f api

docker-logs-whatsapp:
	docker compose logs -f whatsapp

docker-collector-run:
	docker compose exec api python -m api.collector

docker-shell-api:
	docker compose exec api bash

docker-clean:
	docker compose down -v

demo-up:
	docker compose up -d --build
	docker compose ps

demo-status:
	docker compose ps

demo-check:
	@echo "API / health"
	@curl -sS http://127.0.0.1:8000/api/eletrofrio/health; echo
	@echo "Overview operacional"
	@curl -sS http://127.0.0.1:8000/api/eletrofrio/overview | head -c 700; echo
	@echo "Collector"
	@curl -sS http://127.0.0.1:8000/api/collector/status | head -c 700; echo
	@echo "WhatsApp"
	@curl -sS http://127.0.0.1:8000/api/eletrofrio/whatsapp/status; echo
	@echo "Frontend: http://localhost:3000"

demo-collector:
	curl -X POST http://127.0.0.1:8000/api/collector/run-now

demo-whatsapp-start:
	curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/start

demo-whatsapp-status:
	curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/status

demo-whatsapp-summary:
	curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/send-operational-summary

demo-logs:
	docker compose logs -f api frontend whatsapp scheduler
