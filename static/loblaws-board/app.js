const watchListEl = document.getElementById('watch-list');
const emptyStateEl = document.getElementById('watch-empty');
const template = document.getElementById('watch-card-template');
const form = document.getElementById('watch-form');
const urlInput = document.getElementById('watch-url');
const formFeedback = document.getElementById('form-feedback');
const refreshAllBtn = document.getElementById('refresh-all');
const manageLink = document.querySelector('.board-header__manage');
const initialTokens = new URLSearchParams(window.location.search).get('token') || null;

const currencyFormatter = new Intl.NumberFormat('en-CA', {
  style: 'currency',
  currency: 'CAD',
  minimumFractionDigits: 2,
});

let listCache = [];
let loadingAll = false;

async function sha256Hex(value) {
  if (window.crypto && window.crypto.subtle) {
    const data = new TextEncoder().encode(value);
    const digest = await window.crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(digest));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  // Simple fallback hash for browsers without SubtleCrypto support
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash).toString(16);
}

function mapSaleType(type) {
  if (!type) return null;
  const upper = String(type).toUpperCase();
  const mappings = {
    SPECIAL: '促销中',
    CLEARANCE: '清仓特价',
    DEAL: '优惠中',
    SALE: '促销中',
  };
  return mappings[upper] || (upper !== 'REGULAR' ? '促销中' : null);
}

function getSaleLabel(item) {
  if (!item) return null;
  if (item.sale_text && item.sale_text.trim()) return item.sale_text.trim();
  if (item.sale_badge_name && String(item.sale_badge_name).trim()) {
    return String(item.sale_badge_name).trim();
  }
  return mapSaleType(item.sale_type);
}

function hasActiveSale(item) {
  return Boolean(getSaleLabel(item));
}

function toTimestamp(value) {
  if (!value) return 0;
  const parsed = new Date(value);
  const time = parsed.getTime();
  return Number.isNaN(time) ? 0 : time;
}

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

  const saleLabel = getSaleLabel(watch);

  if (saleLabel) {
    saleEl.textContent = saleLabel;
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

  const deleteBtn = node.querySelector('.watch-card__action--delete');
  if (deleteBtn) {
    deleteBtn.addEventListener('click', async () => {
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
  }

  return node;
}

async function loadList() {
  try {
    const url = new URL('/loblaws/watches', window.location.origin);
    if (initialTokens) {
      url.searchParams.set('token', initialTokens);
    }
    const data = await fetchJson(url.toString());
    listCache = Array.isArray(data) ? [...data] : [];
    listCache.sort((a, b) => {
      const dealA = hasActiveSale(a) ? 1 : 0;
      const dealB = hasActiveSale(b) ? 1 : 0;
      if (dealA !== dealB) return dealB - dealA;

      if (dealA && dealB) {
        const expA = toTimestamp(a && a.sale_expiry);
        const expB = toTimestamp(b && b.sale_expiry);
        if (expA !== expB) return expA - expB;
      }

      const updatedA = toTimestamp(a && a.last_checked_at);
      const updatedB = toTimestamp(b && b.last_checked_at);
      return updatedB - updatedA;
    });
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

if (form && urlInput) {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const url = urlInput.value.trim();
    if (!url) {
      setFormFeedback('请填写商品链接', 'error');
      urlInput.focus();
      return;
    }

    setFormFeedback('提交中，请稍候…');
    const payload = { url };

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
}

if (refreshAllBtn) {
  refreshAllBtn.addEventListener('click', async () => {
    if (loadingAll) return;
    loadingAll = true;
    refreshAllBtn.disabled = true;
    refreshAllBtn.textContent = '刷新中…';
    try {
      const url = new URL('/loblaws/watches/refresh', window.location.origin);
      if (initialTokens) {
        url.searchParams.set('token', initialTokens);
      }
      await fetchJson(url.toString(), { method: 'POST' });
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
}

if (manageLink) {
  const manageUrl = new URL(manageLink.href, window.location.origin);
  if (initialTokens) {
    manageUrl.searchParams.set('token', initialTokens);
    manageLink.href = manageUrl.toString();
  } else {
    manageLink.addEventListener('click', async (event) => {
      event.preventDefault();
      const password = window.prompt('请输入访问密码');
      if (!password) return;
      try {
        const hash = await sha256Hex(password);
        manageUrl.searchParams.set('token', hash);
        window.location.href = manageUrl.toString();
      } catch (err) {
        console.error(err);
      }
    });
  }
}

loadList().catch((err) => console.error(err));
