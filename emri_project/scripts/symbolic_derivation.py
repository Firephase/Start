#!/usr/bin/env python3
"""Print symbolic derivation of Schwarzschild geodesics."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from emri_project.symbolic.schwarzschild import print_summary

if __name__ == "__main__":
    print_summary()
