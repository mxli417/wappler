"""Sphinx configuration; autodoc imports the package without loading secrets."""

project = "Wappler"
author = "Wappler contributors"
release = "0.0.1"
extensions = ["sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx.ext.viewcode"]
autodoc_member_order = "bysource"
autodoc_typehints = "description"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_theme = "alabaster"
