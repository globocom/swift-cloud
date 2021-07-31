.PHONY: help clean setup pycodestyle tests docker-build docker-clean docker-stop docker run restart stop

PROJECT_NAME = swift-cloud
PROJECT_HOME := $(shell pwd)

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

clean: ## Project cleaning up for any extra files created during execution
	@echo "Cleaning up"
	@rm -rf build dist *.egg-info
	@find . \( -name '*.pyc' -o  -name '__pycache__' -o -name '**/*.pyc' -o -name '*~' \) -delete

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

docker-stop: ## Stop docker-compose created containers
	@docker-compose stop

docker: docker-build ## Build and start Docker containers
	@docker-compose up

docker-tests:
	@docker exec -it fake_swift sh -c "cd /home/swift_cloud && make tests"

run: ## Run docker-compose in background and attach to fake_swift container
	@docker-compose up -d
	@docker attach fake_swift

restart: ## Restart fake-swift from docker-compose
	@docker-compose restart fake_swift

stop: docker-stop ## Same as docker-stop
