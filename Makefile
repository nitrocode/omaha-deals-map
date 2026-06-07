.PHONY: install scrape parse extract geocode build all serve test lint review rebuild clean

install:
	pip install -e ".[dev]"

scrape:
	python scripts/01_fetch.py

parse:
	python scripts/02_parse.py

extract:
	python scripts/03_extract_times.py

geocode:
	python scripts/04_geocode.py

build:
	python scripts/05_build.py

all: scrape parse extract geocode build

rebuild:
	python scripts/01_fetch.py --force
	python scripts/02_parse.py --force
	python scripts/03_extract_times.py --force
	python scripts/04_geocode.py --force
	python scripts/05_build.py --force

serve:
	python -m http.server 8000 --directory site

test:
	pytest -q

lint:
	ruff check .

review:
	python scripts/review_queue.py

clean:
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name '*.egg-info' -exec rm -rf {} +
