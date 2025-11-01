(function () {
  const placeholder = document.querySelector('[data-shared-footer]');
  if (!placeholder) return;

  fetch('/static/common/footer.html', { cache: 'no-cache' })
    .then((response) => (response.ok ? response.text() : ''))
    .then((html) => {
      if (!html) return;
      placeholder.innerHTML = html;
      const versionEl = placeholder.querySelector('[data-footer-version]');
      if (versionEl) {
        const lastModified = document.lastModified;
        versionEl.textContent = lastModified ? `build: ${lastModified}` : '';
      }
    })
    .catch(() => {});
})();
