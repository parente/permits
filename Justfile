# List targets
help:
	@just --list --unsorted


# Clean the source tree
clean:
	rm -rf .venv

# Run a local dev copy
run:
    source .venv/bin/activate && streamlit run main.py

# Create a virtualenv for local development
venv:
	#!/usr/bin/env bash
	python -m venv .venv
	source ./.venv/bin/activate
	pip install -r requirements.txt
