# Version Selector Implementation

This document explains how version switching works in the VISTA documentation.

## How It Works

### 1. Version Selector Dropdown

A dropdown menu appears at the top of the sidebar showing all available documentation versions. Users can:

- See which version they're currently viewing (selected in dropdown)
- Click the dropdown to see all available versions
- Select a different version to view

When a user selects a different version, they're taken to the same page in that version (if it exists), preserving their navigation context.

**Example:** If you're viewing `main/user_guide/tracking.html` and select version `1.7.0`, you'll be taken to `1.7.0/user_guide/tracking.html`.

### 2. URL-Based Navigation

Users can also manually change the version in the URL:

- **Main branch**: `https://awetomaton.github.io/VISTA/main/index.html`
- **Develop branch**: `https://awetomaton.github.io/VISTA/develop/index.html`
- **Version tags**: `https://awetomaton.github.io/VISTA/1.7.0/index.html`

### 3. Root URL Redirect

The root URL (`https://awetomaton.github.io/VISTA/`) automatically redirects to the `main` branch, which represents the latest stable release.

## Available Versions

The version selector shows:

- **main**: Latest stable release documentation
- **develop**: Development version (may include unreleased features)
- **1.7.0, 1.8.0 etc.**: Specific tagged releases

## Implementation Details

### Files Involved

- **[docs/source/_static/custom.css](source/_static/custom.css)**: Styles for the version selector
- **[docs/source/_static/version-selector.js](source/_static/version-selector.js)**: JavaScript for version switching behavior
- **[docs/source/_templates/base.html](source/_templates/base.html)**: Furo theme override that injects the version selector
- **[docs/source/conf.py](source/conf.py)**: Sphinx configuration with sphinx-multiversion settings

### Configuration

Version filtering is controlled in `conf.py`:

```python
# Only tags matching this pattern are built (e.g., 1.7.0, 1.8.0)
smv_tag_whitelist = r'^v\d+\.\d+\.\d+$'

# Only these branches are built
smv_branch_whitelist = r'^(main|develop)$'
```

## Optional: Version Warning Banner

To add a warning banner on non-stable versions (like `develop`), you can modify your documentation pages to include:

```rst
.. warning::
   You are viewing documentation for the development version.
   For the latest stable release, see the `main version <https://awetomaton.github.io/VISTA/main/>`_.
```

Or add it programmatically in `conf.py`:

```python
import os

# Add version warning banner for non-stable versions
current_branch = os.environ.get('SPHINX_MULTIVERSION_NAME', 'main')

if current_branch == 'develop':
    rst_prolog = """
.. warning::
   You are viewing the **development version** documentation.
   Features shown here may not be available in the latest release.
   For stable documentation, switch to a release version.
"""
```

## Customization

### Change Version Selector Position

Edit `docs/source/_templates/base.html` to move the version selector to a different location in the Furo theme.

### Change Version Display Names

Modify the version selector template to show custom display names:

```html
<option value="{{ item.url }}">
  {% if item.name == 'main' %}Latest ({{ item.name }})
  {% elif item.name == 'develop' %}Development
  {% else %}{{ item.name }}
  {% endif %}
</option>
```

### Change Styling

Edit `docs/source/_static/custom.css` to change colors, fonts, or layout of the version selector.

## Testing

### Test Locally

To test the version selector locally, you need to build with sphinx-multiversion:

```bash
cd docs
sphinx-multiversion source build/html
```

This builds all versions. Open any version's index.html:

```bash
# Open main version
start build/html/main/index.html

# Open develop version
start build/html/develop/index.html
```

The version selector should appear and be functional.

### Test on GitHub Pages

After pushing tags and branches, the GitHub Action will build all versions. Wait for the deployment to complete, then visit:

```
https://awetomaton.github.io/VISTA/main/
```

The version selector should show all available versions.

## Troubleshooting

### Version Selector Not Showing

1. **Local builds**: Regular `make html` won't show the version selector. Use `sphinx-multiversion` instead.
2. **Missing versions**: Check that your tags match the pattern `1.7.0`.
3. **Template not loading**: Ensure `_templates` directory is in the correct location.

### Version Selector Shows Wrong Versions

Check the whitelist patterns in `conf.py`:
- Tags: `smv_tag_whitelist = r'^\d+\.\d+\.\d+$'`
- Branches: `smv_branch_whitelist = r'^(main|develop)$'`

### JavaScript Not Working

Check browser console for errors. Ensure `version-selector.js` is in `docs/source/_static/`.

## More Information

- [sphinx-multiversion Documentation](https://holzhaus.github.io/sphinx-multiversion/)
- [Furo Theme Customization](https://pradyunsg.me/furo/customisation/)
