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

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.analysis import QgsBatchGeocodeAlgorithm
from qgis.core import (
    NULL,
    Qgis,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterNumber,
)

from swiss_locator import PLUGIN_PATH
from swiss_locator.core.geocoder.swiss_geocoder import (
    GEOCODE_ORIGINS,
    MAX_CONSECUTIVE_ERRORS,
    MIN_REQUEST_LIMIT,
    SwissGeocoder,
)
from swiss_locator.core.language import get_language

# Index 0 is "automatic": the language configured in the plugin settings
LANGUAGE_CODES = (None, "de", "fr", "it", "rm", "en")

# Spatial references offered for the output, in the order of the CRS enum
SWISS_SR = ("2056", "21781")


class GeocodeAddressesAlgorithm(QgsBatchGeocodeAlgorithm):
    """
    Geocodes a table of addresses with the geo.admin.ch search service and
    writes a point layer keeping the source attributes.

    The batch logic (address field, one output feature per row, appended
    attributes, reprojection into the input CRS) comes from QGIS, the
    service specific options are configured on the geocoder.
    """

    ORIGINS = "ORIGINS"
    CRS = "CRS"
    EXTENT = "EXTENT"
    LANGUAGE = "LANGUAGE"
    REQUEST_DELAY = "REQUEST_DELAY"

    def __init__(self):
        # The base class keeps a pointer to the geocoder without owning it:
        # the instance must outlive the algorithm, hence the attribute
        self._geocoder = SwissGeocoder()
        super().__init__(self._geocoder)
        self._address_field = ""
        self._in_place = False

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
        return self.tr("Geocode addresses")

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
            "attributes described below. Rows without any match are kept "
            "without geometry so that no source row is lost.</p>"
            "<h3>Parameters</h3>"
            "<ul>"
            "<li><b>Address field</b>: the column holding the full address, "
            "e.g. <i>Seftigenstrasse 264, 3084 Wabern</i>. Build it with the "
            "field calculator when the address is split over several "
            "columns.</li>"
            "<li><b>Search in</b>: the kinds of locations to search for. "
            "Building addresses are the default; cadastral parcels, postal "
            "codes, municipalities, districts, cantons and place names can "
            "be added.</li>"
            "<li><b>Coordinate reference system</b>: CRS of the output when "
            "the input is a table without geometry. When the input is a "
            "layer, the output keeps its CRS.</li>"
            "<li><b>Restrict search to extent</b>: when set, only locations "
            "within this extent are returned.</li>"
            "<li><b>Language</b>: language of the labels returned by the "
            "service.</li>"
            "<li><b>Pause between requests</b>: minimum delay between two "
            "requests, to spread the load on the service.</li>"
            "</ul>"
            "<h3>Added attributes</h3>"
            "<ul>"
            "<li><b>geocode_quality</b>: <i>exact</i> when every word of the "
            "address appears in the location found, <i>fuzzy</i> otherwise. "
            "The service performs a fuzzy search and almost always returns "
            "something, even for typos or unknown addresses: check this "
            "attribute before trusting a result.</li>"
            "<li><b>geocode_candidates</b>: number of locations returned by "
            "the service; more than one means the address is ambiguous, the "
            "best match is written.</li>"
            "<li><b>geocode_label</b>, <b>geocode_detail</b>, "
            "<b>geocode_origin</b>, <b>geocode_feature_id</b>, "
            "<b>geocode_rank</b>, <b>geocode_weight</b>: the location as "
            "returned by the service. For building addresses the feature "
            "identifier is the EGID and EDID of the federal register of "
            "buildings and dwellings.</li>"
            "</ul>"
            "<p>The attributes are empty when no location was found or when "
            "the request failed. The algorithm can also edit a point layer in "
            "place.</p>"
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

    def initParameters(self, configuration=None):
        configuration = configuration or {}
        self._in_place = bool(configuration.get("IN_PLACE", False))
        # Adds the address field parameter
        super().initParameters(configuration)

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
            QgsProcessingParameterEnum(
                self.CRS,
                self.tr("Coordinate reference system (tables without geometry)"),
                options=["LV95 (EPSG:2056)", "LV03 (EPSG:21781)"],
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterExtent(
                self.EXTENT, self.tr("Restrict search to extent"), optional=True
            )
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
        for parameter in (language, delay):
            parameter.setFlags(
                parameter.flags() | Qgis.ProcessingParameterFlag.Advanced
            )
            self.addParameter(parameter)

    def outputCrs(self, inputCrs):
        # The base class records the input CRS to reproject the results into
        # it; a table without geometry has none, the results then stay in
        # the CRS of the geocoder
        crs = super().outputCrs(inputCrs)
        return crs if crs.isValid() else self._geocoder.crs

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def prepareAlgorithm(self, parameters, context, feedback) -> bool:
        super().prepareAlgorithm(parameters, context, feedback)
        self._address_field = self.parameterAsString(parameters, "FIELD", context)

        origins = [
            GEOCODE_ORIGINS[index]
            for index in self.parameterAsEnums(parameters, self.ORIGINS, context)
            if 0 <= index < len(GEOCODE_ORIGINS)
        ] or ["address"]
        sr = SWISS_SR[self.parameterAsEnum(parameters, self.CRS, context)]
        language_index = self.parameterAsEnum(parameters, self.LANGUAGE, context)
        lang = LANGUAGE_CODES[language_index] or get_language()
        delay_s = self.parameterAsInt(parameters, self.REQUEST_DELAY, context) / 1000.0

        # The geocoder is configured, not rebuilt, because the base class
        # keeps a pointer to the instance given at construction
        self._geocoder.configure(
            origins=origins,
            sr=sr,
            lang=lang,
            limit=MIN_REQUEST_LIMIT,
            max_results=1,
            delay_s=delay_s,
        )
        if parameters.get(self.EXTENT) is not None:
            extent = self.parameterAsExtent(
                parameters, self.EXTENT, context, crs=self._geocoder.crs
            )
            if not extent.isNull():
                self._geocoder.bbox = extent
        return True

    def processFeature(self, feature, context, feedback):
        address = feature.attribute(self._address_field)
        if address is None or address == NULL:
            # The base class would search for the string "0", do what it
            # does for an empty address instead
            feedback.pushWarning(
                self.tr("Empty address field for feature {}").format(feature.id())
            )
            if not self._in_place:
                feature.padAttributes(len(SwissGeocoder.FIELD_NAMES))
            return [feature]

        outputs = super().processFeature(feature, context, feedback)
        if self._geocoder.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            raise QgsProcessingException(
                self.tr("{} consecutive requests failed, giving up.").format(
                    self._geocoder.consecutive_errors
                )
            )
        return outputs

    def processAlgorithm(self, parameters, context, feedback) -> dict:
        results = super().processAlgorithm(parameters, context, feedback)
        feedback.pushInfo(
            self.tr("Requests sent: {}, identical addresses reused: {}.").format(
                self._geocoder.requests, self._geocoder.cache_hits
            )
        )
        return results
