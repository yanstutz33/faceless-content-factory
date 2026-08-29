(() => {
  const storageKey = 'faceless-factory-theme';
  const root = document.documentElement;
  const saved = localStorage.getItem(storageKey);
  root.dataset.theme = saved === 'dark' ? 'dark' : 'light';

  const updateButton = button => {
    const dark = root.dataset.theme === 'dark';
    button.setAttribute('aria-pressed', String(dark));
    button.setAttribute('aria-label', dark ? 'Usar tema claro' : 'Usar tema escuro');
    button.querySelector('span').textContent = dark ? '☀' : '◐';
  };

  window.addEventListener('DOMContentLoaded', () => {
    const button = document.querySelector('#theme-toggle');
    if (!button) return;
    updateButton(button);
    button.addEventListener('click', () => {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem(storageKey, root.dataset.theme);
      updateButton(button);
    });
  });
})();
