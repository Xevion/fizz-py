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

# Containerized dev loop (recommended): build + test inside the manylinux image
# the wheels use, against the prebuilt .dev/getdeps tree. Isolated from host
# Homebrew/glibc drift. See scripts/dev.py.
dev-up:
    python scripts/dev.py up

# Editable-build _core in the container (the ~10s inner loop).
dev-build:
    python scripts/dev.py build

# Run the suite in the container. `just dev-test "-- -m network"` runs the
# live-network tests; pass any other pytest args after a `--` the same way.
dev-test *args:
    python scripts/dev.py test {{args}}

# Interactive shell inside the dev container.
dev-shell:
    python scripts/dev.py shell

# Stop + remove the dev container.
dev-down:
    python scripts/dev.py down

# Install the lint/type toolchain into .venv without building _core.
_tools:
    uv sync --no-install-project --group dev

# Lint and type-check Python.
check: _tools
    uv run --no-sync ruff check .
    uv run --no-sync ruff format --check .
    uv run --no-sync basedpyright

# Format Python and C++ in place.
fmt: _tools
    uv run --no-sync ruff format .
    clang-format -i _core.cpp
