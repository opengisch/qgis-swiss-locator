from qgis.PyQt.QtWidgets import QCheckBox, QVBoxLayout, QWidget

from ..swissgeodownloader.api.catalogs import (
    LOCAL_STAC_CATALOGS,
    ApiBaselStadt,
    ApiViageo,
)


class LocalCatalogsWidget(QWidget):
    """A check box per local STAC catalog, to choose those to search"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        titles = {
            ApiViageo.CATALOG_ID: self.tr(
                "viageo.ch (canton of Vaud and its municipalities)"
            ),
            ApiBaselStadt.CATALOG_ID: self.tr("Basel-Stadt (geo.bs.ch)"),
        }
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.check_boxes: dict[str, QCheckBox] = {}
        for catalog in LOCAL_STAC_CATALOGS:
            check_box = QCheckBox(titles[catalog.CATALOG_ID], self)
            layout.addWidget(check_box)
            self.check_boxes[catalog.CATALOG_ID] = check_box

    def catalog_ids(self) -> list[str]:
        return [
            catalog_id
            for catalog_id, check_box in self.check_boxes.items()
            if check_box.isChecked()
        ]

    def set_catalog_ids(self, catalog_ids: list[str]):
        for catalog_id, check_box in self.check_boxes.items():
            check_box.setChecked(catalog_id in catalog_ids)
