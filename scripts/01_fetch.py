"""Pipeline stage 1: fetch all active sources."""
import argparse
import sys

from scripts._fetch_main import main

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    sys.exit(main(force=ap.parse_args().force))
