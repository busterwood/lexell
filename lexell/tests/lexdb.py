#!/usr/bin/env python3
"""Runs the lexdb tests (tests/lexdb/run) with the conformance runner
(run.py: the same // expect: directives; run tests under LXL_CHECK=1).

    python3 lexell/tests/lexdb.py [--compiler PATH] [-j N] [filters...]

lexdb is the SQL server in cmd/lexdb*.lxl (design/lexdb.md). The module
dependency rule (tests/lexdb/imports.py) is checked first."""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


imports = load('lexdb_imports', os.path.join(HERE, 'lexdb', 'imports.py'))
if imports.main() != 0:
    sys.exit(1)

runner = load('conformance', os.path.join(HERE, 'run.py'))
runner.HERE = os.path.join(HERE, 'lexdb')
runner.main()
