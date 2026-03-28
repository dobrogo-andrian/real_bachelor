import time
import sys
import unittest


def main():
    sys.dont_write_bytecode = True
    suite = unittest.defaultTestLoader.discover("tests")
    started_at = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=1, stream=sys.stdout).run(suite)
    duration_seconds = time.perf_counter() - started_at

    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(getattr(result, "skipped", []))
    expected_failures = len(getattr(result, "expectedFailures", []))
    unexpected_successes = len(getattr(result, "unexpectedSuccesses", []))
    passed = total - failures - errors - skipped - expected_failures - unexpected_successes

    print()
    print("Test statistics")
    print(f"  Total: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failures: {failures}")
    print(f"  Errors: {errors}")
    print(f"  Skipped: {skipped}")
    print(f"  Expected failures: {expected_failures}")
    print(f"  Unexpected successes: {unexpected_successes}")
    print(f"  Duration: {duration_seconds:.3f}s")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
