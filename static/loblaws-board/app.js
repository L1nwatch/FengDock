const watchListEl = document.getElementById('watch-list');
const emptyStateEl = document.getElementById('watch-empty');
const template = document.getElementById('watch-card-template');
const form = document.getElementById('watch-form');
const urlInput = document.getElementById('watch-url');
const labelInput = document.getElementById('watch-label');
const formFeedback = document.getElementById('form-feedback');
const refreshAllBtn = document.getElementById('refresh-all');

const currencyFormatter = new Intl.NumberFormat('en-CA', {
  style: 'currency',
  currency: 'CAD',
  minimumFractionDigits: 2,
});

let listCache = [];
let loadingAll = false;

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    const error = new Error(`请求失败 (${response.status})`);
    error.responseText = text;
    throw error;
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function formatCurrency(value, unit) {
  if (value == null) return '--';
  try {
    const formatted = currencyFormatter.format(value);
    return unit ? `${formatted} / ${unit}` : formatted;
  } catch (err) {
    return `${value}${unit ? ` / ${unit}` : ''}`;
  }
}

function formatDate(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

function renderEmptyState(hasItems) {
  if (hasItems) {
    emptyStateEl.setAttribute('hidden', '');
  } else {
    emptyStateEl.removeAttribute('hidden');
  }
}

function clearList() {
  watchListEl.replaceChildren();
}

function renderWatchCard(watch) {
  const node = template.content.firstElementChild.cloneNode(true);
  node.dataset.id = String(watch.id);

  const titleEl = node.querySelector('.watch-card__title');
  const metaEl = node.querySelector('.watch-card__meta');
  const priceEl = node.querySelector('.watch-card__price');
  const wasEl = node.querySelector('.watch-card__was');
  const saleEl = node.querySelector('.watch-card__sale');
  const expiryEl = node.querySelector('.watch-card__expiry');
  const stockEl = node.querySelector('.watch-card__stock');
  const checkedEl = node.querySelector('.watch-card__checked');
  const imageWrapper = node.querySelector('.watch-card__image');
  const imageEl = imageWrapper.querySelector('img');

  titleEl.textContent = watch.label || watch.name || watch.product_code;
  const metaParts = [];
  if (watch.brand) metaParts.push(watch.brand);
  if (watch.store_id) metaParts.push(`Store: ${watch.store_id}`);
  if (watch.product_code) metaParts.push(watch.product_code);
  metaEl.textContent = metaParts.join(' · ');

  priceEl.textContent = formatCurrency(watch.current_price, watch.price_unit);
  wasEl.textContent = formatCurrency(watch.regular_price, watch.price_unit);

  if (watch.sale_text) {
    saleEl.textContent = watch.sale_text;
    saleEl.classList.remove('watch-card__sale--inactive');
    saleEl.classList.add('watch-card__sale--active');
  } else {
    saleEl.textContent = '暂无促销';
    saleEl.classList.remove('watch-card__sale--active');
    saleEl.classList.add('watch-card__sale--inactive');
  }

  expiryEl.textContent = watch.sale_expiry ? formatDate(watch.sale_expiry) : '--';

  if (watch.stock_status) {
    stockEl.textContent = watch.stock_status.toLowerCase() === 'in_stock'
      ? '有货'
      : watch.stock_status.toUpperCase();
  } else {
    stockEl.textContent = '--';
  }

  checkedEl.textContent = watch.last_checked_at ? formatDate(watch.last_checked_at) : '--';

  if (watch.image_url) {
    imageEl.src = watch.image_url;
    imageWrapper.removeAttribute('hidden');
  } else {
    imageWrapper.setAttribute('hidden', '');
  }

  node.querySelector('.watch-card__action--open').addEventListener('click', () => {
    window.open(watch.url, '_blank', 'noopener');
  });

  node.querySelector('.watch-card__action--refresh').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await fetchJson(`/loblaws/watches/${watch.id}/refresh`, { method: 'POST' });
      await loadList();
    } catch (err) {
      console.error(err);
      alert('刷新失败，请稍后重试');
    } finally {
      button.disabled = false;
    }
  });

  node.querySelector('.watch-card__action--delete').addEventListener('click', async () => {
    const confirmed = window.confirm('确定要删除这个监控吗？');
    if (!confirmed) return;
    try {
      await fetchJson(`/loblaws/watches/${watch.id}`, { method: 'DELETE' });
      await loadList();
    } catch (err) {
      console.error(err);
      alert('删除失败，请稍后重试');
    }
  });

  return node;
}

async function loadList() {
  try {
    const data = await fetchJson('/loblaws/watches');
    listCache = Array.isArray(data) ? data : [];
    renderEmptyState(listCache.length > 0);
    clearList();
    listCache.forEach((item) => {
      watchListEl.appendChild(renderWatchCard(item));
    });
  } catch (err) {
    console.error(err);
    renderEmptyState(false);
    emptyStateEl.textContent = '加载列表失败，请刷新页面再试。';
    emptyStateEl.removeAttribute('hidden');
  }
}

function setFormFeedback(message, type = 'info') {
  if (!formFeedback) return;
  formFeedback.textContent = message;
  formFeedback.classList.remove('board-form__feedback--error', 'board-form__feedback--success');
  if (type === 'error') {
    formFeedback.classList.add('board-form__feedback--error');
  } else if (type === 'success') {
    formFeedback.classList.add('board-form__feedback--success');
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  const label = labelInput.value.trim();
  if (!url) {
    setFormFeedback('请填写商品链接', 'error');
    urlInput.focus();
    return;
  }

  setFormFeedback('提交中，请稍候…');
  const payload = { url };
  if (label) payload.label = label;

  try {
    await fetchJson('/loblaws/watches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    setFormFeedback('已刷新最新信息', 'success');
    form.reset();
    await loadList();
  } catch (err) {
    console.error(err);
    setFormFeedback('添加失败，请确认链接是否正确', 'error');
  }
});

refreshAllBtn.addEventListener('click', async () => {
  if (loadingAll) return;
  loadingAll = true;
  refreshAllBtn.disabled = true;
  refreshAllBtn.textContent = '刷新中…';
  try {
    await fetchJson('/loblaws/watches/refresh', { method: 'POST' });
    await loadList();
  } catch (err) {
    console.error(err);
    alert('刷新失败，请稍后再试。');
  } finally {
    loadingAll = false;
    refreshAllBtn.disabled = false;
    refreshAllBtn.textContent = '刷新全部';
  }
});

loadList().catch((err) => console.error(err));
