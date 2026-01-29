// Version selector functionality for sphinx-multiversion
// Dynamically loads versions from versions.json and populates the dropdown
(function() {
    'use strict';

    // Get the base URL for the documentation (e.g., /VISTA/)
    function getBaseUrl() {
        const path = window.location.pathname;
        // Path structure: /VISTA/{version}/page.html
        // We need to get back to /VISTA/
        const parts = path.split('/').filter(part => part);
        if (parts.length >= 2) {
            // Return /VISTA/ (repo name)
            return '/' + parts[0] + '/';
        }
        return '/';
    }

    // Get current version from URL
    function getCurrentVersion() {
        const path = window.location.pathname;
        const parts = path.split('/').filter(part => part);
        // parts[0] = 'VISTA', parts[1] = version
        if (parts.length >= 2) {
            return parts[1];
        }
        return null;
    }

    // Get current page path (after version)
    function getCurrentPagePath() {
        const path = window.location.pathname;
        const parts = path.split('/').filter(part => part);
        // Skip repo name and version, keep the rest
        if (parts.length > 2) {
            return parts.slice(2).join('/');
        }
        return 'index.html';
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
    function createVersionSelector(versions) {
        let container = document.getElementById('version-selector-container');

        // If container doesn't exist (old versions), create and inject it
        if (!container) {
            container = document.createElement('div');
            container.id = 'version-selector-container';
            container.className = 'version-selector-banner';

            // Try to find the best place to inject it
            // Furo theme: look for the main content area or header
            const mainContent = document.querySelector('.main') ||
                               document.querySelector('main') ||
                               document.querySelector('.content') ||
                               document.querySelector('article');

            if (mainContent) {
                mainContent.insertBefore(container, mainContent.firstChild);
            } else {
                // Fallback: insert at the beginning of body
                document.body.insertBefore(container, document.body.firstChild);
            }

            // Add inline styles for old versions that don't have the CSS
            container.style.cssText = `
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.5rem;
                padding: 0.5rem 1rem;
                background-color: #f8f9fa;
                border-bottom: 1px solid #e9ecef;
                font-size: 0.875rem;
                margin-bottom: 1rem;
            `;
        }

        const currentVersion = getCurrentVersion();
        const sortedVersions = sortVersions(versions);

        // Create the selector HTML
        const label = document.createElement('label');
        label.setAttribute('for', 'version-selector');
        label.textContent = 'Version:';

        const select = document.createElement('select');
        select.id = 'version-selector';

        sortedVersions.forEach(version => {
            const option = document.createElement('option');
            option.value = version.url;
            option.textContent = version.name;
            if (version.name === 'main') {
                option.textContent += ' (latest)';
            }
            if (version.name === currentVersion) {
                option.selected = true;
            }
            select.appendChild(option);
        });

        // Add change handler
        select.addEventListener('change', function() {
            const selectedUrl = this.value;
            if (!selectedUrl) return;

            const baseUrl = getBaseUrl();
            const pagePath = getCurrentPagePath();

            // Build new URL - selectedUrl is like "./1.8.1/"
            // We need to construct the full path
            let newUrl = baseUrl + selectedUrl.replace('./', '') + pagePath;

            // Try to navigate to the same page; if it doesn't exist, fall back to index
            fetch(newUrl, { method: 'HEAD' })
                .then(response => {
                    if (response.ok) {
                        window.location.href = newUrl;
                    } else {
                        window.location.href = baseUrl + selectedUrl.replace('./', '');
                    }
                })
                .catch(() => {
                    // On error, just navigate directly
                    window.location.href = newUrl;
                });
        });

        container.appendChild(label);
        container.appendChild(select);
        container.style.display = 'flex';
    }

    // Fetch versions.json and initialize
    function init() {
        const baseUrl = getBaseUrl();
        const versionsUrl = baseUrl + 'versions.json';

        fetch(versionsUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error('versions.json not found');
                }
                return response.json();
            })
            .then(versions => {
                if (versions && versions.length > 1) {
                    createVersionSelector(versions);
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
