#!/usr/bin/env python3
"""v1 command compatibility; all downloads now share the verified engine."""

import sys

from videodl.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
