# Shortcuts. `make setup` = type one word instead of five commands.
PY = .venv/bin/python

up:        # start Elasticsearch in Docker
	cd elasticsearch && docker compose up -d

down:      # stop Elasticsearch (data is kept)
	cd elasticsearch && docker compose down

install:   # create the Python environment
	python3 -m venv .venv && $(PY) -m pip install -q -r elasticsearch/requirements.txt

setup:     # create indexes, load patients, index policies with vectors
	cd elasticsearch && ../$(PY) create_indices.py && ../$(PY) index_data.py && ../$(PY) index_policies.py

search:    # example: make search Q="patient weight too high"
	cd elasticsearch && ../$(PY) search_policies.py "$(Q)" --mode all

smoke:     # run the 9 demo queries
	./elasticsearch/smoke_test.sh
