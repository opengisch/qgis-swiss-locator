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

Requests sent from a thread that waits for their replies.

The locator searches with each filter in a thread of its own and cancels the
search from the main thread each time the text changes, processing cancels an
algorithm the same way. A search that does not end keeps every following one
waiting, and the threads share the GIL with the main thread.
"""

from collections.abc import Callable

from qgis.PyQt import sip
from qgis.PyQt.QtCore import QEventLoop
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qgis.core import QgsFeedback, QgsNetworkAccessManager


def fetch(
    requests: list[QNetworkRequest],
    feedback: QgsFeedback | None,
    handle: Callable[[int, QNetworkReply], None],
    manager: QNetworkAccessManager | None = None,
):
    """
    Sends the requests and waits for their replies, each given to handle with
    the index of its request. Returns once every reply is in, or as soon as the
    feedback is cancelled: the replies left are then not handled.

    :param manager: the network access manager of this thread, by default one
                    created for these requests
    :raises: the first exception raised by handle, once the requests are over
    """
    loop = QEventLoop()
    if feedback is not None:
        feedback.canceled.connect(loop.quit)
    own_manager = manager is None
    sent = []
    pending = {}
    errors = []

    def finished(index: int):
        reply = pending.pop(index, None)
        if reply is None:
            # Cancelled
            return
        try:
            handle(index, reply)
        except Exception as e:
            # Not raised in the slot, where PyQt would abort or report it
            errors.append(e)
        finally:
            # Even if the reply could not be read: PyQt hears late, in the
            # main thread, of an object deleted in another thread, and then
            # invalidates the wrapper at its address, maybe the one of this
            # reply by then
            if not pending:
                loop.quit()

    try:
        if feedback is not None and feedback.isCanceled():
            # Cancelled before being connected, the signal is not emitted
            # again: the requests would be waited for
            return
        if own_manager:
            manager = QNetworkAccessManager()
            manager.setRedirectPolicy(
                QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy
            )
        for index, request in enumerate(requests):
            # A reply could never finish otherwise, e.g. if the connection is
            # dropped silently on the way
            request.setTransferTimeout(QgsNetworkAccessManager.timeout())
            sent.append(manager.get(request))
            pending[index] = sent[-1]
            sent[-1].finished.connect(lambda _index=index: finished(_index))
        if pending:
            loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    finally:
        pending.clear()
        # Destroyed by Qt, not by Python with the GIL held: destructors take
        # locks of Qt that a thread can hold while it waits for the GIL.
        # Disconnected for the same reason: when the loop is destroyed, Qt
        # notifies the feedback, which takes the GIL if it was made in Python.
        if feedback is not None:
            feedback.canceled.disconnect(loop.quit)
        while sent:
            reply = sent.pop()
            try:
                reply.deleteLater()
            except RuntimeError:
                # Invalidated by PyQt, see above: deleted with its manager
                pass
        for qobject in (manager if own_manager else None, loop):
            if qobject is not None:
                sip.transferto(qobject, None)
                qobject.deleteLater()

    if errors:
        raise errors[0]
