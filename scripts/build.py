"""Generation of the data files."""

import logging
import os
from contextlib import contextmanager
from typing import Any

from scripts import summary
from scripts.datasets import DATASETS, Dataset
from scripts.published import published_document, write_document
from swiss_locator.remote_data import spec

# Below this share of the published items, a new version is considered broken
MIN_SIZE_RATIO = 0.5

log = logging.getLogger(__name__)


class DatasetError(Exception):
    pass


def build_files(
    output_dir: str, publish: bool = False, only: list | None = None
) -> dict[str, dict]:
    """Generate the data files into a folder.

    :param publish: for GitHub Pages. A dataset that cannot be generated, or is
                    much smaller than its published version, keeps its
                    published version: a source being temporarily down never
                    removes data from the plugin. A manifest is also written.
    :param only: names of the files to generate, all if None
    :return: a report by file name, with its "status" ("updated", "kept" or
             "failed"), the "notes" logged to the summary logger, and either
             "generated" and "count", or "error"
    """
    report = {}
    for dataset in DATASETS:
        if only and dataset.file_name not in only:
            continue
        with _summary_notes() as notes:
            try:
                if publish:
                    document, status = _publishable_document(dataset)
                else:
                    document, status = _generate(dataset, None), "updated"
            except Exception as e:
                log.error("%s could not be generated: %s", dataset.file_name, e)
                report[dataset.file_name] = {
                    "status": "failed",
                    "error": str(e),
                    "notes": notes,
                }
                continue
        write_document(os.path.join(output_dir, dataset.file_name), document)
        report[dataset.file_name] = {
            "status": status,
            "generated": document["generated"],
            "count": _count(dataset, _data(document)),
            "notes": notes,
        }

    if publish:
        manifest = {
            file_name: {key: entry[key] for key in ("status", "generated", "count")}
            for file_name, entry in report.items()
            if entry["status"] != "failed"
        }
        write_document(os.path.join(output_dir, spec.MANIFEST), spec.wrap(manifest))
    return report


def _generate(dataset: Dataset, published: dict | None) -> dict:
    previous = _data(published)
    data = dataset.build(previous)
    size = dataset.count(data)
    published_size = _count(dataset, previous)
    if size == 0:
        raise DatasetError("no data")
    if size < MIN_SIZE_RATIO * published_size:
        raise DatasetError(f"{size} items, against {published_size} published")
    log.info("%s: %d items", dataset.file_name, size)
    return spec.wrap(data)


def _publishable_document(dataset: Dataset) -> tuple[dict, str]:
    """Return the document to publish and whether it was "updated" or "kept"."""
    published = published_document(dataset.file_name)
    try:
        return _generate(dataset, published), "updated"
    except Exception as e:
        if published is None:
            raise DatasetError(f"{e}, and there is no published version to keep") from e
        summary.warning(
            "could not be generated (%s), keeping the version published on %s",
            e,
            published["generated"],
        )
        return published, "kept"


def _data(document: dict | None) -> Any:
    """Return the data of a document, None if it is missing or invalid."""
    try:
        return spec.unwrap(document)[1]
    except spec.InvalidDataFile:
        return None


def _count(dataset: Dataset, data: Any) -> int:
    try:
        return dataset.count(data)
    except Exception:
        return 0


class _ListHandler(logging.Handler):
    def __init__(self, messages: list):
        super().__init__()
        self.messages = messages

    def emit(self, record):
        self.messages.append(record.getMessage())


@contextmanager
def _summary_notes():
    """Collect the messages logged to the summary logger meanwhile."""
    notes = []
    handler = _ListHandler(notes)
    summary.addHandler(handler)
    try:
        yield notes
    finally:
        summary.removeHandler(handler)
