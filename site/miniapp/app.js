const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const $ = (sel) => document.querySelector(sel);
const itemsEl = $('#items');
const template = $('#itemTemplate');
const draftPreview = $('#draftPreview');
let pendingDraftUrl = '';

function toast(text) {
  const node = $('#toast');
  node.textContent = text;
  node.classList.add('show');
  setTimeout(() => node.classList.remove('show'), 2200);
}

function send(action, payload = {}) {
  const data = JSON.stringify({ action, ...payload });
  if (tg?.sendData) {
    tg.sendData(data);
    toast('נשלח לבוט ✅');
  } else {
    navigator.clipboard?.writeText(data);
    toast('לא בתוך טלגרם — JSON הועתק לבדיקה');
  }
}

function localized(value, lang = 'he') {
  if (typeof value === 'string') return value;
  return value?.[lang] || value?.en || value?.he || '';
}

function vendorFromUrl(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return 'vendor';
  }
}

function showDraftPreview(url) {
  pendingDraftUrl = url;
  const vendor = vendorFromUrl(url);
  draftPreview.classList.remove('hidden');
  draftPreview.innerHTML = `
    <article class="local-draft">
      <span class="draft-badge">טיוטה לאישור</span>
      <h3>${vendor}</h3>
      <p>${url}</p>
      <div class="draft-actions">
        <button id="approveDraft" class="primary">Approve + Publish + Deploy</button>
        <button id="discardDraft">ביטול</button>
      </div>
      <p class="hint">הבוט יעשיר כותרת/תיאור/תמונה בזמן הפרסום. בעתיד נחבר API כדי להציג enrichment מלא כבר כאן.</p>
    </article>
  `;
  $('#approveDraft').addEventListener('click', () => {
    send('publish_url', { url: pendingDraftUrl, auto_deploy: true });
    draftPreview.classList.add('hidden');
    draftPreview.innerHTML = '';
    $('#urlInput').value = '';
  });
  $('#discardDraft').addEventListener('click', () => {
    pendingDraftUrl = '';
    draftPreview.classList.add('hidden');
    draftPreview.innerHTML = '';
  });
}

async function loadItems() {
  itemsEl.innerHTML = '<p class="hint">טוען…</p>';
  const res = await fetch('../data/store.json', { cache: 'no-store' });
  const store = await res.json();
  itemsEl.innerHTML = '';
  store.items.forEach((item) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector('img').src = item.image;
    node.querySelector('img').alt = localized(item.title);
    node.querySelector('.title').textContent = localized(item.title);
    node.querySelector('.meta').textContent = `${item.id} · ${item.price || 'TBD'} · ${item.vendor || ''}`;
    node.querySelector('.save').addEventListener('click', () => {
      const field = node.querySelector('.field').value;
      const value = node.querySelector('.value').value.trim();
      if (!value) return toast('צריך להזין ערך');
      send('setitem', { item_id: item.id, field, value, auto_deploy: true });
    });
    node.querySelector('.delete').addEventListener('click', () => {
      if (confirm(`למחוק את ${localized(item.title)}?`)) {
        send('delete', { target_id: item.id, auto_deploy: true });
      }
    });
    itemsEl.appendChild(node);
  });
}

$('#previewUrl').addEventListener('click', () => {
  const url = $('#urlInput').value.trim();
  if (!url.startsWith('http://') && !url.startsWith('https://')) return toast('לינק לא תקין');
  showDraftPreview(url);
});
$('#deploy').addEventListener('click', () => send('deploy'));
$('#refresh').addEventListener('click', loadItems);

loadItems().catch((err) => {
  console.error(err);
  itemsEl.innerHTML = '<p class="hint">לא הצלחתי לטעון מוצרים.</p>';
});
