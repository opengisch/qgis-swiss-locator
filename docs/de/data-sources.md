# Datenquellen

Das Plugin fragt die Dienste des Geoportals des Bundes, von opendata.swiss und
der Kantone ab. Es benötigt eine Internetverbindung.

| Dienst | Verwendet von |
|--------|---------------|
| [api3.geo.admin.ch](https://api3.geo.admin.ch) | Orte, Kartenlayer, Objekte, Höhenprofil |
| [wms.geo.admin.ch](https://wms.geo.admin.ch) | Kartenlayer |
| [wmts.geo.admin.ch](https://wmts.geo.admin.ch) | WMTS-Layer |
| [vectortiles.geo.admin.ch](https://vectortiles.geo.admin.ch) | Basiskarten |
| [data.geo.admin.ch](https://data.geo.admin.ch) | Datei-Download |
| [opendata.swiss](https://opendata.swiss) und die dort referenzierten WMS-Dienste | Kartenlayer |
| [opengisch.github.io/qgis-swiss-locator](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json) | Kartenlayer, Objekte |

Die Daten gehören ihren Herausgebern: Prüfen Sie deren Nutzungsbedingungen,
bevor Sie die Daten veröffentlichen.

## Der Datenkatalog (STAC)

Der [Datei-Download](search/downloads.md) greift auf den Datenkatalog des
Geoportals des Bundes zu, [data.geo.admin.ch](https://data.geo.admin.ch). Er
folgt dem Standard STAC (SpatioTemporal Asset Catalog) und gliedert die Daten
in:

- **Collections**, die Datensätze, etwa swissALTI3D;
- **Items**, die Teile eines Datensatzes in Raum oder Zeit, etwa eine Kachel
  von einem Quadratkilometer zu einem Zeitstand;
- **Assets**, die Dateien eines Items, nach Format, Auflösung und
  Koordinatensystem.

Beim Start von QGIS lädt das Plugin die Liste der Collections im Hintergrund
herunter. Ihre Titel und Beschreibungen in der Sprache des Plugins stammen aus
dem Metadatenkatalog [geocat.ch](https://www.geocat.ch). Eine Suche sucht den
Text in den Titeln und Kennungen dieser Liste, ohne Anfrage. Für jede gefundene
Collection fragt das Plugin dann ihre ersten Dateien ab: Sind es wenige, werden
sie aufgelistet; sonst öffnet die Collection das Filterfenster.

Das Filterfenster fragt beim Katalog die Items der gewählten Ausdehnung ab und
listet ihre Assets nach Dateityp, Auflösung, Zeitstand und Koordinatensystem
auf. Es stammt aus dem Plugin
[Swiss Geo Downloader](https://pimoll.github.io/swissgeodownloader/) von
Patricia Moll.

Ein als *gestreamt* hinzugefügtes Cloud Optimized GeoTIFF bleibt auf
data.geo.admin.ch: QGIS liest die angezeigten Teile über das Netzwerk.

## Vom Plugin veröffentlichte Dateien

Zwei Suchen stützen sich auf Listen, die das Plugin vorbereitet, da es zu
langsam wäre, sie online zu durchsuchen:

- die Layer von map.geo.admin.ch, deren Objekte durchsuchbar sind, für die
  [Objektsuche](search/features.md);
- die Layer der auf opendata.swiss referenzierten WMS-Dienste, für die Suche
  nach [Kartenlayer](search/layers.md).

Ein GitHub-Workflow des Repositorys des Plugins erzeugt sie regelmässig und veröffentlicht sie auf
[GitHub Pages](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json),
neben dieser Dokumentation. QGIS prüft höchstens einmal täglich im Hintergrund,
ob eine neue Version vorliegt, und bewahrt eine Kopie in seinem Profil auf.
Jede Version des Plugins enthält zudem eine Kopie, die verwendet wird, wenn
GitHub nicht erreichbar ist.

Ein auf opendata.swiss referenzierter Dienst, der nicht antwortet, behält seine
Layer bis zu 30 Tage in der Liste.
