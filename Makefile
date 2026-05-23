.PHONY: help obs-up obs-down obs-restart obs-logs obs-ps obs-pull obs-clean obs-test obs-alloy-fmt

# DOCKER_ROOT_DIR precedence (compose substitutes ${DOCKER_ROOT_DIR:-...} from
# this value when make invokes compose):
#   1. shell-exported value     (export DOCKER_ROOT_DIR=...)
#   2. command-line override    (make obs-up DOCKER_ROOT_DIR=...)
#   3. value in .env            (read here since make does not auto-source it)
#   4. `docker info` autodetect (rootless Docker, Lima, Colima, ...)
#   5. /var/lib/docker fallback (Docker Desktop / rootful Linux default)
ifeq ($(origin DOCKER_ROOT_DIR), undefined)
  ifneq (,$(wildcard .env))
DOCKER_ROOT_DIR := $(shell sed -n 's/^[[:space:]]*DOCKER_ROOT_DIR=//p' .env | tail -n1)
  endif
endif
ifeq ($(DOCKER_ROOT_DIR),)
DOCKER_ROOT_DIR := $(shell docker info --format '{{.DockerRootDir}}' 2>/dev/null)
endif
ifeq ($(DOCKER_ROOT_DIR),)
DOCKER_ROOT_DIR := /var/lib/docker
endif
export DOCKER_ROOT_DIR

COMPOSE_OBS := docker compose -f docker-compose.yml -f docker-compose.observability.yml

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

obs-up: ## Bring up the dev stack + observability overlay (Grafana on :3000)
	$(COMPOSE_OBS) up -d

obs-down: ## Stop the overlayed stack (data volumes preserved)
	$(COMPOSE_OBS) down

obs-restart: ## Restart the overlayed stack
	$(COMPOSE_OBS) down && $(COMPOSE_OBS) up -d

obs-ps: ## Show overlayed stack container status
	$(COMPOSE_OBS) ps

obs-logs: ## Tail logs (override service via SERVICE=, default alloy)
	$(COMPOSE_OBS) logs -f $${SERVICE:-alloy}

obs-pull: ## Pre-pull all overlay images (run before live demos)
	$(COMPOSE_OBS) pull

obs-clean: ## Stop overlayed stack AND wipe its data volumes
	$(COMPOSE_OBS) down -v --remove-orphans

obs-test: ## Parse-time regression test for the overlay (offline, no images)
	./scripts/test_obs_compose.sh
	python3 scripts/test_obs_dashboards.py

obs-alloy-fmt: ## Validate config/alloy/config.alloy with `alloy fmt` (pulls v1.5.1)
	docker run --rm \
	  -v $(PWD)/config/alloy/config.alloy:/etc/alloy/config.alloy:ro \
	  grafana/alloy:v1.5.1 fmt /etc/alloy/config.alloy > /dev/null
	@echo "OK: config/alloy/config.alloy parses cleanly under grafana/alloy:v1.5.1"
