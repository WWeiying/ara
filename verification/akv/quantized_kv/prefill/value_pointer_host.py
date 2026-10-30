#!/usr/bin/env python3
"""Reuse the exact host acceptance fixture with a pointer-transport candidate."""
import value_cache_host as acceptance
from value_pointer_sources import generate as pointer_generate
from pathlib import Path


def generate(out):
    return pointer_generate(out)+[Path(__file__)]


if __name__=='__main__':
    acceptance.generate=generate
    acceptance.main()
