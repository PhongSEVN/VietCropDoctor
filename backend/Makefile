#  VietCropDoctor — Development Makefile
#
#  Usage:
#    make up             Start full dev stack (ordered, waits for health)
#    make down           Stop all containers
#    make logs           Follow logs from all containers
#    make restart-vision Restart vision-ai only
#    make restart-rag    Restart rag-engine only
#    make kafka-ui       Open Kafka UI in browser
#    make ingest         Trigger knowledge-base ingestion via RAG API
#    make train          Run model training via mlops container
#    make mlflow-ui      Open MLflow UI in browser
#    make airflow-ui     Open Airflow UI in browser
#    make trigger-retrain Manually trigger retrain_classifier DAG
#    make trigger-ingest  Manually trigger ingest_knowledge_base DAG
#    make dvc-pull       Pull dataset from DVC remote
#    make dvc-push       Push dataset to DVC remote
#    make dataset-prepare Preprocess raw images into splits
#    make dataset-stats  Show class distribution statistics
#    make k8s-apply-dev  Apply Kustomize dev overlay
#    make k8s-apply-prod Apply Kustomize prod overlay
#    make helm-install   Install/upgrade via Helm (prod values)
#    make k8s-status     Show pod status in vietcropdoctor namespace
#    make k8s-logs       Tail vision-ai logs in k8s
#    make ci-local       Run GitHub Actions locally via nektos/act
#    make tag-release    Tag and push a release (make tag-release VERSION=1.2.0)
#    make help           Show this help

COMPOSE        := docker compose
RAG_URL        := http://localhost:8002
VISION_URL     := http://localhost:8001
GATEWAY_URL    := http://localhost:8000

# Detect OS for 'open' command
UNAME := $(shell uname -s 2>/dev/null || echo Windows)
ifeq ($(UNAME), Darwin)
  OPEN := open
else ifeq ($(UNAME), Linux)
  OPEN := xdg-open
else
  OPEN := start
endif

.PHONY: up down restart status build logs health pull-model clean \
        restart-vision restart-rag restart-gateway \
        kafka-ui ingest reindex \
        train mlflow-ui \
        prometheus-ui grafana-ui \
        airflow-ui trigger-retrain trigger-ingest \
        dvc-pull dvc-push dataset-prepare dataset-stats \
        k8s-apply-dev k8s-apply-prod helm-install k8s-status k8s-logs \
        ci-local tag-release \
        tf-init tf-plan tf-apply tf-destroy \
        ps shell-vision shell-rag shell-kafka \
        up-fast down-v init-topics \
        help

# Lifecycle

up: ## Start all services locally (smart ordered startup with health checks)
	@bash scripts/local-start.sh

up-fast: ## Start everything at once without waiting (faster, may fail on first run)
	$(COMPOSE) up -d

down: ## Stop all services (keeps volumes)
	@bash scripts/local-stop.sh

restart: ## Restart all services (stop then start)
	@bash scripts/local-stop.sh
	@bash scripts/local-start.sh

status: ## Show service status, ports, resource usage, and health checks
	@bash scripts/local-status.sh

down-v: ## Stop all containers AND delete all volumes (clean slate)
	$(COMPOSE) down -v

build: ## Build all Docker images (no cache)
	$(COMPOSE) build --no-cache vision-ai rag-engine analytics auth orchestrator gateway

# Logs

## Usage: make logs          → all app services
##        make logs s=vision-ai → single service
logs: ## Show logs (all app services by default; make logs s=<service> for one)
	@bash scripts/local-logs.sh $(if $(s),$(s),)

logs-vision: ## Follow vision-ai logs
	$(COMPOSE) logs -f vision-ai

logs-rag: ## Follow rag-engine logs
	$(COMPOSE) logs -f rag-engine

logs-kafka: ## Follow kafka logs
	$(COMPOSE) logs -f kafka

# Restart individual services

restart-vision: ## Restart vision-ai service
	$(COMPOSE) restart vision-ai
	@echo "vision-ai restarting… check: $(VISION_URL)/health"

restart-rag: ## Restart rag-engine service
	$(COMPOSE) restart rag-engine
	@echo "rag-engine restarting… check: $(RAG_URL)/health"

restart-gateway: ## Restart gateway (reload nginx config)
	$(COMPOSE) restart gateway

# Dev tools

kafka-ui: ## Open Kafka UI in browser (http://localhost:8080)
	@echo "Opening Kafka UI → http://localhost:8080"
	@$(OPEN) http://localhost:8080 2>/dev/null || true

ingest: ## Trigger RAG knowledge-base ingestion (POST /ingest)
	@echo "Triggering ingestion at $(RAG_URL)/ingest …"
	@curl -sS -X POST "$(RAG_URL)/ingest" \
	     -H "Content-Type: application/json" \
	     -d '{"recreate_collection": false}' \
	  | python3 -m json.tool 2>/dev/null || \
	  curl -sS -X POST "$(RAG_URL)/ingest" \
	       -H "Content-Type: application/json" \
	       -d '{"recreate_collection": false}'

reindex: ## Drop collection and re-ingest all knowledge docs (POST /reindex)
	@echo "Re-indexing at $(RAG_URL)/reindex …"
	@curl -sS -X POST "$(RAG_URL)/reindex" \
	  | python3 -m json.tool 2>/dev/null || \
	  curl -sS -X POST "$(RAG_URL)/reindex"

dvc-pull: ## Pull dataset and model artifacts from DVC remote
	dvc pull

dvc-push: ## Push dataset and model artifacts to DVC remote
	dvc push

dataset-prepare: ## Preprocess raw images into 80/10/10 train/val/test splits
	python services/mlops/data/preprocess.py

dataset-stats: ## Print class distribution and warn on under-represented classes
	python services/mlops/data/stats.py

train: ## Run classifier training (docker compose run --rm mlops)
	$(COMPOSE) --profile training run --rm mlops \
	  python training/train_classifier.py \
	  --config training/configs/mobilenetv3_baseline.yaml

mlflow-ui: ## Open MLflow UI in browser (http://localhost:5000)
	@echo "Opening MLflow UI → http://localhost:5000"
	@$(OPEN) http://localhost:5000 2>/dev/null || true

prometheus-ui: ## Open Prometheus UI in browser (http://localhost:9090)
	@echo "Opening Prometheus UI → http://localhost:9090"
	@$(OPEN) http://localhost:9090 2>/dev/null || true

grafana-ui: ## Open Grafana UI in browser (http://localhost:3001, admin/admin)
	@echo "Opening Grafana UI → http://localhost:3001"
	@$(OPEN) http://localhost:3001 2>/dev/null || true

airflow-ui: ## Open Airflow UI in browser (http://localhost:8090)
	@echo "Opening Airflow UI → http://localhost:8090"
	@$(OPEN) http://localhost:8090 2>/dev/null || true

trigger-retrain: ## Manually trigger the retrain_classifier DAG in Airflow
	@echo "Triggering retrain_classifier DAG…"
	@$(COMPOSE) exec airflow airflow dags trigger retrain_classifier

trigger-ingest: ## Manually trigger the ingest_knowledge_base DAG in Airflow
	@echo "Triggering ingest_knowledge_base DAG…"
	@$(COMPOSE) exec airflow airflow dags trigger ingest_knowledge_base

# Kubernetes / Helm

k8s-apply-dev: ## Apply Kustomize dev overlay (kubectl apply -k infra/k8s/overlays/dev)
	kubectl apply -k infra/k8s/overlays/dev

k8s-apply-prod: ## Apply Kustomize prod overlay (kubectl apply -k infra/k8s/overlays/prod)
	kubectl apply -k infra/k8s/overlays/prod

helm-install: ## Install/upgrade via Helm using prod values
	helm upgrade --install vietcropdoctor infra/k8s/helm/vietcropdoctor \
	  -f infra/k8s/helm/vietcropdoctor/values-prod.yaml \
	  --namespace vietcropdoctor \
	  --create-namespace

k8s-status: ## Show pod status in the vietcropdoctor namespace
	kubectl get pods -n vietcropdoctor

k8s-logs: ## Tail vision-ai logs in Kubernetes
	kubectl logs -f -l app=vision-ai -n vietcropdoctor

# Terraform

tf-init: ## Initialise Terraform (run once after bootstrap)
	cd infra/terraform && terraform init

tf-plan: ## Preview infrastructure changes (prod vars)
	cd infra/terraform && terraform plan -var-file=environments/prod/terraform.tfvars

tf-apply: ## Apply infrastructure changes (prod vars)
	cd infra/terraform && terraform apply -var-file=environments/prod/terraform.tfvars

tf-destroy: ## Destroy all infrastructure (asks for confirmation)
	@echo "WARNING: This will destroy ALL infrastructure. Type 'yes' to confirm."
	@read -r CONFIRM && [ "$$CONFIRM" = "yes" ] || (echo "Aborted." && exit 1)
	cd infra/terraform && terraform destroy -var-file=environments/prod/terraform.tfvars

# CI / Release

ci-local: ## Run CI workflow locally via nektos/act (requires: brew install act)
	act push --platform ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest

tag-release: ## Create and push a git release tag (usage: make tag-release VERSION=1.2.0)
	@test -n "$(VERSION)" || (echo "Usage: make tag-release VERSION=x.y.z" && exit 1)
	git tag -a v$(VERSION) -m "Release v$(VERSION)"
	git push --tags
	@echo "Released: v$(VERSION)"

init-topics: ## (Re-)create Kafka topics
	@bash scripts/init-kafka-topics.sh

ps: ## Show status of all containers
	$(COMPOSE) ps

# Shell access

shell-vision: ## Open a shell in the vision-ai container
	$(COMPOSE) exec vision-ai /bin/bash

shell-rag: ## Open a shell in the rag-engine container
	$(COMPOSE) exec rag-engine /bin/bash

shell-kafka: ## Open a shell in the kafka container
	$(COMPOSE) exec kafka /bin/bash

# Health checks

health: ## Run health checks on all service endpoints
	@bash -c 'cd .. && bash vietcropdoctor-infra/scripts/health-check.sh 2>/dev/null || bash scripts/local-status.sh --short'

pull-model: ## Pull the default Ollama LLM model (qwen2.5:7b)
	@echo "Pulling Ollama model qwen2.5:7b…"
	docker exec vcd-ollama ollama pull qwen2.5:7b

# Cleanup

clean: ## Stop + remove volumes + prune dangling images
	@bash scripts/local-stop.sh --clean

# Help

help: ## Show this help message
	@echo ""
	@echo "  VietCropDoctor — Development Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""

.DEFAULT_GOAL := help
