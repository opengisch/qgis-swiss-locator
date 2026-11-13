# Sources des données

L'extension interroge les services du géoportail fédéral, d'opendata.swiss et
des cantons. Elle nécessite une connexion Internet.

| Service | Utilisé par |
|---------|-------------|
| [api3.geo.admin.ch](https://api3.geo.admin.ch) | lieux, géocodage, couches, objets, profil altimétrique |
| [wms.geo.admin.ch](https://wms.geo.admin.ch) | couches |
| [wmts.geo.admin.ch](https://wmts.geo.admin.ch) | couches WMTS |
| [vectortiles.geo.admin.ch](https://vectortiles.geo.admin.ch) | fonds de plan |
| [data.geo.admin.ch](https://data.geo.admin.ch) | téléchargement de données |
| [viageo.ch](https://viageo.ch) | téléchargement de données |
| [opendata.swiss](https://opendata.swiss) et les services WMS qu'il référence | couches |
| [opengisch.github.io/qgis-swiss-locator](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json) | couches, objets |

Les données appartiennent à leurs producteurs : consultez leurs conditions
d'utilisation avant de les publier.

## Les catalogues de données (STAC)

Le [téléchargement de données](downloads.md) puise dans deux catalogues de
données : celui du géoportail fédéral, [data.geo.admin.ch](https://data.geo.admin.ch),
et [viageo.ch](https://viageo.ch), qui publie les géodonnées des cantons et des
communes. Tous deux suivent le standard STAC (SpatioTemporal Asset Catalog) et
organisent les données en :

- **collections**, les jeux de données, comme swissALTI3D ;
- **items**, les parties d'un jeu de données dans l'espace ou le temps, comme
  une tuile d'un kilomètre carré à une date ;
- **assets**, les fichiers d'un item, par format, résolution et système de
  coordonnées.

Au démarrage de QGIS, l'extension télécharge la liste des collections de chaque
catalogue, en arrière-plan. Les titres et descriptions de data.geo.admin.ch
dans la langue de l'extension viennent du catalogue de métadonnées
[geocat.ch](https://www.geocat.ch) ; ceux de viageo.ch sont en français. Une
recherche cherche le texte dans les titres et identifiants de ces listes, sans
requête. Pour chaque collection trouvée, l'extension demande ensuite ses
premiers fichiers : s'ils sont peu nombreux, ils sont listés ; sinon, la
collection ouvre le panneau de filtre.

Le panneau de filtre demande au catalogue les items de l'étendue choisie, et
liste leurs assets par type de fichier, résolution, date et système de
coordonnées. Il vient de l'extension
[Swiss Geo Downloader](https://pimoll.github.io/swissgeodownloader/), de
Patricia Moll.

Un Cloud Optimized GeoTIFF ou Point Cloud ajouté en *streamed* reste sur le
serveur de son catalogue : QGIS lit par le réseau les parties qu'il affiche.

## Fichiers publiés par l'extension

Deux recherches s'appuient sur des listes que l'extension prépare, car les
consulter en ligne serait trop lent :

- les couches de map.geo.admin.ch dont les objets peuvent être recherchés, pour
  la [recherche d'objets](search/features.md);
- les couches des services WMS référencés par opendata.swiss, pour la recherche
  de [couches WMS](layers/wms.md).

Un workflow GitHub du dépôt de l'extension les génère régulièrement et les publie sur
[GitHub Pages](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json),
à côté de cette documentation. QGIS vérifie au plus une fois par jour, en
arrière-plan, s'il en existe une nouvelle version, et en garde une copie dans
son profil. Chaque version de l'extension en contient aussi une copie, utilisée
quand GitHub n'est pas joignable.

Un service d'opendata.swiss qui ne répond pas garde ses couches dans la liste
pendant 30 jours au plus.
