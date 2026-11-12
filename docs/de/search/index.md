# Suche

Das Plugin fügt der Suchleiste von QGIS sechs Suchen hinzu. Jede hat ein
Präfix, um sie einzeln auszuführen.

| Suche | Präfix | Findet | Quelle |
|-------|--------|--------|--------|
| [Orte](locations.md) | `chs` | Kantone, Gemeinden, Bezirke, Postleitzahlen, Adressen, Parzellen, Namen der Landeskarte | geo.admin.ch |
| [Kartenlayer](layers.md) | `chl` | WMS-Layer | geo.admin.ch, auf opendata.swiss referenzierte kantonale Dienste |
| [WMTS-Layer](wmts.md) | `chw` | WMTS-Layer | geo.admin.ch |
| [Basiskarten](base-maps.md) | `chb` | Basiskarten als Vektorkacheln | swisstopo |
| [Objekte](features.md) | `chf` | Objekte der Layer des Geoportals | geo.admin.ch |
| [Datei-Download](downloads.md) | `chd` | Dateien des Datenkatalogs | data.geo.admin.ch (STAC) |

Die Anzahl der Resultate und die Reihenfolge der Suchen lassen sich in der
[Konfiguration](../configuration.md) einstellen.
