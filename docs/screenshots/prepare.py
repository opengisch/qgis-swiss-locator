"""
Prepare a QGIS profile to take the screenshots in a language, see run.sh.

    python3 docs/screenshots/prepare.py LANG PROFILES_PATH

Installs the plugin from the sources, with the translations of its latest
release and the data published on GitHub Pages, and sets the language.
"""

import io
import json
import os
import shutil
import sys
import urllib.request
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from scripts.published import download  # noqa: E402

LATEST_RELEASE = (
    "https://api.github.com/repos/opengisch/qgis-swiss-locator/releases/latest"
)
LOCALES = {"en": "en_US", "fr": "fr_CH", "de": "de_CH", "it": "it_CH"}


def get(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "qgis-swiss-locator docs"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def install_plugin(plugins_dir: str) -> str:
    plugin_dir = os.path.join(plugins_dir, "swiss_locator")
    shutil.rmtree(plugin_dir, ignore_errors=True)
    shutil.copytree(
        os.path.join(REPO, "swiss_locator"),
        plugin_dir,
        ignore=shutil.ignore_patterns("__pycache__", "tests", "bundled"),
    )
    if not download(os.path.join(plugin_dir, "remote_data", "bundled")):
        sys.exit("The data published on GitHub Pages could not be downloaded")
    return plugin_dir


def install_translations(plugin_dir: str):
    """The translations are not in the repository, take those of the release."""
    release = json.loads(get(LATEST_RELEASE))
    asset = next(a for a in release["assets"] if a["name"].endswith(".zip"))
    i18n_dir = os.path.join(plugin_dir, "i18n")
    os.makedirs(i18n_dir, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(get(asset["browser_download_url"]))) as archive:
        for name in archive.namelist():
            if name.startswith("swiss_locator/i18n/") and name.endswith(".qm"):
                with open(os.path.join(i18n_dir, os.path.basename(name)), "wb") as f:
                    f.write(archive.read(name))
    print(f"Translations of release {release['tag_name']}")


def write_settings(profile_dir: str, lang: str):
    """The language, the plugin, and a new project at launch rather than the
    welcome page, which cannot be grabbed under Xvfb."""
    settings_dir = os.path.join(profile_dir, "QGIS")
    os.makedirs(settings_dir, exist_ok=True)
    locale = LOCALES[lang]
    with open(os.path.join(settings_dir, "QGIS4.ini"), "w") as f:
        f.write(
            f"""[locale]
overrideFlag=true
userLocale={locale}
globalLocale={locale}

[PythonPlugins]
swiss_locator=true

[qgis]
checkVersion=false
showTips=false
projOpenAtLaunch=1

[app]
first-run=false
"""
        )


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in LOCALES:
        sys.exit(__doc__)
    lang, profiles_path = sys.argv[1:]
    profile_dir = os.path.join(profiles_path, "profiles", "default")
    shutil.rmtree(profile_dir, ignore_errors=True)
    plugin_dir = install_plugin(os.path.join(profile_dir, "python", "plugins"))
    install_translations(plugin_dir)
    write_settings(profile_dir, lang)


if __name__ == "__main__":
    main()
