#!/usr/bin/env bash
# Take the screenshots of the documentation, with QGIS in Docker.
#
#   docs/screenshots/run.sh                # all languages: en fr de it
#   docs/screenshots/run.sh fr de          # some languages
#   SCREENSHOTS_ONLY=profile,wmts docs/screenshots/run.sh en
#
# They are written to docs/<lang>/assets/screenshots/. The searches query the
# live services of geo.admin.ch and opendata.swiss: results change over time.
set -euo pipefail

cd "$(dirname "$0")/../.."
IMAGE=${QGIS_IMAGE:-qgis/qgis:4.2}
LANGUAGES=${*:-en fr de it}

# The image is only published for amd64, it runs emulated on arm64
docker run --rm --platform linux/amd64 \
  -v "$PWD:/src" -w /src \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e SCREENSHOTS_ONLY="${SCREENSHOTS_ONLY:-}" \
  -e SCREENSHOTS_LIDAR=/tmp/lidar/ept.json \
  -e LANGUAGES="$LANGUAGES" \
  "$IMAGE" bash -c '
    set -eo pipefail
    python3 docs/screenshots/fake_lidar.py /tmp/lidar
    for lang in $LANGUAGES; do
      python3 docs/screenshots/prepare.py "$lang" /tmp/qgis
      # QGIS is noisy on stderr: keep the script output and the tracebacks
      set +e
      SCREENSHOTS_LANG=$lang xvfb-run -a -s "-screen 0 1600x1000x24" \
        qgis --profiles-path /tmp/qgis --lang "$lang" --nologo --noversioncheck \
        --code docs/screenshots/take_screenshots.py 2>&1 \
        | grep --line-buffered -E "^\[|^Traceback|^  |Error"
      status=${PIPESTATUS[0]}
      set -e
      test "$status" -eq 0
    done
  '
