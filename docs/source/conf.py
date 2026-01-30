# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import re
import sys

# Add the project root directory to the Python path for autodoc
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Read version directly from __init__.py file to avoid import caching issues
# with sphinx-multiversion (which builds multiple versions in sequence)
def get_version():
    init_path = os.path.join(project_root, 'vista', '__init__.py')
    with open(init_path, 'r') as f:
        content = f.read()
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if match:
        return match.group(1)
    raise RuntimeError("Unable to find version string in vista/__init__.py")

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'VISTA'
copyright = '2025, Stephen Hartzell'
author = 'Stephen Hartzell'
release = get_version()
version = get_version()

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',           # Auto-generate documentation from docstrings
    'sphinx.ext.autosummary',       # Generate summary tables for modules/classes
    'sphinx.ext.napoleon',          # Support for NumPy and Google style docstrings
    'sphinx.ext.viewcode',          # Add links to highlighted source code
    'sphinx.ext.intersphinx',       # Link to other project's documentation
    'sphinx.ext.mathjax',           # Math support
    'sphinx.ext.todo',              # Todo notes
    'sphinx.ext.coverage',          # Coverage checker
    'sphinx.ext.githubpages',       # Create .nojekyll file for GitHub Pages
]

# Napoleon settings for NumPy-style docstrings
napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# Autosummary settings
autosummary_generate = True
autosummary_imported_members = False

# Autodoc settings
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__'
}
autodoc_typehints = 'description'
autodoc_typehints_description_target = 'documented'

# Mock imports for packages that can't be imported in CI environment
# (e.g., PyQt6 requires graphics libraries like libEGL.so.1)
autodoc_mock_imports = [
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtOpenGLWidgets',
    'pyqtgraph',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = []

# The suffix(es) of source filenames.
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']

# Furo theme options
html_theme_options = {
    "sidebar_hide_name": False,
    "light_css_variables": {
        "color-brand-primary": "#2b5b84",
        "color-brand-content": "#2b5b84",
    },
    "dark_css_variables": {
        "color-brand-primary": "#5b9bd5",
        "color-brand-content": "#5b9bd5",
    },
    "source_repository": "https://github.com/awetomaton/VISTA",
    "source_branch": "main",
    "source_directory": "docs/source/",
}

html_title = f"VISTA {version}"
html_short_title = "VISTA"
html_logo = None  # Add a logo path here if you have one
html_favicon = None  # Add a favicon path here if you have one

# Add any paths that contain custom static files (such as style sheets)
html_static_path = ['_static']

# Custom CSS and JavaScript files
html_css_files = [
    'custom.css',
]

html_js_files = [
    'version-selector.js',
]

# Context for templates (including version information for sphinx-multiversion)
# Note: sphinx-multiversion automatically provides 'versions' and 'current_version'
# template variables - do NOT override them here or the version selector won't work
html_context = {
    'display_version': version,
}

# If true, "Created using Sphinx" is shown in the HTML footer. Default is True.
html_show_sphinx = True

# If true, "(C) Copyright ..." is shown in the HTML footer. Default is True.
html_show_copyright = True

# Output file base name for HTML help builder.
htmlhelp_basename = 'VISTAdoc'

# -- Options for Intersphinx extension ---------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#configuration

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
    'scipy': ('https://docs.scipy.org/doc/scipy/', None),
    'pandas': ('https://pandas.pydata.org/docs/', None),
    'matplotlib': ('https://matplotlib.org/stable/', None),
    'pyqt6': ('https://www.riverbankcomputing.com/static/Docs/PyQt6/', None),
}

# -- Options for todo extension ----------------------------------------------

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

# -- Options for sphinx-multiversion -----------------------------------------

# Whitelist pattern for tags (only tags that match this pattern will be built)
# Matches tags like: 1.0.0, 1.7.0, 2.0.0 (without 'v' prefix)
# Uses negative lookahead to exclude versions 1.7.0 and 1.8.0
smv_tag_whitelist = r'^(?!1\.[78]\.0$)\d+\.\d+\.\d+$'

# Whitelist pattern for branches (empty pattern to exclude all branches)
smv_branch_whitelist = r'$^'

# Whitelist pattern for remotes
smv_remote_whitelist = r'^origin$'

# Pattern for released versions
smv_released_pattern = r'^refs/tags/.*$'

# Format for version output
smv_outputdir_format = '{ref.name}'

# Prefer tags over branches
smv_prefer_remote_refs = False
