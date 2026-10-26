#!/bin/sh
# Unit tests for rpw.py (no game needed).
exec python3 -I "$(dirname "$0")/test_rpw.py" -v 2>&1
