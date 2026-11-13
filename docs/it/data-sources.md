# Fonti dei dati

Il plugin interroga i servizi del geoportale federale, di opendata.swiss e dei
cantoni. Richiede una connessione a Internet.

| Servizio | Usato da |
|----------|----------|
| [api3.geo.admin.ch](https://api3.geo.admin.ch) | località, geocodifica, layer, oggetti, profilo altimetrico |
| [wms.geo.admin.ch](https://wms.geo.admin.ch) | layer |
| [wmts.geo.admin.ch](https://wmts.geo.admin.ch) | layer WMTS |
| [vectortiles.geo.admin.ch](https://vectortiles.geo.admin.ch) | mappe di base |
| [data.geo.admin.ch](https://data.geo.admin.ch) | download di dati |
| [viageo.ch](https://viageo.ch) | download di dati |
| [opendata.swiss](https://opendata.swiss) e i servizi WMS che vi sono referenziati | layer |
| [opengisch.github.io/qgis-swiss-locator](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json) | layer, oggetti |

I dati appartengono a chi li pubblica: prima di pubblicarli a propria volta,
verificarne le condizioni d'uso.

## I cataloghi dei dati (STAC)

Il [download di dati](downloads.md) attinge a due cataloghi di dati: quello del
geoportale federale, [data.geo.admin.ch](https://data.geo.admin.ch), e
[viageo.ch](https://viageo.ch), che pubblica i geodati di cantoni e comuni.
Entrambi seguono lo standard STAC (SpatioTemporal Asset Catalog) e organizzano
i dati in:

- **collection**, i set di dati, come swissALTI3D;
- **item**, le parti di un set di dati nello spazio o nel tempo, come un
  riquadro di un chilometro quadrato a una data;
- **asset**, i file di un item, per formato, risoluzione e sistema di
  coordinate.

All'avvio di QGIS, il plugin scarica l'elenco delle collection di ogni catalogo
in background. I titoli e le descrizioni di data.geo.admin.ch nella lingua del
plugin provengono dal catalogo di metadati [geocat.ch](https://www.geocat.ch);
quelli di viageo.ch sono in francese. Una ricerca cerca il testo nei titoli e
negli identificativi di questi elenchi, senza richieste. Per ogni
collection trovata, il plugin chiede poi i suoi primi file: se sono pochi,
vengono elencati; altrimenti la collection apre il pannello di filtro.

Il pannello di filtro chiede al catalogo gli item dell'estensione scelta ed
elenca i loro asset per tipo di file, risoluzione, data e sistema di
coordinate. Proviene dal plugin
[Swiss Geo Downloader](https://pimoll.github.io/swissgeodownloader/) di
Patricia Moll.

Un Cloud Optimized GeoTIFF o Point Cloud aggiunto come *streamed* resta sul
server del suo catalogo: QGIS legge via rete le parti che visualizza.

## File pubblicati dal plugin

Due ricerche si basano su elenchi preparati dal plugin, poiché una ricerca
online sarebbe troppo lenta:

- i layer di map.geo.admin.ch con oggetti ricercabili, per la
  [ricerca di oggetti](search/features.md);
- i layer dei servizi WMS referenziati da opendata.swiss, per la ricerca di
  [layer WMS](layers/wms.md).

Un workflow GitHub del repository del plugin li genera regolarmente e li pubblica su
[GitHub Pages](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json),
accanto a questa documentazione. QGIS verifica la presenza di una nuova versione
al massimo una volta al giorno, in background, e ne conserva una copia nel suo
profilo. Ogni versione del plugin ne include inoltre una copia, usata quando
GitHub non è raggiungibile.

Un servizio di opendata.swiss che non risponde mantiene i suoi layer
nell'elenco per un massimo di 30 giorni.
