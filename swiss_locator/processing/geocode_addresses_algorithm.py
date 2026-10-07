"""
/***************************************************************************

                            QGIS Swiss Locator Plugin
 
                             -------------------
        begin                : 2026-10-08
        copyright            : (C) 2026 by Tristan Carel
        email                : tristan.carel@protonmail.com
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

import os
import time

from qgis.PyQt.QtCore import QCoreApplication, QMetaType
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    NULL,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsExpression,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeocoderContext,
    QgsGeocoderResult,
    QgsGeometry,
    QgsProcessingException,
    QgsProcessingFeatureBasedAlgorithm,
    QgsProcessingOutputNumber,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExpression,
    QgsProcessingParameterExtent,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
)

from swiss_locator import PLUGIN_PATH
from swiss_locator.core.geocoder.swiss_geocoder import (
    FIELD_PREFIX,
    GEOCODE_ORIGINS,
    MAX_API_LIMIT,
    SwissGeocoder,
    sleep_cancellable,
    tokens,
)
from swiss_locator.core.language import get_language

STATUS_MATCHED = "matched"
STATUS_UNMATCHED = "unmatched"
STATUS_EMPTY = "empty"
STATUS_ERROR = "error"

# Index 0 is "automatic": the language configured in the plugin settings
LANGUAGE_CODES = (None, "de", "fr", "it", "rm", "en")

# The algorithm stops when this many requests failed in a row, as the
# service is most likely down or refusing the client
MAX_CONSECUTIVE_ERRORS = 5

# Candidates are always requested by batches of at least this size so that
# the candidates count can reveal ambiguous addresses
MIN_REQUEST_LIMIT = 10


class GeocodeAddressesAlgorithm(QgsProcessingFeatureBasedAlgorithm):
    """
    Geocodes a table of addresses with the geo.admin.ch search service and
    writes a point layer keeping the source attributes.
    """

    ADDRESS = "ADDRESS"
    ORIGINS = "ORIGINS"
    TARGET_CRS = "TARGET_CRS"
    LANGUAGE = "LANGUAGE"
    MAX_CANDIDATES = "MAX_CANDIDATES"
    EXTENT = "EXTENT"
    KEEP_UNMATCHED = "KEEP_UNMATCHED"
    REQUEST_DELAY = "REQUEST_DELAY"

    GEOCODED_COUNT = "GEOCODED_COUNT"
    UNMATCHED_COUNT = "UNMATCHED_COUNT"
    ERROR_COUNT = "ERROR_COUNT"
    REQUEST_COUNT = "REQUEST_COUNT"

    DEFAULT_CRS = "EPSG:2056"

    def __init__(self):
        super().__init__()
        self._source = None
        self._expression = None
        self._expression_context = None
        self._target_crs = None
        self._transform = None
        self._geocoder = None
        self._geocoder_context = None
        self._max_candidates = 1
        self._keep_unmatched = True
        self._delay_s = 0.0
        self._last_request = None
        self._cache = {}
        self._counts = {}
        self._consecutive_errors = 0
        self._reported_evaluation_errors = set()

    # ------------------------------------------------------------------
    # Description
    # ------------------------------------------------------------------

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("GeocodeAddressesAlgorithm", string)

    def createInstance(self):
        return GeocodeAddressesAlgorithm()

    def name(self) -> str:
        return "geocodeaddresses"

    def displayName(self) -> str:
        return self.tr("Geocode addresses (geo.admin.ch)")

    def group(self) -> str:
        return self.tr("Geocoding")

    def groupId(self) -> str:
        return "geocoding"

    def tags(self) -> list[str]:
        return self.tr(
            "geocode,geocoding,address,swiss,swisstopo,geo.admin.ch,csv,batch,bulk"
        ).split(",")

    def icon(self) -> QIcon:
        return QIcon(os.path.join(PLUGIN_PATH, "icons", "swiss_locator.png"))

    def helpUrl(self) -> str:
        return "https://github.com/opengisch/qgis-swiss-locator#batch-geocoding"

    def shortDescription(self) -> str:
        return self.tr(
            "Geocodes a table of Swiss addresses with the geo.admin.ch search "
            "service and creates a point layer."
        )

    def shortHelpString(self) -> str:
        return self.tr(
            "<p>Geocodes the rows of a layer or table (typically a CSV file "
            "loaded as a delimited text layer) with the search service of "
            "geo.admin.ch, the Swiss federal geoportal, and creates a point "
            "layer. The source attributes are kept and completed with the "
            "attributes described below.</p>"
            "<h3>Parameters</h3>"
            "<ul>"
            "<li><b>Address</b>: an expression giving the text to search for "
            "each row, usually a field or a concatenation of fields, e.g. "
            "<code>concat(\"street\", ' ', \"number\", ', ', \"zip\", ' ', "
            '"city")</code>.</li>'
            "<li><b>Search in</b>: the kinds of locations to search for. "
            "Building addresses are the default; cadastral parcels, postal "
            "codes, municipalities, districts, cantons and place names can "
            "be added.</li>"
            "<li><b>Output CRS</b>: coordinate reference system of the "
            "output points.</li>"
            "<li><b>Restrict search to extent</b>: when set, only locations "
            "within this extent are returned.</li>"
            "<li><b>Keep unmatched rows</b>: when checked, rows without any "
            "match and rows with an empty address are written without "
            "geometry so that no source row is lost.</li>"
            "<li><b>Maximum candidates per address</b>: number of output "
            "features written for one address when the service returns "
            "several locations, best matches first.</li>"
            "<li><b>Language</b>: language of the labels returned by the "
            "service.</li>"
            "<li><b>Pause between requests</b>: minimum delay between two "
            "requests, to spread the load on the service.</li>"
            "</ul>"
            "<h3>Added attributes</h3>"
            "<ul>"
            "<li><b>geocode_query</b>: the text sent to the service.</li>"
            "<li><b>geocode_status</b>: <i>matched</i>, <i>unmatched</i>, "
            "<i>empty</i> (no address) or <i>error</i> (request failed, see "
            "<b>geocode_message</b>).</li>"
            "<li><b>geocode_candidates</b>: number of locations returned by "
            "the service; more than one means the address is ambiguous.</li>"
            "<li><b>geocode_candidate</b>: rank of this feature among the "
            "candidates, 1 being the best match.</li>"
            "<li><b>geocode_quality</b>: <i>exact</i> when every word of the "
            "query appears in the location found, <i>fuzzy</i> otherwise. "
            "The service performs a fuzzy search and almost always returns "
            "something, even for typos or unknown addresses: check this "
            "attribute before trusting a result.</li>"
            "<li><b>geocode_label</b>, <b>geocode_detail</b>, "
            "<b>geocode_origin</b>, <b>geocode_feature_id</b>, "
            "<b>geocode_rank</b>, <b>geocode_weight</b>: the location as "
            "returned by the service. For building addresses the feature "
            "identifier is the EGID and EDID of the federal register of "
            "buildings and dwellings.</li>"
            "</ul>"
            "<h3>Fair use</h3>"
            "<p>The service is free of charge but subject to a fair use "
            "policy, about 20 requests per minute on average. Identical "
            "addresses are requested only once. Keep the pause between "
            "requests for large tables and do not run unattended bulk "
            "jobs. Transient failures are retried a few times; the "
            "algorithm stops after several consecutive failures.</p>"
        )

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def inputLayerTypes(self) -> list[int]:
        # Plain tables without geometry are the typical input
        return [Qgis.ProcessingSourceType.Vector]

    def inputParameterDescription(self) -> str:
        return self.tr("Input layer or table")

    def outputName(self) -> str:
        return self.tr("Geocoded")

    def initParameters(self, configuration=None):
        self.addParameter(
            QgsProcessingParameterExpression(
                self.ADDRESS,
                self.tr("Address"),
                parentLayerParameterName=self.inputParameterName(),
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.ORIGINS,
                self.tr("Search in"),
                options=[
                    self.tr("Building addresses"),
                    self.tr("Cadastral parcels"),
                    self.tr("Postal codes"),
                    self.tr("Municipalities"),
                    self.tr("Districts"),
                    self.tr("Cantons"),
                    self.tr("Place names"),
                ],
                allowMultiple=True,
                defaultValue=[0],
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS, self.tr("Output CRS"), defaultValue=self.DEFAULT_CRS
            )
        )
        self.addParameter(
            QgsProcessingParameterExtent(
                self.EXTENT, self.tr("Restrict search to extent"), optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.KEEP_UNMATCHED,
                self.tr("Keep unmatched rows (without geometry)"),
                defaultValue=True,
            )
        )

        max_candidates = QgsProcessingParameterNumber(
            self.MAX_CANDIDATES,
            self.tr("Maximum candidates per address"),
            Qgis.ProcessingNumberParameterType.Integer,
            defaultValue=1,
            minValue=1,
            maxValue=MAX_API_LIMIT,
        )
        language = QgsProcessingParameterEnum(
            self.LANGUAGE,
            self.tr("Language"),
            options=[
                self.tr("Automatic (plugin setting)"),
                "Deutsch",
                "Français",
                "Italiano",
                "Rumantsch",
                "English",
            ],
            defaultValue=0,
        )
        delay = QgsProcessingParameterNumber(
            self.REQUEST_DELAY,
            self.tr("Pause between requests (milliseconds)"),
            Qgis.ProcessingNumberParameterType.Integer,
            defaultValue=100,
            minValue=0,
            maxValue=10000,
        )
        for parameter in (max_candidates, language, delay):
            parameter.setFlags(
                parameter.flags() | Qgis.ProcessingParameterFlag.Advanced
            )
            self.addParameter(parameter)

        self.addOutput(
            QgsProcessingOutputNumber(self.GEOCODED_COUNT, self.tr("Geocoded rows"))
        )
        self.addOutput(
            QgsProcessingOutputNumber(self.UNMATCHED_COUNT, self.tr("Unmatched rows"))
        )
        self.addOutput(
            QgsProcessingOutputNumber(self.ERROR_COUNT, self.tr("Failed rows"))
        )
        self.addOutput(
            QgsProcessingOutputNumber(self.REQUEST_COUNT, self.tr("Requests sent"))
        )

    # ------------------------------------------------------------------
    # Output definition
    # ------------------------------------------------------------------

    @staticmethod
    def appended_fields() -> QgsFields:
        """Fields added to the source fields, in the order they are written."""
        fields = QgsFields()
        fields.append(QgsField(f"{FIELD_PREFIX}query", QMetaType.Type.QString))
        fields.append(QgsField(f"{FIELD_PREFIX}status", QMetaType.Type.QString))
        fields.append(QgsField(f"{FIELD_PREFIX}candidates", QMetaType.Type.Int))
        fields.append(QgsField(f"{FIELD_PREFIX}candidate", QMetaType.Type.Int))
        for field in SwissGeocoder().appendedFields():
            fields.append(field)
        fields.append(QgsField(f"{FIELD_PREFIX}message", QMetaType.Type.QString))
        return fields

    def outputFields(self, inputFields: QgsFields) -> QgsFields:
        return QgsProcessingUtils.combineFields(inputFields, self.appended_fields())

    def outputWkbType(self, inputWkbType):
        return Qgis.WkbType.Point

    def outputCrs(self, inputCrs):
        # The model designer may ask before the algorithm is prepared
        if self._target_crs is not None and self._target_crs.isValid():
            return self._target_crs
        return QgsCoordinateReferenceSystem(self.DEFAULT_CRS)

    def sourceFlags(self):
        return Qgis.ProcessingFeatureSourceFlag.SkipGeometryValidityChecks

    def supportInPlaceEdit(self, layer) -> bool:
        return False

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def prepareAlgorithm(self, parameters, context, feedback) -> bool:
        # Everything that is not thread safe (settings, expression
        # preparation, geocoder construction) happens here, in the main thread
        self._source = self.parameterAsSource(
            parameters, self.inputParameterName(), context
        )
        if self._source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.inputParameterName())
            )

        self._expression = QgsExpression(
            self.parameterAsExpression(parameters, self.ADDRESS, context)
        )
        if self._expression.hasParserError():
            raise QgsProcessingException(
                self.tr("Invalid address expression: {}").format(
                    self._expression.parserErrorString()
                )
            )
        self._expression_context = self.createExpressionContext(
            parameters, context, self._source
        )
        self._expression.prepare(self._expression_context)

        self._target_crs = self.parameterAsCrs(parameters, self.TARGET_CRS, context)
        if not self._target_crs.isValid():
            self._target_crs = QgsCoordinateReferenceSystem(self.DEFAULT_CRS)
        # The service answers in LV95 or LV03 only; ask for LV03 when it is
        # the target so that no transformation is needed, LV95 otherwise
        sr = "21781" if self._target_crs.authid() == "EPSG:21781" else "2056"
        request_crs = QgsCoordinateReferenceSystem(f"EPSG:{sr}")
        self._transform = QgsCoordinateTransform(
            request_crs, self._target_crs, context.transformContext()
        )

        origins = [
            GEOCODE_ORIGINS[index]
            for index in self.parameterAsEnums(parameters, self.ORIGINS, context)
            if 0 <= index < len(GEOCODE_ORIGINS)
        ] or ["address"]
        language_index = self.parameterAsEnum(parameters, self.LANGUAGE, context)
        lang = LANGUAGE_CODES[language_index] or get_language()
        self._max_candidates = max(
            1, self.parameterAsInt(parameters, self.MAX_CANDIDATES, context)
        )
        limit = min(MAX_API_LIMIT, max(self._max_candidates, MIN_REQUEST_LIMIT))
        self._geocoder = SwissGeocoder(origins, sr, lang, limit)

        self._geocoder_context = QgsGeocoderContext(context.transformContext())
        if parameters.get(self.EXTENT) is not None:
            extent = self.parameterAsExtent(
                parameters, self.EXTENT, context, crs=request_crs
            )
            if not extent.isNull():
                self._geocoder_context.setAreaOfInterest(QgsGeometry.fromRect(extent))
                self._geocoder_context.setAreaOfInterestCrs(request_crs)

        self._keep_unmatched = self.parameterAsBoolean(
            parameters, self.KEEP_UNMATCHED, context
        )
        self._delay_s = (
            self.parameterAsInt(parameters, self.REQUEST_DELAY, context) / 1000.0
        )
        self._last_request = None
        self._cache = {}
        self._counts = {
            STATUS_MATCHED: 0,
            STATUS_UNMATCHED: 0,
            STATUS_EMPTY: 0,
            STATUS_ERROR: 0,
            "requests": 0,
            "cache_hits": 0,
        }
        self._consecutive_errors = 0
        self._reported_evaluation_errors = set()
        return True

    def _address(self, feature: QgsFeature, feedback) -> str:
        """Evaluates the address expression for a feature."""
        self._expression_context.setFeature(feature)
        value = self._expression.evaluate(self._expression_context)
        if self._expression.hasEvalError():
            message = self._expression.evalErrorString()
            if message not in self._reported_evaluation_errors:
                self._reported_evaluation_errors.add(message)
                feedback.pushWarning(
                    self.tr("Could not evaluate the address expression: {}").format(
                        message
                    )
                )
            return ""
        if value is None or value == NULL:
            return ""
        return " ".join(str(value).split())

    def _geocode(self, query: str, feedback) -> list[QgsGeocoderResult]:
        """Geocodes a query, reusing previous results for identical queries."""
        key = query.casefold()
        if key in self._cache:
            self._counts["cache_hits"] += 1
            return self._cache[key]

        if self._last_request is not None and self._delay_s > 0:
            elapsed = time.monotonic() - self._last_request
            sleep_cancellable(self._delay_s - elapsed, feedback)
        results = self._geocoder.geocodeString(query, self._geocoder_context, feedback)
        self._counts["requests"] += 1
        self._last_request = time.monotonic()
        self._cache[key] = results
        return results

    def _row(
        self,
        feature: QgsFeature,
        query: str,
        status: str,
        candidates: int | None = None,
        message: str | None = None,
    ) -> QgsFeature:
        """Builds an output feature without geometry."""
        output = QgsFeature()
        attributes = feature.attributes() + [query, status, candidates, None]
        attributes += [None] * len(SwissGeocoder.FIELD_NAMES)
        attributes.append(message)
        output.setAttributes(attributes)
        return output

    def processFeature(self, feature, context, feedback) -> list[QgsFeature]:
        query = self._address(feature, feedback)
        if not tokens(query):
            # Nothing to search for, e.g. concatenated empty fields giving ", "
            self._counts[STATUS_EMPTY] += 1
            if not self._keep_unmatched:
                return []
            return [self._row(feature, query, STATUS_EMPTY)]

        results = self._geocode(query, feedback)
        if feedback.isCanceled():
            return []

        if results and not results[0].isValid():
            self._counts[STATUS_ERROR] += 1
            self._consecutive_errors += 1
            message = results[0].error()
            feedback.pushWarning(
                self.tr("Request failed for '{}': {}").format(query, message)
            )
            if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                raise QgsProcessingException(
                    self.tr(
                        "{} consecutive requests failed, giving up. Last error: {}"
                    ).format(self._consecutive_errors, message)
                )
            # Failed rows are always written so that they can be told apart
            # from rows without any match
            return [self._row(feature, query, STATUS_ERROR, message=message)]
        self._consecutive_errors = 0

        if not results:
            self._counts[STATUS_UNMATCHED] += 1
            if not self._keep_unmatched:
                return []
            return [self._row(feature, query, STATUS_UNMATCHED, candidates=0)]

        self._counts[STATUS_MATCHED] += 1
        outputs = []
        for rank, result in enumerate(results[: self._max_candidates], start=1):
            geometry = QgsGeometry(result.geometry())
            try:
                geometry.transform(self._transform)
            except QgsCsException as e:
                self._counts[STATUS_ERROR] += 1
                outputs.append(
                    self._row(feature, query, STATUS_ERROR, len(results), str(e))
                )
                continue
            additional = result.additionalAttributes()
            output = QgsFeature()
            output.setGeometry(geometry)
            output.setAttributes(
                feature.attributes()
                + [query, STATUS_MATCHED, len(results), rank]
                + [additional.get(name) for name in SwissGeocoder.FIELD_NAMES]
                + [None]
            )
            outputs.append(output)
        return outputs

    def processAlgorithm(self, parameters, context, feedback) -> dict:
        results = super().processAlgorithm(parameters, context, feedback)
        feedback.pushInfo(
            self.tr(
                "Geocoded rows: {}, unmatched rows: {}, empty rows: {}, "
                "failed rows: {}. Requests sent: {}, identical addresses "
                "reused: {}."
            ).format(
                self._counts[STATUS_MATCHED],
                self._counts[STATUS_UNMATCHED],
                self._counts[STATUS_EMPTY],
                self._counts[STATUS_ERROR],
                self._counts["requests"],
                self._counts["cache_hits"],
            )
        )
        results.update(
            {
                self.GEOCODED_COUNT: self._counts[STATUS_MATCHED],
                self.UNMATCHED_COUNT: self._counts[STATUS_UNMATCHED],
                self.ERROR_COUNT: self._counts[STATUS_ERROR],
                self.REQUEST_COUNT: self._counts["requests"],
            }
        )
        return results
