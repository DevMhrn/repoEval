#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
cd /repo
if pytest -v /verifier/tests/; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
exit 0
