# Documentation Quick Reference

## Quick Commands

### Build documentation locally (single version)
```bash
cd docs
make html                    # Linux/macOS
.\make.bat html             # Windows
```

### View documentation locally
Open `docs/build/html/index.html` in your browser

### Build multi-version documentation

**Important**: sphinx-multiversion builds from git refs (branches and tags), so:

1. Commit and push your documentation changes to `main` or `develop`
2. Make sure your working directory is clean
3. Run from the project root:

```bash
# From project root (not from docs/)
sphinx-multiversion docs/source docs/build/html
```

**Note**: This command must be run from the project root directory, and you should be on a whitelisted branch (`main` or `develop`) with a clean working directory.

### Clean build files
```bash
make clean                  # Linux/macOS
.\make.bat clean           # Windows
```

## File Locations

- **Main config**: `docs/source/conf.py`
- **Home page**: `docs/source/index.rst`
- **API docs**: `docs/source/api/`
- **User guides**: `docs/source/user_guide/`
- **Getting started**: `docs/source/getting_started/`
- **Developer docs**: `docs/source/developer_guide/`

## Creating a New Release with Documentation

1. Update version in `vista/__init__.py`
2. Commit changes
3. Create and push a version tag:
   ```bash
   git tag 1.7.0
   git push origin 1.7.0
   ```
4. GitHub Actions will automatically build and deploy the documentation

## Common Edits

### Update home page
Edit `docs/source/index.rst`

### Add a new user guide page
1. Create `docs/source/user_guide/my_page.rst`
2. Add to toctree in `docs/source/index.rst`:
   ```rst
   user_guide/my_page
   ```

### Update API documentation
Edit files in `docs/source/api/`

### Change theme colors
Edit `html_theme_options` in `docs/source/conf.py`

## Troubleshooting

### "No matching refs found!" error

This error occurs when:
- You're not on a whitelisted branch (`main` or `develop`)
- Your working directory has uncommitted changes
- You're running from the wrong directory (should be project root)

**Solution**:
```bash
# Commit your changes first
git add .
git commit -m "Update documentation"

# Checkout to a whitelisted branch
git checkout develop

# Run from project root
cd /path/to/vista
sphinx-multiversion docs/source docs/build/html
```

### Build fails with import errors
```bash
pip install -e ".[docs]"
```

### Changes don't appear
```bash
make clean
make html
```

### GitHub Pages not updating
Check the Actions tab in GitHub repository

## More Information

See `docs/README.md` for complete documentation guide
