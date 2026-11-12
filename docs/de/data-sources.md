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
