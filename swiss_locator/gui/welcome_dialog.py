from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .local_catalogs_widget import LocalCatalogsWidget
from ..core.settings import Settings
from ..swissgeodownloader.api.catalogs import ApiGeodienste

# Bump it when the dialog asks something new: it then shows again to everyone
WELCOME_DIALOG_VERSION = 2

# The local catalogs on by default, by the version of the dialog that brought
#  them: turned on for those who have not seen that version yet, the dialog
#  shows them checked, to uncheck
CATALOGS_ON_BY_DEFAULT = {ApiGeodienste.CATALOG_ID: 2}


def unseen_catalogs_on_by_default() -> list[str]:
    """The catalogs on by default brought by a version of the dialog the user
    has not seen"""
    seen = Settings().welcome_dialog_version.value()
    return [
        catalog_id
        for catalog_id, version in CATALOGS_ON_BY_DEFAULT.items()
        if version > seen
    ]


def turn_on_default_catalogs():
    """Turn on the catalogs on by default that the user was not asked about"""
    settings = Settings()
    catalog_ids = settings.stac_local_catalogs.value()
    new = [c for c in unseen_catalogs_on_by_default() if c not in catalog_ids]
    if new:
        settings.stac_local_catalogs.setValue(catalog_ids + new)


class WelcomeDialog(QDialog):
    """Shown at the first launch of the plugin, and again after each bump of
    WELCOME_DIALOG_VERSION. It asks which local catalogs to search."""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.settings = Settings()
        # Set when closed by the Open Settings button
        self.open_settings = False

        self.setWindowTitle(self.tr("Swiss Locator"))
        layout = QVBoxLayout(self)

        title = QLabel(self.tr("Welcome to Swiss Locator"), self)
        font = title.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.3)
        title.setFont(font)
        layout.addWidget(title)
        intro = QLabel(
            self.tr(
                "Search the geodata of Switzerland from the locator bar of QGIS: "
                "places, layers, features and files to download."
            ),
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        catalogs = QGroupBox(self.tr("Local data catalogs"), self)
        catalogs_layout = QVBoxLayout(catalogs)
        catalogs_intro = QLabel(
            self.tr(
                "On top of the files of the Swiss Geoportal, search and download "
                "those of local catalogs:"
            ),
            catalogs,
        )
        catalogs_intro.setWordWrap(True)
        catalogs_layout.addWidget(catalogs_intro)
        self.local_catalogs = LocalCatalogsWidget(catalogs)
        self.local_catalogs.set_catalog_ids(self.settings.stac_local_catalogs.value())
        if self.settings.welcome_dialog_version.value() > 0:
            # Seen before: what this version brings is in bold
            self.local_catalogs.set_bold(unseen_catalogs_on_by_default())
        catalogs_layout.addWidget(self.local_catalogs)
        layout.addWidget(catalogs)

        hint = QLabel(
            self.tr(
                "To change these choices later, open the settings of the plugin "
                "from Settings ▸ Options ▸ Locator."
            ),
            self,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        open_settings = buttons.addButton(
            self.tr("Open Settings"), QDialogButtonBox.ButtonRole.ActionRole
        )
        open_settings.clicked.connect(self.accept_and_open_settings)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @staticmethod
    def is_due() -> bool:
        """Whether the user has not seen this version of the dialog yet"""
        return Settings().welcome_dialog_version.value() < WELCOME_DIALOG_VERSION

    def accept_and_open_settings(self):
        self.open_settings = True
        self.accept()

    def accept(self):
        self.settings.stac_local_catalogs.setValue(self.local_catalogs.catalog_ids())
        super().accept()

    def done(self, result: int):
        # Closed in any way, it was seen: it does not show again
        self.settings.welcome_dialog_version.setValue(WELCOME_DIALOG_VERSION)
        super().done(result)
