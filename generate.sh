#!/bin/bash
set -e
python -m build
pip install ./dist/*.whl --force-reinstall
stubgen -m fizzpy -o ./