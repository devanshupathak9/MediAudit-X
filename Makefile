# MediAudit-X
.PHONY: help up down reset data indices load smoke demo logs kibana

ES ?= http://localhost:9200

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-10s\033[0m %s\n",$$1,$$2}'

up:      ## start Elasticsearch and wait for green
	cd elasticsearch && docker compose up -d
	./elasticsearch/scripts/wait_for_es.sh

kibana:  ## start Kibana too (http://localhost:5601)
	cd elasticsearch && docker compose --profile ui up -d

down:    ## stop containers, keep data
	cd elasticsearch && docker compose down

reset:   ## stop containers and WIPE all indexed data
	cd elasticsearch && docker compose down -v

data:    ## regenerate demo patients, policy chunks and citation offsets
	python3 data/patients/build_demo_patients.py
	python3 data/policies/anchor_citations.py
	python3 data/policies/chunk_policy.py

indices: ## (re)create indices from mappings/
	./elasticsearch/scripts/create_indices.sh --force

load:    ## bulk-load the demo dataset
	./elasticsearch/scripts/load_data.sh

smoke:   ## run the nine proof queries
	./elasticsearch/scripts/smoke_test.sh

demo: up data indices load smoke  ## everything, from nothing, in one command
