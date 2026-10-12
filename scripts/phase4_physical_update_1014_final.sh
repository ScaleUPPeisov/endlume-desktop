#!/bin/bash
set -Eeuo pipefail

# Final updater acceptance executes the already hardened Vision-based normal
# updater harness directly. The base harness itself owns ERR rollback handling
# and restores exact 10.0.13 production + test-machine application on failure.
exec /bin/bash scripts/phase4_physical_update_1014_vision_retry.sh
