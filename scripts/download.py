#!/usr/bin/env python3
"""Portable skill entry point; importing it has no installation side effects."""

from videodl.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
