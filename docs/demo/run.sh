#!/usr/bin/env bash
# Record the demo video of the plugin, on macOS: drives the local QGIS app and
# records its window with screencapture. See .claude/skills/demo/SKILL.md.
#
#   docs/demo/run.sh                                # the plugin of the checkout
#   DEMO_REF=my-branch docs/demo/run.sh             # the plugin of a branch
#   DEMO_SCRIPT=other.py docs/demo/run.sh           # another script in QGIS
#   DEMO_RECORD=0 docs/demo/run.sh                  # rehearse, no recording
#
# Writes $DEMO_WORK/demo.mp4, 1280x800. Hands off the mouse and the keyboard
# while it runs: the script moves the real pointer, QGIS must stay in front.
set -euo pipefail

cd "$(dirname "$0")/../.."
REPO=$PWD
APP=${QGIS_APP:-/Applications/QGIS-final-4_2_2.app}
WORK=${DEMO_WORK:-$HOME/Library/Caches/qgis-swiss-locator-demo}
SCRIPT=${DEMO_SCRIPT:-$REPO/docs/demo/demo.py}
RECORD=${DEMO_RECORD:-1}
FFMPEG=${FFMPEG:-/opt/homebrew/bin/ffmpeg}
CONTROL=$WORK/control

mkdir -p "$WORK"
rm -rf "$CONTROL"
mkdir -p "$CONTROL"
: >"$WORK/qgis.log"

now() { /usr/bin/python3 -c 'import time; print(f"{time.time():.3f}")'; }

# The plugin, from the working tree or from a git ref
SOURCE=$REPO/swiss_locator
if [ -n "${DEMO_REF:-}" ]; then
  rm -rf "$WORK/src"
  mkdir -p "$WORK/src"
  git archive "$DEMO_REF" swiss_locator | tar -x -C "$WORK/src"
  SOURCE=$WORK/src/swiss_locator
fi

# The Python of QGIS: prepare.py needs Python >= 3.10
PYTHONHOME=$APP/Contents/Frameworks \
  PYTHONPATH=$APP/Contents/Frameworks/lib/python3.12/site-packages \
  "$APP/Contents/MacOS/python3.12" docs/demo/prepare.py "$WORK/qgis" "$SOURCE"

# open, rather than the binary: QGIS comes to the front
open -n -W -a "$APP" \
  --env DEMO_CONTROL="$CONTROL" \
  --stdout "$WORK/qgis.log" --stderr "$WORK/qgis.log" \
  --args --profiles-path "$WORK/qgis" --profile demo \
  --nologo --noversioncheck --code "$SCRIPT" &
QGIS=$!

# The script writes the region of the window once ready
until [ -f "$CONTROL/region" ]; do
  if ! kill -0 "$QGIS" 2>/dev/null; then
    echo "QGIS stopped before the demo started, see $WORK/qgis.log" >&2
    exit 1
  fi
  sleep 0.5
done

if [ "$RECORD" = 1 ]; then
  rm -f "$WORK/raw.mov"
  # screencapture stops recording at the end of its input: keep it open
  mkfifo "$CONTROL/stdin"
  screencapture -v -C -R"$(cat "$CONTROL/region")" "$WORK/raw.mov" <"$CONTROL/stdin" &
  RECORDER=$!
  exec 3>"$CONTROL/stdin"
  now >"$CONTROL/recording-start"
  sleep 2
fi
touch "$CONTROL/go"

until [ -f "$CONTROL/done" ] || ! kill -0 "$QGIS" 2>/dev/null; do
  sleep 0.5
done

if [ "$RECORD" = 1 ]; then
  # macOS can stop a recording, ScreenCaptureKit error -3821 in the log
  if ! kill -INT "$RECORDER" 2>/dev/null; then
    echo "screencapture stopped before the end of the demo: run it again" >&2
    exit 1
  fi
  wait "$RECORDER" || true
  now >"$CONTROL/recording-stop"
  exec 3>&-
fi
wait "$QGIS" || true
grep -E "^\[demo\]|^Traceback|^  File|Error" "$WORK/qgis.log" || true

if [ ! -f "$CONTROL/done" ] || [ "$(cat "$CONTROL/done")" != ok ]; then
  echo "The demo failed, see $WORK/qgis.log" >&2
  exit 1
fi
if [ "$RECORD" = 1 ]; then
  /usr/bin/python3 docs/demo/encode.py "$WORK/raw.mov" "$CONTROL" "$WORK/demo.mp4" "$FFMPEG"
fi
