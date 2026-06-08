"""Pipeline stage 6 entry point: find venue photos. See _photos_main.py."""
import argparse
import sys

from scripts._photos_main import main

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    sys.exit(main(force=ap.parse_args().force))
