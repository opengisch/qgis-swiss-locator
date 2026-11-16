---
name: demo
description: "Record the demo video of the plugin, for LinkedIn or the README: drives the local QGIS app on macOS as a user would and records its window, a small 1280x800 MP4."
---

# The demo video

About 50 s, 1280x800, H.264, under 10 MB: plays on LinkedIn and inline in a GitHub README.

## Use

```bash
docs/demo/run.sh                                # the plugin of the checkout
DEMO_REF=my-branch docs/demo/run.sh             # the plugin of a branch
DEMO_RECORD=0 docs/demo/run.sh                  # rehearse, no recording
```

It writes `~/Library/Caches/qgis-swiss-locator-demo/demo.mp4` (`DEMO_WORK` to change). Hands off the mouse and
the keyboard while it runs, about 2 minutes: the script moves the real pointer, QGIS must stay in front. Turn on Do
Not Disturb. Needs the QGIS 4.2.2 app (`QGIS_APP`), `brew install ffmpeg`, and the Screen Recording permission for
the app running the shell (VS Code).

Check every take: tile its frames and look at them with `Read`.

```bash
ffmpeg -i demo.mp4 -vf "fps=1/2,scale=640:-1,tile=3x3" sheet%d.png
ffmpeg -ss 36 -t 4 -i demo.mp4 -vf "fps=3,scale=480:-1,tile=4x3" -frames:v 1 moment.png
```

## Where things are

| Path                   | Holds                                                                                      |
|------------------------|--------------------------------------------------------------------------------------------|
| `docs/demo/run.sh`     | Prepares the profile, starts QGIS with `open`, records the window with `screencapture -v`  |
| `docs/demo/prepare.py` | The profile `demo`: the plugin, its published data, English, no dialog at launch           |
| `docs/demo/demo.py`    | The scenario, run by QGIS with `--code`: the steps of `STEPS`, the places and the camera at the top |
| `docs/demo/encode.py`  | Cuts the recording to the demo, plays the waits `SPEED` times faster, encodes the MP4      |

`demo.py` and `run.sh` talk through files in `$DEMO_WORK/control`: `region` (the window, written when ready),
`go` (written once recording), `marks.json` (the waits to speed up), `done`.

## The scenario

From an empty project: the light base map (`chb `), the search for "gare de vevey" and a zoom with the wheel, an
elevation profile drawn across the town, the search for "lidar", the list scrolled down to swissSURFACE3D, the file
list, **Deselect all**, **Select on map**, a rectangle over the tile 2554-1145, **Download** (COPC, streamed: no
folder to choose), the points in the profile, a 3D view and a camera move closing in on the old town.

Pacing asked for: pointer moves not too fast, short pauses after each action, no waiting for the map to render
before going on (the zoom shows the scaled map while the tiles load), waits for the network sped up by
`encode.py`. Tune the `wait()` of each step, `Pointer.glide` for the moves.

## Gotchas

- On macOS, QGIS reads its settings from `<profile>/qgis.org/QGIS4.ini`, not `QGIS/QGIS4.ini` as on Linux.
- `screencapture -v` stops recording at the end of its input: `run.sh` feeds it a FIFO. macOS also stops it when
  the disk is nearly full (ScreenCaptureKit error -3821 in `log show --predicate 'process == "screencapture"'`,
  after `deleted` purges `replayd`): free some space and run again, `run.sh` says so.
- The pointer is warped with `CGWarpMouseCursorPosition`, which needs no permission. The clicks and keys are
  `QTest` events sent to the `QWindow` of the main window, so Qt dispatches them as real ones, double clicks
  included. They never reach macOS: no Accessibility permission, but Qt shows no tooltip (`QToolTip.showText`
  does), and macOS keeps the shape of the pointer: `Pointer.update_shape` overrides it with the cursor of the
  widget under the pointer.
- A result far down the locator list: `scroll_to` scrolls to it, the pointer over the list, rather than jumping.
- Mouse moves are sent only to draw the profile line and the rectangle: moves over the elevation profile leave a
  crosshair on it.
- QGIS 4 shows its welcome page (`QgsWelcomeScreen`, with news) over the map of an empty project: hidden at start.
  DB Manager is off in the profile: QGIS 4.2 warns at launch that it will be removed.
- No toolbar has the elevation profile: the script adds its action to the Map Navigation toolbar.
- A location result only pans the map: the script zooms with wheel events at the station.
- The "lidar" search waits for its result only: the search of opendata.swiss takes more than 30 s.
- A new 3D view opens in a window of its own, with the identify results: `HideNewWindows` hides both, the
  **Dock 3D Map View** action docks the view. `Qgs3DMapCanvas` is a `QWindow`, not a widget.
- The 3D map takes the extent of the 2D map at its creation, narrow by then: the script sets a larger one. The
  terrain is flat, at the height of the town, under the points.
- A new 3D view on an empty project in a geographic CRS opens a modal dialog, which blocks the script.
- Opening a dock changes the scale of the map, which keeps its extent.
- Once, the download ran twice and the second showed a message: the script fails unless it ran once.
