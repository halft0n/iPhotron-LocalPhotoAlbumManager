#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
I18N_DIR="${ROOT_DIR}/src/iPhoto/resources/i18n"

pyside6-lrelease \
  "${I18N_DIR}/iPhoto_de.ts" \
  "${I18N_DIR}/iPhoto_zh_CN.ts"
