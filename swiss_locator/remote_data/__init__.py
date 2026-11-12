"""
Data files generated nightly by CI and published on GitHub Pages.

- spec.py: what is published and in which format. Standard library only, so
  the generators in scripts/ share it with the plugin.
- remote_data_file.py: how the plugin loads these files, keeps a local cache
  and updates it.

This package must not import QGIS at package level, see spec.py.
"""
