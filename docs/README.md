# VISTA Documentation

This directory contains the Sphinx documentation for VISTA.

## Documentation Stack

- **Sphinx**: Documentation generator
- **Furo**: Modern, clean theme
- **sphinx-multiversion**: Multi-version documentation support
- **Napoleon**: NumPy-style docstring support
- **Autodoc**: Automatic API documentation from docstrings

## Building the Documentation

### Prerequisites

Install documentation dependencies:

```bash
pip install -e ".[docs]"
```

Or for development (includes VISTA and all its dependencies):

```bash
cd ..
pip install -e ".[dev]"
```

### Building Locally

**Windows:**

```bash
cd docs
.\make.bat html
```

**Linux/macOS:**

```bash
cd docs
make html
```

The built documentation will be in `build/html/`. Open `build/html/index.html` in your browser to view it.

### Building with Multiple Versions

To build documentation for all versions (branches and tags):

```bash
cd docs
sphinx-multiversion source build/html
```

This will:
- Build documentation for all matching branches (main, develop)
- Build documentation for all version tags (1.0.0, 1.1.0, etc.)
- Create a version selector in the documentation

### Cleaning Build Files

**Windows:**

```bash
.\make.bat clean
```

**Linux/macOS:**

```bash
make clean
```

## Documentation Structure

```
docs/
├── source/
│   ├── conf.py              # Sphinx configuration
│   ├── index.rst            # Main documentation page
│   ├── getting_started/     # Installation and quickstart guides
│   ├── user_guide/          # User guides and tutorials
│   ├── api/                 # API reference documentation
│   ├── developer_guide/     # Developer documentation
│   ├── _static/             # Static files (images, CSS, etc.)
│   └── _templates/          # Custom templates
├── build/                   # Built documentation (generated)
├── requirements.txt         # Documentation dependencies
├── Makefile                 # Linux/macOS build script
└── make.bat                 # Windows build script
```

## Writing Documentation

### Adding New Pages

1. Create a new `.rst` file in the appropriate directory:
   - `getting_started/` - Installation and setup guides
   - `user_guide/` - Usage instructions and tutorials
   - `api/` - API reference pages
   - `developer_guide/` - Development documentation

2. Add the file to the appropriate `toctree` in `index.rst` or parent document:

```rst
.. toctree::
   :maxdepth: 2

   new_page
```

### API Documentation

API documentation is automatically generated from docstrings using the autodoc extension. VISTA uses NumPy-style docstrings:

```python
def my_function(param1, param2):
    """
    Brief description of the function.

    Longer description if needed.

    Parameters
    ----------
    param1 : type
        Description of param1
    param2 : type
        Description of param2

    Returns
    -------
    type
        Description of return value
    """
    pass
```

To document a module in the API reference, add it to the appropriate API page:

```rst
.. automodule:: vista.module_name
   :members:
   :undoc-members:
   :show-inheritance:
```

### reStructuredText Tips

**Headings:**

```rst
Main Title
==========

Section
-------

Subsection
~~~~~~~~~~
```

**Code Blocks:**

```rst
.. code-block:: python

   from vista import Imagery
   img = Imagery.from_file('data.h5')
```

**Links:**

```rst
External: `Link text <https://example.com>`_
Internal: :doc:`page_name`
API: :class:`~vista.imagery.imagery.Imagery`
```

**Notes and Warnings:**

```rst
.. note::
   This is a note.

.. warning::
   This is a warning.
```

## GitHub Pages Deployment

Documentation is automatically built and deployed to GitHub Pages via GitHub Actions.

### Automatic Deployment

The workflow (`.github/workflows/docs.yml`) triggers on:
- Pushes to `main` branch
- Pushes to `develop` branch
- New version tags (e.g., `1.7.0`)

### Accessing Documentation

Once deployed, documentation is available at:

```
https://awetomaton.github.io/VISTA/
```

Version-specific documentation:
- Latest (main): `https://awetomaton.github.io/VISTA/main/`
- Develop: `https://awetomaton.github.io/VISTA/develop/`
- Specific version: `https://awetomaton.github.io/VISTA/1.7.0/`

### Manual Deployment

If you need to manually deploy:

1. Build the documentation with sphinx-multiversion:
   ```bash
   sphinx-multiversion source build/html
   ```

2. Push to the `gh-pages` branch:
   ```bash
   git checkout --orphan gh-pages
   git rm -rf .
   cp -r docs/build/html/* .
   git add .
   git commit -m "Deploy documentation"
   git push origin gh-pages --force
   ```

## Versioning Strategy

### Branch Documentation

- `main`: Latest stable release documentation
- `develop`: Development version documentation (may include unreleased features)

### Tag Documentation

Version tags should follow semantic versioning: `MAJOR.MINOR.PATCH`

Example: `1.7.0`, `2.0.0`, `2.1.3`

When you create a new version tag and push it, the documentation for that version will be automatically built and published.

```bash
git tag 1.7.0
git push origin 1.7.0
```

## Configuration

### Sphinx Configuration (`source/conf.py`)

Key configuration sections:

- **Project information**: Name, version, author
- **Extensions**: Enabled Sphinx extensions
- **Theme options**: Furo theme customization
- **Autodoc settings**: API documentation generation
- **Napoleon settings**: NumPy docstring parsing
- **sphinx-multiversion**: Version selector configuration

### Customizing the Theme

Edit `conf.py` to customize Furo theme colors, fonts, etc.:

```python
html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#2b5b84",
        "color-brand-content": "#2b5b84",
    },
    # ... more options
}
```

### Version Selector

The version selector is configured in `conf.py`:

```python
# Which tags to include
smv_tag_whitelist = r"^v\d+\.\d+\.\d+$"

# Which branches to include
smv_branch_whitelist = r"^(main|develop)$"
```

## Troubleshooting

### Import Errors

If you get import errors when building:

1. Make sure VISTA is installed: `pip install -e .`
2. Check that all dependencies are installed: `pip install -r docs/requirements.txt`
3. Verify Python can import vista: `python -c "import vista; print(vista.__version__)"`

### Missing Module Warnings

If you see "WARNING: autodoc: failed to import module":

1. Ensure the module exists and is importable
2. Check for syntax errors in the module
3. Verify all dependencies are installed

### Build Errors

Clear the build cache and rebuild:

```bash
make clean
make html
```

### Version Selector Not Showing

The version selector requires:
1. Multiple versions to be built (branches or tags)
2. Proper sphinx-multiversion configuration
3. GitHub Pages deployment with all versions

## Contributing to Documentation

When contributing documentation:

1. Follow the existing structure and style
2. Use NumPy-style docstrings in code
3. Build and preview locally before submitting
4. Update the appropriate section (User Guide, API Reference, etc.)
5. Test that all links work
6. Ensure code examples are correct and tested

## Resources

- [Sphinx Documentation](https://www.sphinx-doc.org/)
- [Furo Theme Documentation](https://pradyunsg.me/furo/)
- [sphinx-multiversion Documentation](https://holzhaus.github.io/sphinx-multiversion/)
- [reStructuredText Primer](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html)
- [NumPy Docstring Guide](https://numpydoc.readthedocs.io/en/latest/format.html)
