(() => {
  const $ = (selector) => document.querySelector(selector);
  const theme = $('.theme-toggle');
  theme?.setAttribute('aria-pressed', String(document.documentElement.dataset.theme === 'dark'));
  theme?.addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme !== 'dark';
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    theme.setAttribute('aria-pressed', String(dark));
    try { localStorage.setItem('theme', dark ? 'dark' : 'light'); } catch (_) {}
  });

  const input = $('#article-search');
  const cards = [...document.querySelectorAll('[data-post]')];
  const filters = [...document.querySelectorAll('[data-filter]')];
  let selected = '全部';
  function filter() {
    const query = (input?.value || '').trim().toLocaleLowerCase();
    let count = 0;
    cards.forEach(card => {
      const matches = (selected === '全部' || card.dataset.category === selected) &&
        (!query || card.dataset.search.toLocaleLowerCase().includes(query));
      card.hidden = !matches;
      if (matches) count++;
    });
    const empty = $('.empty-state'); if (empty) empty.hidden = count > 0;
    const status = $('.search-status');
    if (status) status.textContent = query || selected !== '全部' ? `找到 ${count} 篇笔记` : '';
  }
  input?.addEventListener('input', filter);
  filters.forEach(button => button.addEventListener('click', () => {
    selected = button.dataset.filter;
    filters.forEach(item => {
      item.classList.toggle('is-active', item === button);
      item.setAttribute('aria-pressed', String(item === button));
    });
    filter();
  }));
  $('#clear-search')?.addEventListener('click', () => {
    input.value = ''; filters[0].click(); input.focus();
  });
  document.addEventListener('keydown', event => {
    if (event.key === '/' && input && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !event.ctrlKey && !event.metaKey) {
      event.preventDefault(); input.focus();
    }
    if (event.key === 'Escape' && document.activeElement === input) {
      input.value = ''; filter(); input.blur();
    }
  });

  document.querySelectorAll('.prose pre').forEach(pre => {
    if (pre.closest('details')) return;
    const button = document.createElement('button');
    button.className = 'copy-code'; button.type = 'button';
    button.textContent = '复制'; button.setAttribute('aria-label', '复制代码');
    button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(pre.querySelector('code')?.textContent || '');
        button.textContent = '已复制';
      } catch (_) { button.textContent = '请选中复制'; }
      setTimeout(() => { button.textContent = '复制'; }, 1800);
    });
    pre.append(button);
  });

  const back = $('.back-top'), bar = $('.reading-progress span');
  function progress() {
    if (back) back.hidden = window.scrollY < 600;
    if (bar) {
      const available = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = `${available > 0 ? Math.min(100, window.scrollY / available * 100) : 100}%`;
    }
  }
  window.addEventListener('scroll', progress, { passive: true });
  progress();
  back?.addEventListener('click', () => window.scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }));
  if ('IntersectionObserver' in window) {
    const tocLinks = [...document.querySelectorAll('.desktop-toc nav a')];
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        tocLinks.forEach(link => link.classList.toggle('is-current', decodeURIComponent(link.hash.slice(1)) === entry.target.id));
      });
    }, { rootMargin: '-10% 0px -65% 0px' });
    document.querySelectorAll('.prose h2, .prose h3').forEach(heading => observer.observe(heading));
  }
})();
