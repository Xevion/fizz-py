# fizzpy dev tasks. `just build` is the fast local loop (editable _core against
# a liboqs-enabled Fizz); CI wheels are built separately via scripts/build_fizz_deps.py.

_default:
    @just --list

# Build the OQS Fizz prefix if needed, then editable-install _core against it.
build:
    python scripts/build_fizz.py ensure
    pip install -e . --no-build-isolation --config-settings=build-dir=.dev/build-editable --config-settings=cmake.define.CMAKE_PREFIX_PATH="$(python scripts/build_fizz.py prefix-path)"

# Build a non-editable wheel and force-reinstall it (full install, not the editable loop).
wheel:
    python -m build
    pip install ./dist/*.whl --force-reinstall

# Run the test suite. Defaults to the offline, deterministic subset; pass args to
# override, e.g. `just test ""` for the full suite (needs network).
test *args="-m 'not network'":
    pytest {{args}}

# Lint and type-check Python.
check:
    ruff check .
    basedpyright

# Format Python and C++ in place.
fmt:
    ruff format .
    clang-format -i _core.cpp
