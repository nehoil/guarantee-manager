const translations = {
  he: {
    appName: 'Guarantee Manager',
    theme: 'מצב כהה',
    themeLight: 'מצב בהיר',
    eyebrow: 'רשימת לונג׳ביטי שמחזירה אהבה לכסף שלך',
    browse: 'לראות המלצות',
    managedBy: 'מנוהל דרך בוט טלגרם פשוט',
    badgeTop: 'כסף בחזרה',
    badgeMain: 'מובטח',
    cmsTitle: 'CMS קטן, שימושי, בלי כאב ראש',
    cmsBody: 'מנהלים שולחים קישור מוצר לבוט. Guarantee Manager מושך תמונה, כותרת ותיאור, ואז מאפשר לאשר, לערוך ולפרסם לרשימה.',
    adminRole: 'אדמין בוט',
    adminRoleText: 'מוסיף מנהלים, מסיר אותם וקובע הרשאות CRUD.',
    managerRole: 'מנהל עמוד',
    managerRoleText: 'מוסיף, עורך ומסדר מוצרים לפי ההרשאות.',
    picksEyebrow: 'בחירות ראשונות',
    picksTitle: 'דברים קטנים שעושים טוב',
    visit: 'למוצר',
    footer: 'POC — מוכן ל-GitHub Pages, מחובר בהמשך לבוט.'
  },
  en: {
    appName: 'Guarantee Manager',
    theme: 'Dark mode',
    themeLight: 'Light mode',
    eyebrow: 'A longevity list that gives your money some love back',
    browse: 'Browse picks',
    managedBy: 'Managed by a simple Telegram bot',
    badgeTop: 'Money back',
    badgeMain: 'Guaranteed',
    cmsTitle: 'Tiny CMS, useful, no headache',
    cmsBody: 'Managers send a product link to the bot. Guarantee Manager fetches image, title, and description, then lets them approve, edit, and publish to the list.',
    adminRole: 'Bot admin',
    adminRoleText: 'Adds/removes managers and controls CRUD permissions.',
    managerRole: 'Page manager',
    managerRoleText: 'Adds, edits, and organizes products within their permissions.',
    picksEyebrow: 'First picks',
    picksTitle: 'Small things that do good',
    visit: 'View item',
    footer: 'POC — GitHub Pages ready, bot-connected next.'
  }
};

const state = {
  lang: localStorage.getItem('gm.lang') || 'he',
  theme: localStorage.getItem('gm.theme') || 'light',
  store: null
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

async function init() {
  const response = await fetch('data/store.json');
  state.store = await response.json();
  $('#langToggle').addEventListener('click', toggleLang);
  $('#themeToggle').addEventListener('click', toggleTheme);
  applyTheme();
  render();
}

function t(key) {
  return translations[state.lang][key] || key;
}

function localized(value) {
  if (typeof value === 'string') return value;
  return value?.[state.lang] || value?.en || value?.he || '';
}

function render() {
  document.documentElement.lang = state.lang;
  document.documentElement.dir = state.lang === 'he' ? 'rtl' : 'ltr';
  $('#langToggle').textContent = state.lang === 'he' ? 'EN' : 'עברית';
  $$('[data-i18n]').forEach((node) => node.textContent = t(node.dataset.i18n));
  $('#siteName').textContent = localized(state.store.site.name);
  $('#tagline').textContent = localized(state.store.site.tagline);
  $('#returnPolicy').textContent = localized(state.store.site.returnPolicy);
  renderItems();
  updateThemeText();
}

function renderItems() {
  $('#itemGrid').innerHTML = state.store.items.map((item) => `
    <article class="item-card">
      <div class="image-wrap"><img src="${item.image}" alt="${escapeHtml(localized(item.title))}" loading="lazy"></div>
      <div class="item-body">
        <div class="item-meta">
          <span>${escapeHtml(localized(item.category))}</span>
          <span>★ ${item.rating}</span>
        </div>
        <h3>${escapeHtml(localized(item.title))}</h3>
        <p>${escapeHtml(localized(item.description))}</p>
        <div class="badges">${(item.badges[state.lang] || []).map((badge) => `<span>${escapeHtml(badge)}</span>`).join('')}</div>
        <div class="item-foot">
          <strong>${escapeHtml(item.price)}</strong>
          <a href="${item.url}" target="_blank" rel="noopener noreferrer">${t('visit')} ↗</a>
        </div>
      </div>
    </article>
  `).join('');
}

function toggleLang() {
  state.lang = state.lang === 'he' ? 'en' : 'he';
  localStorage.setItem('gm.lang', state.lang);
  render();
}

function toggleTheme() {
  state.theme = state.theme === 'light' ? 'dark' : 'light';
  localStorage.setItem('gm.theme', state.theme);
  applyTheme();
}

function applyTheme() {
  document.body.dataset.theme = state.theme;
  updateThemeText();
}

function updateThemeText() {
  $('#themeToggle').textContent = state.theme === 'light' ? t('theme') : t('themeLight');
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
}

init().catch((error) => {
  console.error(error);
  $('#itemGrid').innerHTML = '<p>Could not load store data.</p>';
});
