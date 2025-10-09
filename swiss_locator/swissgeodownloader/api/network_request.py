"""
/***************************************************************************
 SwissGeoDownloader
                                 A QGIS plugin
 This plugin lets you comfortably download swiss geo data.
                             -------------------
        begin                : 2021-03-14
        copyright            : (C) 2025 by Patricia Moll
        email                : pimoll.dev@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import json

from qgis.PyQt.QtCore import (
    QByteArray,
    QEventLoop,
    QUrl,
    QUrlQuery
)
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import QgsTask, QgsBlockingNetworkRequest, QgsFileDownloader

from swiss_locator.swissgeodownloader.utils.utilities import translate, log


def fetch(
        task: QgsTask,
        url: QUrl | str,
        params=None,
        header=None,
        method="get",
        decoder="json",
) -> dict | QByteArray:
    """Perform a blocking network request without the help of the
    QgsStacController. This is necessary because the controller does not
    parse all available item/asset properties of the response."""
    
    request = QNetworkRequest()
    # Prepare url
    callUrl = createUrl(url, params)
    request.setUrl(callUrl)
    
    if header:
        request.setHeader(*tuple(header))
    
    log(translate("SGD", "Start request {}").format(callUrl.toString()))
    # Start request
    http = QgsBlockingNetworkRequest()
    if method == "get":
        http.get(request, forceRefresh=True)
    elif method == "head":
        http.head(request, forceRefresh=True)
    
    # Check if request was successful
    r = http.reply()
    try:
        assert r.error() == QNetworkReply.NetworkError.NoError, r.error()
    except AssertionError:
        # Service is not reachable
        task.exception = translate("SGD",
                                   "{} not reachable or no internet connection").format(
                callUrl.toString())
        # Service returned an error
        if r.content():
            try:
                errorResp = json.loads(str(r.content(), "utf-8"))
            except json.JSONDecodeError as e:
                task.exception = str(e)
                raise e
            if "code" and "description" in errorResp:
                task.exception = (
                        translate("SGD", "{} returns error").format(
                            callUrl.toString())
                        + f": {errorResp['code']} - {errorResp['description']}"
                )
        return False
    
    # Process response
    if method == "get":
        if decoder == "json":
            try:
                content = str(r.content(), "utf-8")
                if content:
                    return json.loads(content)
                else:
                    raise Exception('Empty response')
            except json.JSONDecodeError as e:
                task.exception = str(e)
                raise Exception(task.exception)
        else:  # decoder string
            return r.content()
    elif method == "head":
        return r
    else:
        raise Exception(f"Method {method} not supported")


def fetchFile(task: QgsTask, url: QUrl | str, filename: str,
              filePath: str, part: float, params: dict | None = None):
    # Prepare url
    callUrl = QUrl(url)
    if params:
        queryParams = QUrlQuery()
        for key, value in params.items():
            queryParams.addQueryItem(key, str(value))
        callUrl.setQuery(queryParams)
    
    log(translate("SGD", 'Start download of {}').format(callUrl.toString()))
    fileFetcher = QgsFileDownloader(callUrl, filePath)
    
    def onError():
        task.exception = translate("SGD", 'Error when downloading {}'
                                   ).format(filename)
        return False
    
    def onProgress(bytesReceived, bytesTotal):
        if task.isCanceled():
            task.exception = translate("SGD", 'Download of {} was canceled'
                                       ).format(filename)
            fileFetcher.cancelDownload()
        else:
            partProgress = 0
            if bytesTotal > 0:
                partProgress = (part / 100) * (bytesReceived / bytesTotal)
            task.setProgress(task.progress() + partProgress)
    
    # Run file download in separate event loop
    eventLoop = QEventLoop()
    fileFetcher.downloadError.connect(onError)
    fileFetcher.downloadCanceled.connect(eventLoop.quit)
    fileFetcher.downloadCompleted.connect(eventLoop.quit)
    fileFetcher.downloadProgress.connect(onProgress)
    eventLoop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
    fileFetcher.downloadCompleted.disconnect(eventLoop.quit)


def createUrl(baseUrl: QUrl | str, urlParams: dict | None) -> QUrl:
    url = QUrl(baseUrl)
    if urlParams:
        queryParams = QUrlQuery()
        for key, value in urlParams.items():
            if value is None or value == "" or value == []:
                continue
            if isinstance(value, list):
                param = ",".join([str(v) for v in value])
            else:
                param = str(value)
            queryParams.addQueryItem(key, param)
        url.setQuery(queryParams)
    return url
