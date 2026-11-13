"""
Translations of the plugin, run from the repository root:

  python -m scripts.translations update   update the translation files from
                                          the strings of the source code
  python -m scripts.translations edits [--since COMMIT]
                                          prepare the translations edited in
                                          the repository to be pushed to
                                          Transifex (CI)

The translation files, swiss_locator/i18n/swiss_locator_<lang>.ts, are edited
on Transifex or directly in the repository. The Translations workflow keeps
both in sync, see .github/workflows/translations.yml.

The strings are extracted by pylupdate5. Set PYLUPDATE5 to run another one,
e.g. the one of QGIS: PYLUPDATE5="/path/to/python3 -m PyQt5.pylupdate_main"
"""

import argparse
import logging
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET

PLUGIN_DIR = "swiss_locator"
I18N_DIR = os.path.join(PLUGIN_DIR, "i18n")
SOURCE_LANGUAGE = "en"

# Author of the commits of the Translations workflow: they bring the
# translations from Transifex, they are never pushed back to it
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"

logger = logging.getLogger(__name__)


def ts_path(language: str) -> str:
    return os.path.join(I18N_DIR, f"swiss_locator_{language}.ts")


def translation_languages() -> list[str]:
    """The languages with a translation file, the source language excepted."""
    languages = []
    for name in sorted(os.listdir(I18N_DIR)):
        match = re.fullmatch(r"swiss_locator_(\w+)\.ts", name)
        if match and match.group(1) != SOURCE_LANGUAGE:
            languages.append(match.group(1))
    return languages


def source_files() -> list[str]:
    """The Python and Qt Designer files of the plugin, tests excepted."""
    files = []
    for root, dirs, names in os.walk(PLUGIN_DIR):
        dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", "tests"))
        files += [
            os.path.join(root, name)
            for name in sorted(names)
            if name.endswith((".py", ".ui"))
        ]
    return files


def update():
    """
    Update the translation files from the strings of the source code: add the
    new strings, drop the removed ones. Write the source file as well, for
    Transifex (git-ignored).
    """
    translations = [ts_path(language) for language in translation_languages()]
    command = shlex.split(os.environ.get("PYLUPDATE5", "pylupdate5"))
    subprocess.run(
        [
            *command,
            "-noobsolete",
            *source_files(),
            "-ts",
            ts_path(SOURCE_LANGUAGE),
            *translations,
        ],
        check=True,
    )
    for path in translations:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(drop_line_numbers(content))


def drop_line_numbers(content: str) -> str:
    """
    Keep only the file of the locations of the strings: the translation files
    do not change each time the code moves.
    """
    content = re.sub(r'(<location filename="[^"]*") line="\d+"', r"\1", content)
    # one location per file
    return re.sub(r'(\n *<location filename="[^"]*"/>)\1+', r"\1", content)


def edits(since: str | None = None) -> list[str]:
    """
    Keep, in each translation file, only the translations edited in the
    repository since the commit `since`, or ever without it. The other ones
    are emptied: Transifex ignores empty translations, those edited there in
    the meantime are kept. Commits of the Translations workflow are ignored.

    Return the languages with edited translations, whose files are ready to
    be pushed.
    """
    revisions = "HEAD"
    if since:
        try:
            revisions = f"{_git('merge-base', since, 'HEAD').decode().strip()}..HEAD"
        except subprocess.CalledProcessError:
            logger.warning(f"Commit {since} not found, looking at all commits")

    languages = []
    for language in translation_languages():
        path = ts_path(language)
        edited = set()
        log = _git("log", "--no-merges", "--format=%H %ae", revisions, "--", path)
        for line in log.decode().splitlines():
            commit, author = line.split(" ", 1)
            if author == BOT_EMAIL:
                continue
            before = _translations(_read(f"{commit}^", path))
            after = _translations(_read(commit, path))
            edited |= {key for key, texts in after.items() if before.get(key) != texts}

        root = _read("HEAD", path)
        edited &= _translations(root).keys()
        if not edited:
            continue
        for key, message in _messages(root):
            translation = message.find("translation")
            if translation is None:
                continue
            if key in edited:
                translation.attrib.pop("type", None)
            else:
                translation.attrib["type"] = "unfinished"
                for element in [translation, *translation.iter("numerusform")]:
                    element.text = None
        with open(path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n')
            f.write(ET.tostring(root, encoding="unicode"))
            f.write("\n")
        logger.info(f"{language}: {len(edited)} translation(s) to push")
        languages.append(language)
    return languages


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def _read(revision: str, path: str) -> ET.Element | None:
    """The translation file at this revision, None if it does not exist."""
    try:
        return ET.fromstring(_git("show", f"{revision}:{path}"))
    except subprocess.CalledProcessError:
        return None


def _messages(root: ET.Element):
    """Yield the key (context, source, comment) and the element of each message."""
    for context in root.iter("context"):
        name = context.findtext("name", "")
        for message in context.iter("message"):
            source = message.findtext("source", "")
            yield (name, source, message.findtext("comment", "")), message


def _translations(root: ET.Element | None) -> dict[tuple, tuple]:
    """The texts of the translated messages, by key."""
    translations = {}
    for key, message in _messages(root) if root is not None else ():
        translation = message.find("translation")
        if translation is None or translation.get("type") in ("obsolete", "vanished"):
            continue
        forms = translation.findall("numerusform")
        texts = tuple(form.text or "" for form in forms or [translation])
        if any(texts):
            translations[key] = texts
    return translations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.translations",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("update", help="update the translation files")
    edits_parser = commands.add_parser(
        "edits",
        help="keep only the translations edited in the repository, print their "
        "languages",
    )
    edits_parser.add_argument(
        "--since", metavar="COMMIT", help="edited after this commit"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "update":
        update()
    else:
        print(",".join(edits(args.since)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
