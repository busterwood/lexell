#!/usr/bin/env python3
"""Runs the lexdb tests (tests/lexdb/run) with the conformance runner
(run.py: the same // expect: directives; run tests under LXL_CHECK=1).

    python3 lexell/tests/lexdb.py [--compiler PATH] [-j N] [filters...]

lexdb is the SQL server in cmd/lexdb*.lxl (design/lexdb.md)."""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('conformance', os.path.join(HERE, 'run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.HERE = os.path.join(HERE, 'lexdb')
runner.main()
