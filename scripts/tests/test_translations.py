"""Unit tests of the translations script, without pylupdate5 nor Transifex."""

import os
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts import translations

HUMAN = ("Translator", "translator@example.com")
BOT = ("github-actions[bot]", translations.BOT_EMAIL)


def ts(**translated: str) -> str:
    """A translation file with the messages one, two and three."""
    messages = ""
    for source in ("one", "two", "three"):
        text = translated.get(source, "")
        kind = "" if text else ' type="unfinished"'
        messages += (
            f"<message><source>{source}</source>"
            f"<translation{kind}>{text}</translation></message>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
        f'<TS version="2.1" language="fr"><context><name>Ctx</name>{messages}'
        "</context></TS>\n"
    )


@unittest.skipUnless(shutil.which("git"), "git is needed")
class TestEdits(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo)
        self.addCleanup(os.chdir, self.cwd)
        os.chdir(self.repo)
        os.makedirs(translations.I18N_DIR)
        self.git("init", "--quiet")

    def git(self, *args, author=HUMAN) -> str:
        name, email = author
        env = dict(
            os.environ,
            GIT_AUTHOR_NAME=name,
            GIT_AUTHOR_EMAIL=email,
            GIT_COMMITTER_NAME=name,
            GIT_COMMITTER_EMAIL=email,
        )
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout.strip()

    def commit(self, language, content, author=HUMAN) -> str:
        with open(translations.ts_path(language), "w", encoding="utf-8") as f:
            f.write(content)
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", "edit", author=author)
        return self.git("rev-parse", "HEAD")

    def pushed(self, language) -> dict[str, str | None]:
        """The translations left in the file, those to push."""
        root = ET.parse(translations.ts_path(language)).getroot()
        return {
            message.findtext("source"): message.find("translation").text
            for message in root.iter("message")
        }

    def test_only_human_edits_since_the_commit(self):
        first = self.commit("fr", ts(one="un", three="trois"))
        # pulled from Transifex: never pushed back
        self.commit("fr", ts(one="un", two="deux", three="TROIS"), author=BOT)
        self.commit("fr", ts(one="UN", two="deux", three="TROIS"))
        self.commit("de", ts(one="eins"), author=BOT)

        self.assertEqual(translations.edits(since=first), ["fr"])
        self.assertEqual(self.pushed("fr"), {"one": "UN", "two": None, "three": None})
        root = ET.parse(translations.ts_path("fr")).getroot()
        types = [m.find("translation").get("type") for m in root.iter("message")]
        self.assertEqual(types, [None, "unfinished", "unfinished"])
        # untouched
        self.assertEqual(self.git("status", "--porcelain", "--", "*_de.ts"), "")

    def test_all_commits_without_a_commit(self):
        self.commit("fr", ts(one="un", three="trois"))
        self.commit("fr", ts(one="un", two="deux", three="TROIS"), author=BOT)

        self.assertEqual(translations.edits(), ["fr"])
        self.assertEqual(
            self.pushed("fr"), {"one": "un", "two": None, "three": "TROIS"}
        )

    def test_unknown_commit_means_all_commits(self):
        self.commit("fr", ts(one="un"))

        with self.assertLogs(translations.logger, "WARNING"):
            self.assertEqual(translations.edits(since="0" * 40), ["fr"])

    def test_nothing_edited(self):
        last = self.commit("fr", ts(one="un"))
        self.commit("fr", ts(one="un", two="deux"), author=BOT)
        # a translation emptied cannot be pushed
        self.commit("fr", ts(two="deux"))

        self.assertEqual(translations.edits(since=last), [])

    def test_source_file_ignored(self):
        self.commit(translations.SOURCE_LANGUAGE, ts())

        self.assertEqual(translations.edits(), [])


class TestDropLineNumbers(unittest.TestCase):
    def test_one_location_per_file(self):
        content = (
            "    <message>\n"
            '        <location filename="../a.py" line="12"/>\n'
            '        <location filename="../a.py" line="40"/>\n'
            '        <location filename="../b.ui" line="3"/>\n'
            "        <source>one</source>\n"
        )
        self.assertEqual(
            translations.drop_line_numbers(content),
            "    <message>\n"
            '        <location filename="../a.py"/>\n'
            '        <location filename="../b.ui"/>\n'
            "        <source>one</source>\n",
        )


if __name__ == "__main__":
    unittest.main()
