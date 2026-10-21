#!/usr/bin/env python3
"""v1 command compatibility; stores scoped Netscape cookies in the private cache."""

import sys

from videodl.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["login", "douyin", *sys.argv[1:]]))
