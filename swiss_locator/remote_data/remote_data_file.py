"""
/***************************************************************************

 QGIS Swiss Locator Plugin
 Copyright (C) 2026 Denis Rouzaud

 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/

How the plugin gets the data files published on GitHub Pages.

A file has up to two local copies:
- the cache in the QGIS profile, updated from GitHub Pages,
- the copy bundled in the plugin package at release time.
The freshest valid copy is used, so the cache of an older release does not
shadow the bundled copy of a newer one.

The cache is updated in the background, at most once per MAX_AGE, with a
conditional request. A download replaces the cache only once it has been
validated. When GitHub is unreachable or serves anything invalid, the plugin
keeps using its local copy and tries again at the next start of QGIS.
"""

import json
import os
import tempfile
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, UTC
from typing import Any

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsNetworkAccessManager

from swiss_locator.core.constants import USER_AGENT
from swiss_locator.remote_data import spec

MAX_AGE = timedelta(days=1)


def default_cache_dir() -> str:
    profile_dir = QgsApplication.qgisSettingsDirPath() or tempfile.gettempdir()
    return os.path.join(profile_dir, "cache", "swiss_locator", spec.DATA_PATH)


def _log(message: str, level=Qgis.MessageLevel.Info):
    QgsMessageLog.logMessage(message, "Swiss locator", level)


def _write_atomically(path: str, content: bytes):
    """Write a file so that readers never see it half-written."""
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "wb") as f:
        f.write(content)
    os.replace(temporary_path, path)


class RemoteDataFile:
    """A data file published on GitHub Pages and its local copies.

    data() can be called from any thread, refresh() only from the main thread.
    """

    def __init__(
        self,
        file_name: str,
        parse: Callable[[Any], Any] | None = None,
        cache_dir: str | None = None,
        bundled_dir: str = spec.BUNDLED_DIR,
        url: str | None = None,
        max_age: timedelta = MAX_AGE,
    ):
        """
        :param file_name: name of the file, see spec.DATA_FILES
        :param parse: turns the data of a document into what data() returns,
                      raises spec.InvalidDataFile (or any exception) if invalid
        :param cache_dir: defaults to a folder of the QGIS profile
        """
        self.file_name = file_name
        self.url = url or spec.url(file_name)
        self.max_age = max_age
        self._parse = parse or (lambda data: data)
        self._cache_dir = cache_dir
        self._bundled_dir = bundled_dir

        self._lock = threading.Lock()
        self._loaded = False
        self._generated = None
        self._data = None
        # conditional requests require a valid cache to fall back on
        self._cache_is_valid = False
        self._reply = None

    @property
    def cache_path(self) -> str:
        # resolved lazily, the QGIS profile is not known at import time
        return os.path.join(self._cache_dir or default_cache_dir(), self.file_name)

    @property
    def bundled_path(self) -> str:
        return os.path.join(self._bundled_dir, self.file_name)

    @property
    def generated(self) -> str | None:
        """Generation timestamp of the data in use."""
        self.data()
        return self._generated

    def data(self) -> Any:
        """Return the parsed data of the freshest valid copy, None if there is none."""
        with self._lock:
            if not self._loaded:
                self._loaded = True
                self._cache_is_valid = self._load_file(self.cache_path, "cache")
                self._load_file(self.bundled_path, "bundled copy")
                if self._data is None:
                    _log(
                        f"{self.file_name}: no local copy available yet",
                        Qgis.MessageLevel.Warning,
                    )
            return self._data

    def set_document(self, document: dict):
        """Use the given document, whatever the local copies. Meant for tests."""
        generated, data = self._read(document)
        with self._lock:
            self._loaded = True
            self._generated, self._data = generated, data

    def refresh(self, force: bool = False) -> QNetworkReply | None:
        """Update the cache from GitHub Pages in the background, if outdated.

        :param force: ignore the age of the cache
        :return: the pending reply, None if no update is needed
        """
        if self._reply is not None:
            return self._reply
        self.data()
        meta = self._read_meta() if self._cache_is_valid else {}
        if not force and not self._is_outdated(meta):
            return None

        request = QNetworkRequest(QUrl(self.url))
        request.setRawHeader(b"User-Agent", USER_AGENT)
        # The cache is handled here, bypass the one of the network access manager
        request.setAttribute(
            QNetworkRequest.Attribute.CacheLoadControlAttribute,
            QNetworkRequest.CacheLoadControl.AlwaysNetwork,
        )
        request.setAttribute(QNetworkRequest.Attribute.CacheSaveControlAttribute, False)
        if meta.get("etag"):
            request.setRawHeader(b"If-None-Match", meta["etag"].encode())
        if meta.get("last_modified"):
            request.setRawHeader(b"If-Modified-Since", meta["last_modified"].encode())

        reply = QgsNetworkAccessManager.instance().get(request)
        reply.finished.connect(lambda: self._on_finished(reply))
        self._reply = reply
        return reply

    def process_download(
        self, content: bytes, etag: str = "", last_modified: str = ""
    ) -> bool:
        """Validate downloaded content and, if it is valid, use and cache it.

        :return: True if the cache has been updated
        """
        try:
            generated, data = self._read(json.loads(content))
        except Exception as e:
            _log(
                f"{self.file_name}: ignoring the invalid file served by {self.url}: {e}",
                Qgis.MessageLevel.Warning,
            )
            return False

        current = self.generated
        if current is not None and generated < current:
            _log(
                f"{self.file_name}: the published file ({generated}) is older "
                f"than the local copy ({current}), keeping the local copy"
            )
            return False

        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        _write_atomically(self.cache_path, content)
        self._write_meta(
            {"etag": etag, "last_modified": last_modified, "checked": spec.utc_now()}
        )
        self._cache_is_valid = True
        with self._lock:
            self._use(generated, data, "downloaded file")
        return True

    def _on_finished(self, reply: QNetworkReply):
        self._reply = None
        reply.deleteLater()

        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status == 304:
            self._write_meta({**self._read_meta(), "checked": spec.utc_now()})
            _log(f"{self.file_name}: local copy is up to date")
        elif reply.error() != QNetworkReply.NetworkError.NoError:
            # retried at next start of QGIS since "checked" is not updated
            _log(
                f"{self.file_name}: could not be updated from {self.url} "
                f"({reply.errorString()}), using the local copy "
                f"generated on {self.generated}"
            )
        else:
            self.process_download(
                reply.readAll().data(),
                etag=reply.rawHeader(b"ETag").data().decode(),
                last_modified=reply.rawHeader(b"Last-Modified").data().decode(),
            )

    def _read(self, document: Any) -> tuple[str, Any]:
        generated, data = spec.unwrap(document)
        return generated, self._parse(data)

    def _load_file(self, path: str, origin: str) -> bool:
        """Use a local copy if it is valid and fresher. Return whether it is valid."""
        if not os.path.exists(path):
            return False
        try:
            with open(path, encoding="utf-8") as f:
                generated, data = self._read(json.load(f))
        except Exception as e:
            _log(
                f"{self.file_name}: ignoring the invalid {origin} {path}: {e}",
                Qgis.MessageLevel.Warning,
            )
            return False
        self._use(generated, data, origin)
        return True

    def _use(self, generated: str, data: Any, origin: str):
        """Use the data if fresher than the current one. Call with the lock held."""
        if self._generated is not None and generated <= self._generated:
            return
        self._generated, self._data = generated, data
        _log(f"{self.file_name}: using the {origin} generated on {generated}")

    @property
    def _meta_path(self) -> str:
        return f"{self.cache_path}.meta.json"

    def _read_meta(self) -> dict:
        try:
            with open(self._meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            return {}
        return meta if isinstance(meta, dict) else {}

    def _write_meta(self, meta: dict):
        os.makedirs(os.path.dirname(self._meta_path), exist_ok=True)
        _write_atomically(self._meta_path, json.dumps(meta).encode())

    def _is_outdated(self, meta: dict) -> bool:
        try:
            checked = datetime.strptime(meta["checked"], spec.TIMESTAMP_FORMAT)
        except (KeyError, TypeError, ValueError):
            return True
        age = datetime.now(UTC) - checked.replace(tzinfo=UTC)
        # a negative age means the clock went backwards
        return not timedelta(0) <= age < self.max_age
