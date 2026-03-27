#!/bin/bash
# Called by launchd to generate videos from newsbot articles
set -e

export PATH="/usr/local/bin:/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/3.13/bin:$HOME/.local/bin:$PATH"

cd "$(dirname "$0")/.."
source .venv/bin/activate

python -m pipeline from-newsbot --count 2 2>&1

exit 0
