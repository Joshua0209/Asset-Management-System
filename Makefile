.PHONY: help obs-up obs-down obs-restart obs-logs obs-ps obs-pull obs-clean obs-test obs-alloy-fmt \
        load-smoke load-steady load-spike load-load load-stress load-consistent \
        traffic-start traffic-stop traffic-status traffic-logs

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
	python3 scripts/test_obs_k6.py

obs-alloy-fmt: ## Validate config/alloy/config.alloy with `alloy fmt` (pulls v1.5.1)
	docker run --rm \
	  -v $(PWD)/config/alloy/config.alloy:/etc/alloy/config.alloy:ro \
	  grafana/alloy:v1.5.1 fmt /etc/alloy/config.alloy > /dev/null
	@echo "OK: config/alloy/config.alloy parses cleanly under grafana/alloy:v1.5.1"

# ── Phase 7 — k6 load / stress runners ───────────────────────────────────────
# All `load-*` targets are one-shot: they invoke `docker compose run --rm` so
# the k6 container exits when the run ends. Pass extra args via K6_ARGS=...
# (e.g. K6_ARGS="--out experimental-prometheus-rw -e K6_PROMETHEUS_RW_SERVER_URL=
# http://prometheus:9090/api/v1/write"). The k6 service from the overlay sits
# under the `tools` profile so it doesn't start with `make obs-up`.
K6_RUN := $(COMPOSE_OBS) --profile tools run --rm k6 run
K6_ARGS ?=

load-smoke: ## k6 smoke (1m, ~3 VUs) — quick "is it green" check
	$(K6_RUN) $(K6_ARGS) /scripts/k6-smoke.js

load-steady: ## k6 steady-state mix (5m at ~10 VUs)
	$(K6_RUN) $(K6_ARGS) /scripts/k6-steady.js

load-spike: ## k6 spike (ramp 5→50 VUs over ~100s)
	$(K6_RUN) $(K6_ARGS) /scripts/k6-spike.js

load-load: ## k6 main load test — constant-arrival-rate across 6 AMS flows (~10m)
	$(K6_RUN) $(K6_ARGS) /scripts/k6-load.js

# Stress measures the app, not slowapi. RATE_LIMIT_ENABLED=false is set on the
# k6-side of the env so it propagates only into the k6 container; the backend
# still needs to be restarted with the env var for the limiter to no-op (the
# warning printed by setup() in k6-stress.js reminds the operator).
load-stress: ## k6 ramp-VUs stress test — find the breakpoint (~7m)
	$(K6_RUN) $(K6_ARGS) /scripts/k6-stress.js

# load-consistent runs the same script the traffic-generator profile uses,
# but as a one-shot so the run terminates with TRAFFIC_DURATION. Useful for
# CI scenarios that want a fixed-window load before snapshotting dashboards.
load-consistent: ## k6 long-running per-flow constant-arrival-rate (TRAFFIC_DURATION env)
	$(K6_RUN) $(K6_ARGS) /scripts/k6-consistent.js

traffic-start: ## Start the long-running traffic-generator (k6-consistent.js)
	$(COMPOSE_OBS) --profile traffic up -d traffic-generator

traffic-stop: ## Stop and remove the traffic-generator
	-$(COMPOSE_OBS) --profile traffic stop traffic-generator
	-$(COMPOSE_OBS) --profile traffic rm -f traffic-generator

traffic-status: ## Show the traffic-generator container status
	$(COMPOSE_OBS) --profile traffic ps traffic-generator

traffic-logs: ## Tail the traffic-generator logs
	$(COMPOSE_OBS) --profile traffic logs -f --tail=100 traffic-generator
