"""Unit tests of the generation of the data files and of the command line."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from scripts import __main__ as cli
from scripts import build, summary
from scripts.datasets import Dataset
from swiss_locator.remote_data import spec

PUBLISHED = spec.wrap(list(range(10)), "2026-01-01T00:00:00Z")


def failing_build(previous):
    raise RuntimeError("source down")


def dataset(file_name, build_function):
    return Dataset(file_name, build_function, len)


class BuildTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output_dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def build_files(self, datasets, published=None, **kwargs):
        def published_document(file_name):
            return (published or {}).get(file_name)

        with (
            mock.patch.object(build, "DATASETS", datasets),
            mock.patch.object(build, "published_document", published_document),
        ):
            return build.build_files(self.output_dir, **kwargs)

    def read(self, file_name):
        with open(os.path.join(self.output_dir, file_name), encoding="utf-8") as f:
            return json.load(f)

    def exists(self, file_name):
        return os.path.exists(os.path.join(self.output_dir, file_name))


class TestPublish(BuildTestCase):
    """Generation of the GitHub Pages site."""

    def publish(self, build_function, published=PUBLISHED):
        report = self.build_files(
            [dataset("test.json", build_function)],
            {"test.json": published} if published else None,
            publish=True,
        )
        document = self.read("test.json") if self.exists("test.json") else None
        return report["test.json"], document

    def test_updated(self):
        entry, document = self.publish(lambda previous: list(range(8)))
        self.assertEqual(entry["status"], "updated")
        self.assertEqual(entry["count"], 8)
        self.assertEqual(spec.unwrap(document)[1], list(range(8)))

    def test_build_gets_published_data(self):
        received = []
        self.publish(lambda previous: received.append(previous) or [1] * 10)
        self.assertEqual(received, [list(range(10))])

    def test_first_publication(self):
        entry, document = self.publish(lambda previous: [1], published=None)
        self.assertEqual(spec.unwrap(document)[1], [1])

    def test_failure_keeps_published(self):
        # failing, empty, much smaller than the published version
        for build_function in (
            failing_build,
            lambda previous: [],
            lambda previous: [1, 2, 3],
        ):
            with self.subTest(build_function=build_function):
                entry, document = self.publish(build_function)
                self.assertEqual(entry["status"], "kept")
                self.assertEqual(document, PUBLISHED)
                self.assertIn("keeping the version published on", entry["notes"][0])

    def test_failure_without_published(self):
        entry, document = self.publish(failing_build, published=None)
        self.assertEqual(entry["status"], "failed")
        self.assertIn("source down", entry["error"])
        self.assertIsNone(document)

    def test_unreadable_published_version_does_not_block(self):
        entry, document = self.publish(lambda previous: [1], spec.wrap(None))
        self.assertEqual(spec.unwrap(document)[1], [1])

    def test_manifest(self):
        datasets = [
            dataset("ok.json", lambda previous: [1, 2]),
            dataset("kept.json", failing_build),
            dataset("missing.json", failing_build),
        ]
        self.build_files(datasets, {"kept.json": PUBLISHED}, publish=True)
        manifest = spec.unwrap(self.read(spec.MANIFEST))[1]
        self.assertEqual(
            manifest,
            {
                "ok.json": {
                    "status": "updated",
                    "generated": self.read("ok.json")["generated"],
                    "count": 2,
                },
                "kept.json": {
                    "status": "kept",
                    "generated": PUBLISHED["generated"],
                    "count": 10,
                },
            },
        )

    def test_summary_notes(self):
        def build_function(previous):
            summary.info("%d services", 3)
            return [1]

        datasets = [dataset("a.json", build_function), dataset("b.json", lambda p: [1])]
        report = self.build_files(datasets, publish=True)
        self.assertEqual(report["a.json"]["notes"], ["3 services"])
        self.assertEqual(report["b.json"]["notes"], [])


class TestLocalBuild(BuildTestCase):
    """Generation into the plugin sources, to test it locally."""

    def test_failure_is_not_replaced_by_published_version(self):
        datasets = [
            dataset("ok.json", lambda previous: [1]),
            dataset("failing.json", failing_build),
        ]
        report = self.build_files(datasets, {"failing.json": PUBLISHED})
        self.assertEqual(report["failing.json"]["status"], "failed")
        self.assertEqual(spec.unwrap(self.read("ok.json"))[1], [1])
        self.assertFalse(self.exists("failing.json"))
        self.assertFalse(self.exists(spec.MANIFEST))

    def test_no_previous_data(self):
        received = []
        datasets = [
            dataset("a.json", lambda previous: received.append(previous) or [1])
        ]
        self.build_files(datasets, {"a.json": PUBLISHED})
        self.assertEqual(received, [None])

    def test_only(self):
        datasets = [
            dataset("a.json", lambda previous: [1]),
            dataset("b.json", lambda previous: [1]),
        ]
        self.build_files(datasets, only=["b.json"])
        self.assertFalse(self.exists("a.json"))
        self.assertTrue(self.exists("b.json"))


REPORT = {
    "a.json": {"status": "updated", "generated": "t", "count": 3, "notes": ["n"]},
    "b.json": {"status": "kept", "generated": "t", "count": 9, "notes": []},
}


class TestCommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, report=REPORT):
        output = io.StringIO()
        with (
            mock.patch.object(spec, "BUNDLED_DIR", self.tmp.name),
            mock.patch.object(cli, "build_files", return_value=report) as build_files,
            mock.patch.object(cli, "download", return_value=False) as download,
            mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}),
            redirect_stdout(output),
        ):
            code = cli.main(list(args))
        return code, build_files, download, output.getvalue()

    def test_local_build(self):
        code, build_files, _, output = self.run_cli("build")
        self.assertEqual(code, 0)
        build_files.assert_called_once_with(self.tmp.name, only=None)
        self.assertIn("✓ a.json: updated, 3 items\n      n\n", output)
        self.assertIn("! b.json: kept, 9 items", output)

    def test_failure_exit_code(self):
        report = {"a.json": {"status": "failed", "error": "boom", "notes": []}}
        code, _, _, output = self.run_cli("build", report=report)
        self.assertEqual(code, 1)
        self.assertIn("✗ a.json: FAILED, boom", output)

    def test_site_build(self):
        _, build_files, _, _ = self.run_cli(
            "build", "--site", "_site", "--only", spec.MAP_GEO_ADMIN_LAYERS
        )
        build_files.assert_called_once_with(
            os.path.join("_site", spec.DATA_PATH),
            publish=True,
            only=[spec.MAP_GEO_ADMIN_LAYERS],
        )

    def test_job_summary(self):
        job_summary = os.path.join(self.tmp.name, "summary.md")
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": job_summary}):
            with (
                mock.patch.object(cli, "build_files", return_value=REPORT),
                redirect_stdout(io.StringIO()),
            ):
                cli.main(["build", "--site", self.tmp.name])
        with open(job_summary, encoding="utf-8") as f:
            self.assertIn("✓ a.json: updated, 3 items", f.read())

    def test_fetch(self):
        code, _, download, _ = self.run_cli("fetch")
        self.assertEqual(code, 1)
        download.assert_called_once_with(self.tmp.name)


if __name__ == "__main__":
    unittest.main()
