.PHONY: install scrape parse extract geocode photos build all serve test lint review rebuild clean scrape-npdodge

install:
	pip install --require-hashes -r requirements.lock
	pip install -e . --no-deps

# Regenerate requirements.lock after any pyproject.toml change. Run this
# locally; CI verifies the lockfile matches via --require-hashes.
lock:
	uv pip compile pyproject.toml --extra dev --generate-hashes \
		--output-file requirements.lock

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

# Photo discovery: OSM tags + Wikidata + venue og:image. Skips already-cached
# venues; ~1 req/sec to respect Nominatim rate limits. Re-run with --force
# (see `make rebuild`) to refresh negatives.
photos:
	python scripts/06_photos.py

all: scrape parse extract geocode build photos build

rebuild:
	python scripts/01_fetch.py --force
	python scripts/02_parse.py --force
	python scripts/03_extract_times.py --force
	python scripts/04_geocode.py --force
	python scripts/05_build.py --force
	python scripts/06_photos.py --force
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

# One-off: scrape npdodge's annual happy-hour guide via Playwright (the
# site is behind Cloudflare, regular HTTP gets a challenge page).
# First-time setup:
#   pip install -e ".[oneoff]"
#   playwright install chromium
# Then this command appends new venues to data/overrides/manual_venues.yaml.
scrape-npdodge:
	python scripts/oneoff/scrape_npdodge.py
