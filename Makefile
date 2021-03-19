.PHONY: help clean setup pycodestyle tests docker-build docker-clean docker run restart

PROJECT_NAME = swift-gcp
PROJECT_HOME := $(shell pwd)

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

clean: ## Project cleaning up for any extra files created during execution
	@echo "Cleaning up"
	@find . -name "*.pyc" -delete
	@find . -name "*.~" -delete

setup: dependencies ## Install project dependencies and some git hooks
	@pip install -r requirements_test.txt

pycodestyle: ## Check source-code for pycodestyle compliance
	@echo "Checking source-code pycodestyle compliance"
	@-pycodestyle $(PROJECT_HOME) --ignore=E501,E126,E127,E128,W605

tests: clean pycodestyle ## Run tests (with coverage)
	@echo "Running all tests with coverage"
	@py.test --cov-config .coveragerc --cov $(PROJECT_HOME) --cov-report term-missing

docker-build: ## Build Docker containers
	@docker-compose build

docker-clean: ## Remove any container, network, volume and image created by docker
	@docker-compose down -v --rmi all --remove-orphans

docker: docker-build ## Build and start Docker containers
	@docker-compose up -d
	@docker attach fake_swift

run: docker ## Same as "docker"

restart: ## Restart fake-swift from docker-compose
	@docker-compose restart fake_swift
