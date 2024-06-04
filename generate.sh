#!/bin/bash
set -e
python3 -m build
pip3 install ./dist/*.whl --force-reinstall
# stubgen -m fizzpy -o ./