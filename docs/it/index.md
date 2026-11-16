# Swiss Locator

Swiss Locator è il coltellino svizzero di QGIS, con l'obiettivo principale di
portare in QGIS le soluzioni offerte da swisstopo e da alcuni attori cantonali.

Digitare nella
[barra di localizzazione](https://docs.qgis.org/3.44/it/docs/user_manual/introduction/qgis_gui.html#locator-bar)
di QGIS, come su [map.geo.admin.ch](https://map.geo.admin.ch), per trovare:

- **luoghi**: cantoni, comuni, distretti, numeri postali d'avviamento,
  indirizzi, particelle e i nomi della carta nazionale;
- **layer** del geoportale federale e dei servizi cantonali referenziati da
  [opendata.swiss](https://opendata.swiss), come WMS o WMTS;
- **mappe di base** di swisstopo, in tile vettoriali;
- **oggetti** dei layer del geoportale, come una fermata dei trasporti pubblici
  o una capanna alpina;
- **file da scaricare** dai cataloghi dei dati del geoportale, di
  [viageo.ch](https://viageo.ch) per cantoni e comuni, e di
  [Basilea Città](https://www.geo.bs.ch) (STAC).

Il plugin disegna inoltre il terreno di swissALTI3D nei **profili altimetrici**
di QGIS, e [geocodifica](geocoding.md) **tabelle di indirizzi** con Processing.

In un minuto: una mappa di base, un luogo e un profilo altimetrico, poi i dati
lidar di swissSURFACE3D, scelti sulla carta, scaricati e mostrati in 3D.

<video controls muted playsinline preload="none" width="100%"
       poster="assets/images/demo.jpg"
       src="https://github.com/user-attachments/assets/e1571d17-ff0a-41a3-ae48-93357aeb86c0"></video>

## Per iniziare

1. In QGIS, aprire **Plugins ▸ Gestisci ed Installa Plugin...**, cercare
   *Swiss Locator* e installarlo. Richiede QGIS 3.44 o successivo.
2. Fare clic nella barra di localizzazione, in basso a sinistra della finestra,
   oppure premere ++ctrl+k++.
3. Digitare un luogo, ad esempio `Lausanne`, e fare doppio clic su un risultato.

[Primi passi](getting-started.md) spiega la barra di localizzazione. Poi è
possibile [cercare luoghi e oggetti](search/index.md),
[aggiungere layer](layers/index.md) o [scaricare dati](downloads/swisstopo.md).

## Informazioni

Il plugin è sviluppato da [OPENGIS.ch](https://opengis.ch) con il sostegno del
[gruppo svizzero degli utenti QGIS](https://qgis.ch). Il codice si trova su
[GitHub](https://github.com/opengisch/qgis-swiss-locator), dove è possibile
segnalare problemi.
