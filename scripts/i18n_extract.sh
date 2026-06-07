#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
I18N_DIR="${ROOT_DIR}/src/iPhoto/resources/i18n"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

cp "${I18N_DIR}/iPhoto_de.ts" "${TMP_DIR}/iPhoto_de.ts"
cp "${I18N_DIR}/iPhoto_zh_CN.ts" "${TMP_DIR}/iPhoto_zh_CN.ts"

restore_translations() {
  cp "${TMP_DIR}/iPhoto_de.ts" "${I18N_DIR}/iPhoto_de.ts"
  cp "${TMP_DIR}/iPhoto_zh_CN.ts" "${I18N_DIR}/iPhoto_zh_CN.ts"
  echo "$1" >&2
  exit 1
}

has_active_messages() {
  python - "$1" <<'PY'
import sys
import xml.etree.ElementTree as ET

tree = ET.parse(sys.argv[1])
for message in tree.findall(".//message"):
    translation = message.find("translation")
    if translation is None or translation.get("type") != "vanished":
        sys.exit(0)

sys.exit(1)
PY
}

if ! python "${ROOT_DIR}/tools/extract_i18n_strings.py" \
  --source "${ROOT_DIR}/src/iPhoto/gui" \
  --source "${ROOT_DIR}/src/maps" \
  --ts "${I18N_DIR}/iPhoto_de.ts" \
  --ts "${I18N_DIR}/iPhoto_zh_CN.ts"; then
  restore_translations "Python i18n extraction failed; existing translations were preserved."
fi

if ! has_active_messages "${I18N_DIR}/iPhoto_de.ts" || ! has_active_messages "${I18N_DIR}/iPhoto_zh_CN.ts"; then
  restore_translations "Python i18n extraction did not extract active messages; existing translations were preserved."
fi
