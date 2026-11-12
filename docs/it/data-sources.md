# Fonti dei dati

Il plugin interroga i servizi del geoportale federale, di opendata.swiss e dei
cantoni. Richiede una connessione a Internet.

| Servizio | Usato da |
|----------|----------|
| [api3.geo.admin.ch](https://api3.geo.admin.ch) | località, layer, oggetti, profilo altimetrico |
| [wms.geo.admin.ch](https://wms.geo.admin.ch) | layer |
| [wmts.geo.admin.ch](https://wmts.geo.admin.ch) | layer WMTS |
| [vectortiles.geo.admin.ch](https://vectortiles.geo.admin.ch) | mappe di base |
| [data.geo.admin.ch](https://data.geo.admin.ch) | download di file |
| [opendata.swiss](https://opendata.swiss) e i servizi WMS che vi sono referenziati | layer |
| [opengisch.github.io/qgis-swiss-locator](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json) | layer, oggetti |

I dati appartengono a chi li pubblica: prima di pubblicarli a propria volta,
verificarne le condizioni d'uso.

## File pubblicati dal plugin

Due ricerche si basano su elenchi preparati dal plugin, poiché una ricerca
online sarebbe troppo lenta:

- i layer di map.geo.admin.ch con oggetti ricercabili, per la
  [ricerca di oggetti](search/features.md);
- i layer dei servizi WMS referenziati da opendata.swiss, per la ricerca di
  [layer](search/layers.md).

Un workflow GitHub del repository del plugin li genera regolarmente e li pubblica su
[GitHub Pages](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json),
accanto a questa documentazione. QGIS verifica la presenza di una nuova versione
al massimo una volta al giorno, in background, e ne conserva una copia nel suo
profilo. Ogni versione del plugin ne include inoltre una copia, usata quando
GitHub non è raggiungibile.

Un servizio di opendata.swiss che non risponde mantiene i suoi layer
nell'elenco per un massimo di 30 giorni.
