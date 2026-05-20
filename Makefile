.PHONY: help obs-up obs-down obs-restart obs-logs obs-ps obs-pull obs-clean obs-test

# Auto-detect Docker daemon root so Alloy + cAdvisor bind mounts resolve on
# rootless Docker / Lima / Colima. Falls back to the Docker Desktop default.
DOCKER_ROOT_DIR ?= $(shell docker info --format '{{.DockerRootDir}}' 2>/dev/null)
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
