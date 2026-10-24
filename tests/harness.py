#!/usr/bin/env python3
"""The runner both test files share: by default each test in its own turn,
in this process, in file order; with -j, spread over worker processes.

A test file registers its tests in TESTS (in file order) with @test, and
@test(group='name') for tests that share a story directory: a group runs
in one worker, in file order, as it would serially. Each worker imports
the test file as a module (TESTS registered, main() not run) and runs the
tests it is handed with their output captured; a passing test's output is
dropped, a failing test's is printed with its traceback.
"""

import concurrent.futures
import contextlib
import importlib.util
import io
import multiprocessing
import os
import sys
import time
import traceback


def add_jobs_argument(parser):
    parser.add_argument('-j', '--jobs', type=int, default=1,
                        help='worker processes; 0 for one per CPU (default 1: every test in this process, in file order)')


def jobs_from(args):
    return args.jobs if args.jobs > 0 else (os.cpu_count() or 1)


def registrar(tests):
    """The @test decorator for a file whose tests go in `tests`: bare, or
    @test(group='basic') to keep the test in that group's worker."""
    def test(fn=None, group=None):
        if fn is None:
            return lambda f: test(f, group)
        fn.group = group
        tests.append(fn)
        return fn
    return test


def run_one(fn):
    """(passed, seconds, traceback text or '') for fn run here."""
    t = time.time()
    try:
        fn()
        return True, time.time() - t, ''
    except Exception:
        return False, time.time() - t, traceback.format_exc()


_modules = {}


def load(path):
    """The test file as a module, in a worker. A spawned worker has already
    run it once as __mp_main__; that copy is used when it is the same file."""
    if path not in _modules:
        main = sys.modules.get('__mp_main__')
        if main is not None and os.path.abspath(getattr(main, '__file__', '') or '') == path:
            _modules[path] = main
        else:
            spec = importlib.util.spec_from_file_location('_tests_' + os.path.basename(path)[:-3], path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _modules[path] = mod
    return _modules[path]


def run_group(path, names, collect):
    """Worker side: run the named tests in order. Returns their (name,
    passed, seconds, output) and, with `collect`, the test file's set of
    that name (what the tests recorded, to merge in the parent)."""
    mod = load(path)
    by_name = {fn.__name__: fn for fn in mod.TESTS}
    results = []
    for name in names:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            ok, seconds, tb = run_one(by_name[name])
        results.append((name, ok, seconds, buf.getvalue() + tb))
    return results, set(getattr(mod, collect)) if collect else None


def groups_of(tests):
    """Tests in schedulable units: each group's tests together, in file
    order, at the group's first test; ungrouped tests one to a unit."""
    units, at = [], {}
    for fn in tests:
        if fn.group is None:
            units.append([fn.__name__])
        elif fn.group in at:
            units[at[fn.group]].append(fn.__name__)
        else:
            at[fn.group] = len(units)
            units.append([fn.__name__])
    return units


def run_here(tests):
    """Run tests in this process, in order; returns the number that failed."""
    failed = 0
    for fn in tests:
        ok, seconds, tb = run_one(fn)
        failed += not ok
        print(f'ok    {fn.__name__} ({seconds:.1f}s)' if ok else f'FAIL  {fn.__name__}', flush=True)
        if tb:
            print(tb, end='', file=sys.stderr, flush=True)
    return failed


def run(tests, path, jobs=1, collect=None, into=None, last=()):
    """Run `tests` (functions from the test file at `path`), up to `jobs`
    at a time; returns the number that failed. With jobs 1 they run here,
    in file order. With more, the sets the workers' tests filled under the
    name `collect` are merged into `into`, and `last` runs here after every
    other test: tests that read what all the others recorded."""
    if jobs <= 1:
        return run_here(tests)
    failed = 0
    units = groups_of([fn for fn in tests if fn not in last])
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(jobs, max(1, len(units))),
                                                mp_context=multiprocessing.get_context('spawn')) as pool:
        futures = [pool.submit(run_group, os.path.abspath(path), names, collect) for names in units]
        for future in concurrent.futures.as_completed(futures):
            results, seen = future.result()
            if into is not None and seen:
                into.update(seen)
            for name, ok, seconds, output in results:
                failed += not ok
                if ok:
                    print(f'ok    {name} ({seconds:.1f}s)', flush=True)
                else:
                    print(f'FAIL  {name}\n{output}', end='' if output.endswith('\n') else '\n', flush=True)
    return failed + run_here(last)
