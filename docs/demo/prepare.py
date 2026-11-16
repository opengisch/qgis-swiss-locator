"""
Prepare the QGIS profile of the demo video, see run.sh.

    python3 docs/demo/prepare.py PROFILES_PATH PLUGIN_SOURCE

Installs the plugin from PLUGIN_SOURCE, a swiss_locator folder, with the data
published on GitHub Pages, in the profile "demo", in English. The rest of the
profile is kept between runs: its network cache makes the tiles, the searches
and the point cloud load faster the second time.
"""

import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from scripts.published import download  # noqa: E402


def install_plugin(source: str, plugins_dir: str):
    plugin_dir = os.path.join(plugins_dir, "swiss_locator")
    shutil.rmtree(plugin_dir, ignore_errors=True)
    shutil.copytree(
        source,
        plugin_dir,
        ignore=shutil.ignore_patterns("__pycache__", "tests", "bundled"),
    )
    if not download(os.path.join(plugin_dir, "remote_data", "bundled")):
        sys.exit("The data published on GitHub Pages could not be downloaded")


def welcome_dialog_version(source: str) -> int:
    with open(os.path.join(source, "gui", "welcome_dialog.py")) as f:
        return int(re.search(r"^WELCOME_DIALOG_VERSION = (\d+)$", f.read(), re.M)[1])


def write_settings(profile_dir: str, source: str):
    """English, the plugin, no dialog at launch, and the catalogue of the
    geoportal only: the results of viageo.ch would crowd the lidar search.
    DB Manager is off: QGIS 4.2 warns at launch that it will be removed.
    Written again at each run, so that each run starts the same. On macOS,
    QGIS reads them from qgis.org/, not from QGIS/ as on Linux."""
    settings_dir = os.path.join(
        profile_dir, "qgis.org" if sys.platform == "darwin" else "QGIS"
    )
    os.makedirs(settings_dir, exist_ok=True)
    with open(os.path.join(settings_dir, "QGIS4.ini"), "w") as f:
        f.write(
            f"""[locale]
overrideFlag=true
userLocale=en_US
globalLocale=en_US

[PythonPlugins]
swiss_locator=true
db_manager=false
MetaSearch=false

[plugins]
swiss_locator_plugin\\welcome_dialog_version={welcome_dialog_version(source)}

[qgis]
checkVersion=false
showTips=false
projOpenAtLaunch=1

[app]
first-run=false
"""
        )


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    profiles_path, source = sys.argv[1:]
    profile_dir = os.path.join(profiles_path, "profiles", "demo")
    install_plugin(source, os.path.join(profile_dir, "python", "plugins"))
    write_settings(profile_dir, source)


if __name__ == "__main__":
    main()
