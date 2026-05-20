SHELL := /bin/bash

# Override these as needed:
#   make build DOCKER_USER=myuser TAG=v1.0.0
DOCKER_USER ?= operry
IMAGE_NAME  ?= atlantis-teams-relay
TAG         ?= latest
IMAGE       := $(DOCKER_USER)/$(IMAGE_NAME):$(TAG)
PLATFORMS   ?= linux/amd64,linux/arm64
PORT        ?= 5025

PYTHON  ?= python3
VENV    ?= .venv
PIP     := $(VENV)/bin/pip
PY      := $(VENV)/bin/python

.PHONY: help venv install run dev clean \
        build push buildx-setup buildx-push \
        docker-run docker-stop tag login

help:
	@echo "Targets:"
	@echo "  venv           Create a Python virtualenv in $(VENV)"
	@echo "  install        Install Python dependencies into the venv"
	@echo "  run            Run relay.py locally (uses TEAMS_WEBHOOK_URL env var)"
	@echo "  dev            Run with Flask in debug mode"
	@echo "  clean          Remove venv and Python caches"
	@echo ""
	@echo "  login          docker login (uses DOCKER_USER)"
	@echo "  build          Build local Docker image: $(IMAGE)"
	@echo "  tag            Also tag image as :latest"
	@echo "  push           Push $(IMAGE) (and :latest if tagged) to Docker Hub"
	@echo "  buildx-setup   Create/use a buildx builder for multi-arch"
	@echo "  buildx-push    Build & push multi-arch ($(PLATFORMS)) image"
	@echo "  docker-run     Run the image locally on port $(PORT)"
	@echo "  docker-stop    Stop the locally running container"
	@echo ""
	@echo "Vars: DOCKER_USER=$(DOCKER_USER) IMAGE_NAME=$(IMAGE_NAME) TAG=$(TAG)"

# ---------- Python (local dev) ----------

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

run:
	$(PY) relay.py

dev:
	FLASK_APP=relay.py FLASK_DEBUG=1 $(VENV)/bin/flask run --host 0.0.0.0 --port $(PORT)

clean:
	rm -rf $(VENV) __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

# ---------- Docker ----------

login:
	docker login -u $(DOCKER_USER)

build:
	docker build -t $(IMAGE) .

tag: build
	docker tag $(IMAGE) $(DOCKER_USER)/$(IMAGE_NAME):latest

push: build
	docker push $(IMAGE)
ifneq ($(TAG),latest)
	docker tag $(IMAGE) $(DOCKER_USER)/$(IMAGE_NAME):latest
	docker push $(DOCKER_USER)/$(IMAGE_NAME):latest
endif

buildx-setup:
	docker buildx inspect relay-builder >/dev/null 2>&1 || \
		docker buildx create --name relay-builder --use
	docker buildx inspect --bootstrap

buildx-push: buildx-setup
	docker buildx build \
		--platform $(PLATFORMS) \
		-t $(IMAGE) \
		$(if $(filter-out latest,$(TAG)),-t $(DOCKER_USER)/$(IMAGE_NAME):latest,) \
		--push .

docker-run:
	@if [ -z "$$TEAMS_WEBHOOK_URL" ]; then echo "TEAMS_WEBHOOK_URL is not set"; exit 1; fi
	docker run --rm -d --name $(IMAGE_NAME) \
		-p $(PORT):$(PORT) \
		-e TEAMS_WEBHOOK_URL="$$TEAMS_WEBHOOK_URL" \
		-e PORT=$(PORT) \
		$(IMAGE)

docker-stop:
	-docker stop $(IMAGE_NAME)
