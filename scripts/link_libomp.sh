#!/usr/bin/env bash
# LightGBM's macOS wheel needs libomp, normally from Homebrew. scikit-learn's wheel bundles a copy,
# so point LightGBM at it. This only changes files inside .venv and does nothing on Linux.
set -euo pipefail
[ "$(uname)" = "Darwin" ] || exit 0

site_packages=$(uv run python -c "import sklearn, pathlib; print(pathlib.Path(sklearn.__file__).parents[1])")
library="$site_packages/lightgbm/lib/lib_lightgbm.dylib"
rpath="@loader_path/../../sklearn/.dylibs"

if ! otool -l "$library" | grep -qF "$rpath"; then
  install_name_tool -add_rpath "$rpath" "$library"
  codesign --force --sign - "$library"
fi
