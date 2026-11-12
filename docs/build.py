"""
Build the documentation, in all its languages, into docs/site.

    pip install -r docs/requirements.txt
    python docs/build.py

Each language is a site of its own, docs/site/<lang>/, built from the pages of
docs/<lang>/ by docs/mkdocs.<lang>.yml. The root page sends visitors to the
language of their browser. To preview one language while editing:

    zensical serve -f docs/mkdocs.fr.yml
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent
SITE_DIR = DOCS_DIR / "site"

# The first one is the default language
LANGUAGES = {
    "en": "mkdocs.yml",
    "fr": "mkdocs.fr.yml",
    "de": "mkdocs.de.yml",
    "it": "mkdocs.it.yml",
}

ROOT_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Swiss Locator</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<noscript><meta http-equiv="refresh" content="0; url={default}/"></noscript>
<script>
  var languages = {languages};
  var preferred = (navigator.languages || [navigator.language || ""])
    .map(function (tag) {{ return tag.slice(0, 2).toLowerCase(); }})
    .filter(function (lang) {{ return languages.indexOf(lang) >= 0; }});
  location.replace((preferred[0] || "{default}") + "/");
</script>
</head>
<body>
{links}
</body>
</html>
"""


IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")


def check() -> list[str]:
    """The languages have the same pages, and their images exist.

    Zensical checks the links between pages, not the images.
    """
    problems = []
    pages = {
        lang: {p.relative_to(DOCS_DIR / lang) for p in (DOCS_DIR / lang).rglob("*.md")}
        for lang in LANGUAGES
    }
    default = next(iter(LANGUAGES))
    for lang, lang_pages in pages.items():
        for page in sorted(pages[default] - lang_pages):
            problems.append(f"{lang}/{page} is missing")
        for page in sorted(lang_pages - pages[default]):
            problems.append(f"{lang}/{page} is not in {default}")
        for page in sorted(lang_pages):
            path = DOCS_DIR / lang / page
            for image in IMAGE.findall(path.read_text(encoding="utf-8")):
                if "://" not in image and not (path.parent / image).is_file():
                    problems.append(f"{lang}/{page}: image {image} does not exist")
    return problems


def build(strict: bool) -> int:
    problems = check()
    for problem in problems:
        print(f"Warning: {problem}")
    if problems and strict:
        return 1

    shutil.rmtree(SITE_DIR, ignore_errors=True)
    for lang, config in LANGUAGES.items():
        print(f"Building {lang}", flush=True)
        command = [sys.executable, "-m", "zensical", "build", "-f", config]
        if strict:
            command.append("--strict")
        result = subprocess.run(command, cwd=DOCS_DIR)
        if result.returncode:
            return result.returncode

    default = next(iter(LANGUAGES))
    links = "\n".join(f'<p><a href="{lang}/">{lang}</a></p>' for lang in LANGUAGES)
    root_page = ROOT_PAGE.format(
        default=default,
        languages=list(LANGUAGES),
        links=links,
    )
    (SITE_DIR / "index.html").write_text(root_page, encoding="utf-8")
    # GitHub Pages serves it for any missing page. Its links are absolute.
    shutil.copy(SITE_DIR / default / "404.html", SITE_DIR / "404.html")
    print(f"Written to {SITE_DIR}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--strict", action="store_true", help="fail on warnings, as CI does"
    )
    args = parser.parse_args()
    return build(args.strict)


if __name__ == "__main__":
    sys.exit(main())
