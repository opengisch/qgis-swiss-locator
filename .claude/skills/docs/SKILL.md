---
name: docs
description: "Write or update the user documentation of the plugin (docs/, Zensical, in en, fr, de and it), take its screenshots with QGIS in Docker, build it and check it."
---

# The documentation

The user documentation, published on <https://opengisch.github.io/qgis-swiss-locator/> by
`.github/workflows/docs.yml`, on a push to `main` or `docs`.

## Use

```bash
pip install -r docs/requirements.txt
python docs/build.py --strict                  # every language into docs/site, as CI
zensical serve -f docs/mkdocs.fr.yml           # preview one language while editing
docs/screenshots/run.sh                        # every screenshot, every language
SCREENSHOTS_ONLY=profile,wmts docs/screenshots/run.sh fr de
```

`run.sh` needs Docker and a few GB of free disk. It prints the results of each search: read them when a shot
fails.

## Where things are

| Path                              | Holds                                                                 |
|-----------------------------------|-----------------------------------------------------------------------|
| `docs/en`, `fr`, `de`, `it`       | The pages, one copy per language, with the same file names            |
| `docs/<lang>/assets/screenshots`  | The screenshots of that language, generated                           |
| `docs/mkdocs.yml`                 | The configuration, English; `mkdocs.<lang>.yml` inherit it, with the titles of the navigation |
| `docs/overrides`                  | What all languages share: the logo, `shortcuts.js`                    |
| `docs/build.py`                   | Builds each language into `docs/site/<lang>`, and the root page, which sends visitors to the language of their browser |
| `docs/screenshots`                | `run.sh` starts QGIS in Docker, `prepare.py` installs the plugin, `take_screenshots.py` drives QGIS, `fake_lidar.py` makes the point cloud of the profile |

## Rules

- Zensical does not translate a site. A change to a page is made in the four languages, in the same commit.
  `build.py --strict` fails when a language misses a page or an image; Zensical checks the links and anchors.
- The same file names in every language: the language selector switches to the same page. A link to an anchor
  keeps the English id on the translated heading: `## Dans les options de QGIS {#in-the-options-of-qgis}`.
- A label in bold is the one QGIS and the plugin show in the language of the page: read it on the screenshot of
  that language. When QGIS or the plugin has no translation for it, it shows English, and so does the page.
- A shortcut is written as on Windows and Linux, `++ctrl+k++`, `++alt+x++`, `++enter++`. On macOS,
  `shortcuts.js` shows Cmd, Option and Return, as QGIS takes them there.
- A screenshot is taken by `take_screenshots.py`, never by hand: a function of `SHOTS` saves
  `docs/<lang>/assets/screenshots/<name>.png`. What is typed in the locator differs by language
  (`LAYER_SEARCH`, `OPENDATA_SEARCH`): the example of a page matches its screenshots.
- Look at every new screenshot with `Read`. The searches query live services: a blank map, a missing result or
  a message of error is a failed shot, not a passed one.
- Take again only the shots that changed, with `SCREENSHOTS_ONLY`: each PNG weighs some hundred KB in the
  history.
- GitHub Pages serves one site: the documentation, and the data files of the plugin under `data/v1/`. Each
  deployment replaces it all. `docs.yml` publishes the data again as it is online (`python -m scripts fetch
  --site`), `update-data.yml` builds the documentation again. Never deploy a site without `data/v1/`.

## Gotchas

- `qgis/qgis` is only published for amd64: on Apple silicon it runs emulated, QGIS takes about 20 s to start.
- The settings of QGIS 4 are in `QGIS/QGIS4.ini`. The plugin takes its language from `locale/userLocale`,
  which `prepare.py` writes. The translations of the plugin are not in the repository: `prepare.py` takes those
  of the latest release.
- `QgsLocatorWidget` comes back from `findChildren` as a `QWidget`: `sip.cast` it. It keeps its text after
  Escape, and `search("")` does not clear it: `new_project()` does.
- Adding the first layer to an empty project zooms to its full extent: zoom after, as `background()` does.
- The welcome page of QGIS 4 is a QML view: grabbing the window while it shows hangs QGIS under Xvfb.
  `prepare.py` starts QGIS on a new project, `main()` adds a layer before any shot.
- The welcome page also hides the map of an empty project: add a layer, wait, then zoom, as `background()`
  does. Without layers, the map keeps its last image until `refresh()`.
- A shot that hangs: grab the Xvfb screen from inside the container, with the `DISPLAY` and `XAUTHORITY` of
  `/proc/<pid of qgis>/environ` and `QApplication.primaryScreen().grabWindow(0)`.
- The national maps are sharp at the scales of the WMTS only: zoom with `SCALE`.
- A point result only pans the map: zoom to the right scale before the search.
- A label of QGIS in the running language: `QCoreApplication.translate("QgsElevationProfileWidget", "Capture Curve")`.
- A modal dialog, such as the options of QGIS, blocks the script: grab it from a `QTimer`.
- The image has no PDAL: `fake_lidar.py` writes an Entwine Point Tile dataset, read by the native `ept`
  provider. QGIS ignores its CRS unless written as WKT, so the script sets it.
