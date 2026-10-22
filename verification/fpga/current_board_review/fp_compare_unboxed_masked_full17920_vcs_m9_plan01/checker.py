"""Exact shared six-event+owner+strict composition; new spec/strict injected."""
import sys
from shared import module
_m=module('masked17920_worker_checker','checker.py')
sys.modules[__name__]=_m
