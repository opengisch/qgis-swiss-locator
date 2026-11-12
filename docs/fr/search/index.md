# Recherche

L'extension ajoute six recherches à la barre de localisation de QGIS. Chacune a
un préfixe pour la lancer seule.

| Recherche | Préfixe | Trouve | Source |
|-----------|---------|--------|--------|
| [Lieux](locations.md) | `chs` | cantons, communes, districts, codes postaux, adresses, parcelles, noms de la carte nationale | geo.admin.ch |
| [Couches](layers.md) | `chl` | couches WMS | geo.admin.ch, services cantonaux référencés par opendata.swiss |
| [Couches WMTS](wmts.md) | `chw` | couches WMTS | geo.admin.ch |
| [Fonds de plan](base-maps.md) | `chb` | fonds de plan en tuiles vectorielles | swisstopo |
| [Objets](features.md) | `chf` | objets des couches du géoportail | geo.admin.ch |
| [Téléchargement de fichiers](downloads.md) | `chd` | fichiers du catalogue de données | data.geo.admin.ch (STAC) |

Le nombre de résultats et l'ordre des recherches peuvent être définis dans la
[configuration](../configuration.md).
