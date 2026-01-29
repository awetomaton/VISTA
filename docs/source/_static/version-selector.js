// Version selector functionality for sphinx-multiversion
// This script enhances the version selector to navigate to the same page
// in the new version (if it exists), rather than just the version root.
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const versionSelector = document.getElementById('version-selector');

        if (!versionSelector) {
            return;
        }

        versionSelector.addEventListener('change', function() {
            const selectedVersionUrl = this.value;
            if (!selectedVersionUrl) return;

            // Parse the current URL to extract the path after the version
            // URL structure: /VISTA/{version}/{path}
            const currentPath = window.location.pathname;
            const pathParts = currentPath.split('/').filter(part => part);

            // Find the version part (assuming structure: /VISTA/version/page.html)
            // pathParts might be: ['VISTA', '1.8.0', 'api', 'index.html']
            let pagePath = '';
            if (pathParts.length >= 2) {
                // Skip the repo name and version, keep the rest
                pagePath = pathParts.slice(2).join('/');
            }

            // Build the new URL
            let newUrl = selectedVersionUrl;
            if (pagePath) {
                // Remove trailing slash from version URL if present
                newUrl = selectedVersionUrl.replace(/\/$/, '') + '/' + pagePath;
            }

            // Try to navigate to the same page; if it fails, fall back to index
            fetch(newUrl, { method: 'HEAD' })
                .then(response => {
                    if (response.ok) {
                        window.location.href = newUrl;
                    } else {
                        // Page doesn't exist in new version, go to index
                        window.location.href = selectedVersionUrl;
                    }
                })
                .catch(() => {
                    // On error (e.g., CORS), just navigate directly
                    window.location.href = newUrl;
                });
        });
    });
})();
