#!/usr/bin/env python3
"""IPGuard entry point.

Usage:
    python main.py                 # start widget + tray
    python main.py --check         # one-shot gate check (no GUI)
    python main.py --no-gate       # disable the local gate HTTP service
    python main.py --config PATH   # custom config file
"""
import sys

from ipguard.app import main

if __name__ == "__main__":
    sys.exit(main())
