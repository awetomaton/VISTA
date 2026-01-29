// Version selector functionality for sphinx-multiversion
// Dynamically loads versions from versions.json and populates the dropdown
(function() {
    'use strict';

    // Known version patterns to detect in URL
    const VERSION_PATTERNS = ['main', 'develop', /^\d+\.\d+\.\d+$/];

    // Detect if a path segment is a version
    function isVersion(segment) {
        return VERSION_PATTERNS.some(pattern => {
            if (typeof pattern === 'string') {
                return segment === pattern;
            }
            return pattern.test(segment);
        });
    }

    // Parse the URL to find base URL, current version, and page path
    // Works for both /VISTA/{version}/page.html and /{version}/page.html
    function parseUrl() {
        const path = window.location.pathname;
        const parts = path.split('/').filter(part => part);

        let baseIndex = -1;
        for (let i = 0; i < parts.length; i++) {
            if (isVersion(parts[i])) {
                baseIndex = i;
                break;
            }
        }

        if (baseIndex === -1) {
            // No version found in URL
            return { baseUrl: '/', currentVersion: null, pagePath: '' };
        }

        // Base URL is everything before the version
        const baseUrl = '/' + (baseIndex > 0 ? parts.slice(0, baseIndex).join('/') + '/' : '');
        const currentVersion = parts[baseIndex];
        const pagePath = parts.slice(baseIndex + 1).join('/') || 'index.html';

        return { baseUrl, currentVersion, pagePath };
    }

    // Sort versions: 'main' first, then 'develop', then semantic versions descending
    function sortVersions(versions) {
        return versions.sort((a, b) => {
            if (a.name === 'main') return -1;
            if (b.name === 'main') return 1;
            if (a.name === 'develop') return -1;
            if (b.name === 'develop') return 1;
            // Sort semantic versions descending (newest first)
            return b.name.localeCompare(a.name, undefined, { numeric: true });
        });
    }

    // Create and populate the version selector
    function createVersionSelector(versions, urlInfo) {
        let container = document.getElementById('version-selector-container');

        // If container doesn't exist (old versions), create and inject it
        if (!container) {
            container = document.createElement('div');
            container.id = 'version-selector-container';
            container.className = 'version-selector-banner';

            // For Furo theme: inject at the very top of the page, before everything
            document.body.insertBefore(container, document.body.firstChild);

            // Add inline styles - full width fixed banner at top
            container.style.cssText = `
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.5rem;
                padding: 0.5rem 1rem;
                background-color: #2b5b84;
                color: white;
                font-size: 0.875rem;
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                z-index: 1000;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            `;

            // Add padding to body to account for fixed banner
            document.body.style.paddingTop = '40px';
        }

        const sortedVersions = sortVersions(versions);

        // Create the selector HTML
        const label = document.createElement('label');
        label.setAttribute('for', 'version-selector');
        label.textContent = 'Version:';
        label.style.cssText = 'font-weight: 600; color: white;';

        const select = document.createElement('select');
        select.id = 'version-selector';
        select.style.cssText = `
            padding: 0.25rem 0.5rem;
            border: 1px solid rgba(255,255,255,0.3);
            border-radius: 0.25rem;
            background-color: rgba(255,255,255,0.1);
            color: white;
            font-size: 0.875rem;
            cursor: pointer;
        `;

        sortedVersions.forEach(version => {
            const option = document.createElement('option');
            option.value = version.name;
            option.textContent = version.name;
            if (version.name === 'main') {
                option.textContent += ' (latest)';
            }
            if (version.name === urlInfo.currentVersion) {
                option.selected = true;
            }
            select.appendChild(option);
        });

        // Add change handler
        select.addEventListener('change', function() {
            const selectedVersion = this.value;
            if (!selectedVersion) return;

            // Build new URL
            let newUrl = urlInfo.baseUrl + selectedVersion + '/' + urlInfo.pagePath;

            // Try to navigate to the same page; if it doesn't exist, fall back to index
            fetch(newUrl, { method: 'HEAD' })
                .then(response => {
                    if (response.ok) {
                        window.location.href = newUrl;
                    } else {
                        window.location.href = urlInfo.baseUrl + selectedVersion + '/';
                    }
                })
                .catch(() => {
                    // On error (e.g., CORS), just navigate directly
                    window.location.href = newUrl;
                });
        });

        container.appendChild(label);
        container.appendChild(select);
    }

    // Fix the navbar title to show the correct version from URL
    // This is needed because old tags have cached Python imports that show wrong version
    function fixNavbarTitle(currentVersion) {
        // Pattern to match "VISTA X.Y.Z" or "VISTA main" or "VISTA develop"
        const versionPattern = /VISTA\s+(\d+\.\d+\.\d+|main|develop)/g;
        const replacement = 'VISTA ' + currentVersion;

        // Fix the page title
        if (document.title.match(versionPattern)) {
            document.title = document.title.replace(versionPattern, replacement);
        }

        // Fix the sidebar brand text (Furo theme)
        const brandElements = document.querySelectorAll('.sidebar-brand-text, .brand');
        brandElements.forEach(el => {
            if (el.textContent.match(versionPattern)) {
                el.textContent = el.textContent.replace(versionPattern, replacement);
            }
        });

        // Fix any other elements that might contain the version
        const headerTitle = document.querySelector('.sidebar-brand');
        if (headerTitle) {
            const textNodes = [];
            const walk = document.createTreeWalker(headerTitle, NodeFilter.SHOW_TEXT, null, false);
            let node;
            while (node = walk.nextNode()) {
                if (node.textContent.match(versionPattern)) {
                    node.textContent = node.textContent.replace(versionPattern, replacement);
                }
            }
        }
    }

    // Fetch versions.json and initialize
    function init() {
        const urlInfo = parseUrl();

        if (!urlInfo.currentVersion) {
            console.log('Version selector: Could not detect current version from URL');
            return;
        }

        // Always fix the navbar title based on URL version
        fixNavbarTitle(urlInfo.currentVersion);

        const versionsUrl = urlInfo.baseUrl + 'versions.json';

        fetch(versionsUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error('versions.json not found at ' + versionsUrl);
                }
                return response.json();
            })
            .then(versions => {
                if (versions && versions.length > 1) {
                    createVersionSelector(versions, urlInfo);
                }
            })
            .catch(error => {
                console.log('Version selector not available:', error.message);
            });
    }

    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
