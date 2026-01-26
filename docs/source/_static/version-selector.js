// Version selector functionality for sphinx-multiversion
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const versionSelector = document.getElementById('version-selector');

        if (!versionSelector) {
            return;
        }

        versionSelector.addEventListener('change', function() {
            const selectedUrl = this.value;

            // Get the current path without the version prefix
            const pathParts = window.location.pathname.split('/').filter(part => part);

            // Remove the first part (version) and reconstruct the path
            if (pathParts.length > 0) {
                pathParts.shift(); // Remove version
            }

            const newPath = pathParts.length > 0 ? pathParts.join('/') : 'index.html';

            // Navigate to the same page in the selected version
            window.location.href = selectedUrl + '/' + newPath;
        });
    });
})();
