// ============================================================
//  Bhairava Anugraha · Lacquer — controller
//  Reads its data from <script id="qna-data" type="application/json">
//  and renders the recent list, featured entry, and reading overlay.
// ============================================================

// ---------- CSV → DATA pipeline ----------
// Categories the site knows about, with their Sanskrit marks and roman numerals.
const CATEGORY_META = {
  "Mantra & Japa": { key: "mantra-japa", skt: "मन्त्र · जप", roman: "I" },
  "Pūjā, Āratī & Rituals": { key: "puja-aarti", skt: "पूजा · आरती", roman: "II" },
  "Maṇḍala & Anuṣṭhāna": { key: "mandala", skt: "मण्डल · अनुष्ठान", roman: "III" },
  "Experiences in Sādhanā": { key: "experiences", skt: "अनुभव", roman: "IV" },
  "Advanced Topics": { key: "advanced", skt: "गूढ विद्या", roman: "V" },
  "Women & Sādhanā": { key: "women", skt: "स्त्री · साधना", roman: "VI" },
};
const CAT_ORDER = ["mantra-japa", "puja-aarti", "mandala", "experiences", "advanced", "women"];

// Minimal RFC-4180 CSV parser: quoted fields, embedded newlines, "" escapes.
function parseCSV(text) {
  if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);  // strip BOM
  const CR = "\r", LF = "\n";
  const rows = []; let row = []; let field = ""; let inQ = false; let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (inQ) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        inQ = false; i++;
      } else { field += c; i++; }
    } else {
      if (c === '"') { inQ = true; i++; }
      else if (c === ",") { row.push(field); field = ""; i++; }
      else if (c === CR || c === LF) {
        row.push(field); field = "";
        if (c === CR && text[i + 1] === LF) i++;
        i++;
        if (row.length > 1 || row[0] !== "") rows.push(row);
        row = [];
      } else { field += c; i++; }
    }
  }
  if (field !== "" || row.length > 0) { row.push(field); rows.push(row); }
  return rows;
}

function formatDate(d) {
  if (!d) return "";
  const m = d.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (!m) return d;
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  return parseInt(m[1], 10) + " " + months[parseInt(m[2], 10) - 1] + " " + m[3];
}
function toIso(d, t) {
  const m = (d || "").match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (!m) return "";
  const time = t && /^\d{1,2}:\d{2}$/.test(t) ? t : "00:00";
  const hhmm = time.split(":").map(s => s.padStart(2, "0")).join(":");
  return m[3] + "-" + m[2].padStart(2, "0") + "-" + m[1].padStart(2, "0") + "T" + hhmm + ":00";
}
function stripGreeting(s) {
  return s.replace(/^\s*(namaskaram|namaskara|namaste|pranam(s)?|pranaam)\s*[,!\.]?\s*/i, "").trim();
}
function firstSentence(s, maxLen) {
  if (maxLen === undefined) maxLen = 110;
  const t = stripGreeting(s);
  const m = t.match(/^(.+?[\.\?\!])(\s|$)/);
  let out = m ? m[1].trim() : t.trim();
  if (out.length > maxLen) {
    out = out.slice(0, maxLen).replace(/\s+\S*$/, "").replace(/[,;:\- ]+$/, "") + "…";
  }
  return out;
}
function paragraphsToHtml(s) {
  if (!s) return "";
  const escape = t => t.replace(/&(?!#?\w+;)/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = t => t
    .replace(/\*\*\*([^*\n]+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*\n\s][^*\n]*?[^*\n\s]|[^*\n\s])\*(?!\*)/g, "<em>$1</em>");
  return s.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean).map(para => {
    const lines = para.split("\n").map(l => l.trim()).filter(Boolean);
    const isList = lines.length > 0 && lines.every(l => /^-\s+/.test(l));
    if (isList) {
      const items = lines.map(l => inline(escape(l.replace(/^-\s+/, "")))).map(i => "<li>" + i + "</li>").join("");
      return "<ul>" + items + "</ul>";
    }
    return "<p>" + inline(escape(para)) + "</p>";
  }).join("");
}

function buildData(csvText) {
  const rows = parseCSV(csvText);
  if (rows.length < 2) return { categories: [], entries: [] };
  const header = rows[0].map(h => h.trim().toLowerCase());
  const col = name => header.indexOf(name);
  const entries = [];
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    const cat = (r[col("category")] || "").trim();
    const meta = CATEGORY_META[cat];
    if (!meta) continue;
    const question = (r[col("question")] || "").trim();
    const answer = (r[col("answer")] || "").trim();
    if (!question || !answer) continue;

    // Filter out unapproved entries
    const approvedCol = col("approved");
    const approved = approvedCol !== -1 ? (r[approvedCol] || "").trim().toLowerCase() : "true";
    if (approved === "false" || approved === "0") continue;

    const date = (r[col("date")] || "").trim();
    const time = (r[col("time")] || "").trim();
    entries.push({
      num: parseInt(r[col("num")], 10) || 0,
      asker: (r[col("asker")] || "Anonymous").trim() || "Anonymous",
      date: formatDate(date),
      time: time,
      iso: toIso(date, time),
      category_key: meta.key,
      title: firstSentence(question),
      question: question.replace(/\n+/g, " "),
      original: question.replace(/\n+/g, " "),
      answer: paragraphsToHtml(answer),
    });
  }
  // Sort newest first (by iso desc, fallback to num desc)
  entries.sort((a, b) => (b.iso || "").localeCompare(a.iso || "") || (b.num - a.num));
  // In-folio numbering: oldest first within each folio
  const folio = {};
  entries.slice().sort((a, b) => (a.iso || "").localeCompare(b.iso || "")).forEach(e => {
    folio[e.category_key] = (folio[e.category_key] || 0) + 1;
    e.in_folio = folio[e.category_key];
  });
  // Renumber codex (1..N, newest = N)
  const N = entries.length;
  entries.forEach((e, i) => { e.num = N - i; });
  // Category list with counts
  const totals = {};
  entries.forEach(e => { totals[e.category_key] = (totals[e.category_key] || 0) + 1; });
  const categories = CAT_ORDER.map(k => {
    const found = Object.entries(CATEGORY_META).find(entry => entry[1].key === k);
    return { key: k, name: found[0], skt: found[1].skt, roman: found[1].roman, count: totals[k] || 0 };
  });
  return { categories, entries };
}

function showLoadError(err) {
  const banner = document.createElement("div");
  banner.style.cssText = "position: fixed; inset: 80px 24px auto 24px; z-index: 1000; background: rgba(7,6,10,0.95); color: var(--paper); border: 1px solid var(--gold-2); padding: 28px 32px; font-family: var(--display); font-style: italic; font-size: 17px; line-height: 1.55; max-width: 640px; margin: 0 auto; box-shadow: 0 0 0 4px rgba(0,0,0,0.5), 0 0 0 5px var(--gold-2), 0 30px 60px rgba(0,0,0,0.6);";
  const isFile = location.protocol === "file:";
  const head = '<div style="font-family: var(--mono); font-size: 10px; letter-spacing: 0.24em; color: var(--gold); margin-bottom: 14px;">— ॐ — UNABLE TO LOAD qna.csv —</div>';
  const msg = '<p style="margin: 0 0 12px;"><strong style="color: var(--gold);">' + (err.message || err) + '</strong></p>';
  const body = isFile
    ? '<p style="margin: 0 0 8px;">You are opening this file directly (<code style="font-family: var(--mono); color: var(--gold);">file://</code>), and browsers block CSV loading from <code>file://</code> for security.</p><p style="margin: 0 0 8px;">Double-click <code style="font-family: var(--mono); color: var(--gold);">start-site.bat</code> (Windows) or <code>start-site.sh</code> (Mac/Linux) in this folder, or from a terminal:</p><pre style="margin: 8px 0; padding: 12px; background: rgba(0,0,0,0.4); color: var(--gold); font-family: var(--mono); font-size: 12px;">python3 -m http.server 8000</pre><p style="margin: 0;">Then open <code style="color: var(--gold);">http://localhost:8000</code>.</p>'
    : '<p>Make sure <code style="font-family: var(--mono); color: var(--gold);">qna.csv</code> is in the same folder as <code>index.html</code> on the server.</p>';
  banner.innerHTML = head + msg + body;
  document.body.appendChild(banner);
}

let DATA = { categories: [], entries: [] };
const BY_NUM = Object.create(null);

async function loadData() {
  try {
    const resp = await fetch("qna.csv", { cache: "no-cache" });
    if (!resp.ok) throw new Error("Failed to load qna.csv (HTTP " + resp.status + ")");
    const text = await resp.text();
    DATA = buildData(text);
    DATA.entries.forEach(e => { BY_NUM[String(e.num)] = e; });
  } catch (err) {
    console.error("[Lacquer] data load failed:", err);
    showLoadError(err);
  }
}

// Helpers
const escapeHtml = s => String(s).replace(/[&<>"']/g, c => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));
const norm = s => String(s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

function categoryByKey(key) {
  return DATA.categories.find(c => c.key === key) || null;
}
function asciiTitle(t) {
  // Strip stray double-spaces / tab-y artifacts from titles for safer rendering.
  return String(t).replace(/\s+/g, " ").trim();
}

function smoothScrollTo(targetSel) {
  // If a folio page is active, exit it first so the homepage section we're scrolling to
  // is actually visible. Also clear any folio/entry hash so applyHash() agrees.
  if (document.body.classList.contains("is-folio-view")) {
    if (location.hash.startsWith("#folio/") || location.hash.startsWith("#entry/")) {
      history.replaceState(null, "", location.pathname + location.search);
    }
    hideFolioPage();
  }
  if (overlay.classList.contains("is-open")) {
    closeOverlay({ skipHash: true });
  }
  if (targetSel === "top") {
    window.scrollTo({ top: 0, behavior: "smooth" });
    return;
  }
  const el = document.querySelector(targetSel);
  if (!el) return;
  const chrome = document.querySelector(".chrome");
  const offset = chrome ? chrome.getBoundingClientRect().height : 0;
  const top = el.getBoundingClientRect().top + window.scrollY - offset - 12;
  window.scrollTo({ top, behavior: "smooth" });
}

function pulse(el) {
  if (!el) return;
  el.classList.remove("lacquer-pulse"); void el.offsetWidth;
  el.classList.add("lacquer-pulse");
  setTimeout(() => el.classList.remove("lacquer-pulse"), 1700);
}

// ---------- render: recent list (newest 8) ----------
function renderRecent() {
  const host = document.getElementById("recent-list");
  if (!host) return;
  // entries are already sorted newest-first by num desc
  const newest = DATA.entries.slice(0, 8);
  host.innerHTML = newest.map(e => {
    const cat = categoryByKey(e.category_key);
    const skt = cat ? cat.skt.split(" ")[0] : "";
    const catLabel = cat ? cat.name.toUpperCase() : e.category_key.toUpperCase();
    const dateBits = e.date ? e.date.split(" ") : [];
    const dateShort = e.date
      ? `${dateBits[0]} · ${(dateBits[1] || "").slice(0, 3).toUpperCase()} · ${dateBits[2] || ""}`
      : "—";
    return `
      <div class="row" data-id="${e.num}" data-cat-key="${e.category_key}">
        <div class="num">№ ${e.num}</div>
        <div class="skt">${escapeHtml(skt)}</div>
        <div class="q">${escapeHtml(asciiTitle(e.title))}</div>
        <div class="meta">
          <div class="meta-cat">${escapeHtml(catLabel)}</div>
          <div class="date">${escapeHtml(dateShort)}</div>
        </div>
        <div class="arr">→</div>
      </div>`;
  }).join("");
}

// ---------- render: featured "Today's Offering" (most recent) ----------
function renderFeatured() {
  const host = document.getElementById("featured-inner");
  if (!host) return;
  const e = DATA.entries[0];
  if (!e) return;
  const cat = categoryByKey(e.category_key);
  const inFolioRoman = toRoman(e.in_folio);
  const labelBits = [
    `ENTRY № ${e.num}`,
    e.date ? e.date.toUpperCase() : "",
    cat ? cat.name.toUpperCase() : "",
  ].filter(Boolean).join(" · ");

  // Pull the first paragraph of the answer for the preview
  const m = (e.answer || "").match(/<p>(.*?)<\/p>/);
  const previewHtml = m ? m[1] : "";

  host.innerHTML = `
    <div class="feat-text" style="grid-column: 1 / -1;">
      <div class="lab mono">${escapeHtml(labelBits)}</div>
      <h2>${escapeHtml(asciiTitle(e.title))}</h2>
      <p class="qbody">"${escapeHtml(e.question)}"</p>
      <div class="answer">${previewHtml}</div>
      <div class="meta-row">
        <div class="item"><div class="k">ASKED BY</div><div class="v">${escapeHtml(e.asker)}</div></div>
        ${cat ? `<div class="item"><div class="k">FOLIO</div><div class="v">${escapeHtml(cat.name)}</div></div>` : ""}
        <button class="read-more" data-id="${e.num}">READ FULL ENTRY →</button>
      </div>
    </div>`;
}

function toRoman(n) {
  if (!n) return "";
  const m = [["M", 1000], ["CM", 900], ["D", 500], ["CD", 400], ["C", 100], ["XC", 90],
  ["L", 50], ["XL", 40], ["X", 10], ["IX", 9], ["V", 5], ["IV", 4], ["I", 1]];
  let s = "", x = n;
  for (const [r, v] of m) while (x >= v) { s += r; x -= v; }
  return s;
}

// ---------- detail overlay ----------
const overlay = document.getElementById("overlay");
const overlayCard = overlay.querySelector(".overlay-card");

function renderEntry(id) {
  const e = BY_NUM[String(id)];
  if (!e) return false;
  const cat = categoryByKey(e.category_key);
  const folioRoman = cat ? cat.roman : "";
  const folioName = cat ? cat.name.toUpperCase() : "";
  const inFolioRoman = toRoman(e.in_folio);

  // Most answers don't have an explicit "lead" — wrap the first paragraph as the lead style
  let answerHtml = e.answer || "";
  const leadMatch = answerHtml.match(/^<p>(.*?)<\/p>/);
  if (leadMatch) {
    answerHtml = `<p class="lead">${leadMatch[1]}</p>` + answerHtml.slice(leadMatch[0].length);
  }

  overlayCard.innerHTML = `
    <button class="overlay-close" aria-label="Close">×</button>
    <div class="breadcrumb">
      <span>BHAIRAVA ANUGRAHA</span>
      <span class="sep">/</span>
      <span>FOLIO ${escapeHtml(folioRoman)} · ${escapeHtml(folioName)}</span>
      <span class="sep">/</span>
      <span>ENTRY ${escapeHtml(inFolioRoman || String(e.num))}</span>
    </div>
    <h1>${escapeHtml(asciiTitle(e.title))}</h1>
    <div class="meta-row">
      ${e.date ? `<span><span class="v">${escapeHtml(e.date)}</span></span>` : ""}
      <span style="margin-left:auto;">№ <span class="v">${e.num}</span></span>
    </div>
    <div class="layout">
      <aside class="original">
        <div class="head">
          <span>QUESTION</span>
        </div>
        <div class="body"><p><em>"${escapeHtml(e.original || e.question)}"</em></p></div>
      </aside>
      <div class="answer">
        ${answerHtml}
        <div class="signoff">
          <span>— Guruji</span>
          <span class="om-mark">ॐ</span>
        </div>
      </div>
    </div>`;
  return true;
}

// Track whether the user opened an entry from a folio page
// so we can return them there on close.
let folioBeforeEntry = null;

function openOverlay(id, opts) {
  opts = opts || {};
  if (!renderEntry(id)) return;
  overlay.classList.add("is-open");
  document.body.style.overflow = "hidden";
  overlay.scrollTop = 0;
  if (!opts.skipHash) history.replaceState(null, "", "#entry/" + id);
  const closer = overlayCard.querySelector(".overlay-close");
  if (closer) closer.focus();
}

function closeOverlay(opts) {
  opts = opts || {};
  if (!overlay.classList.contains("is-open")) return;
  overlay.classList.remove("is-open");
  document.body.style.overflow = "";
  if (!opts.skipHash) {
    if (folioBeforeEntry) {
      location.hash = "#folio/" + folioBeforeEntry;
      folioBeforeEntry = null;
    } else if (location.hash.startsWith("#entry/")) {
      history.replaceState(null, "", location.pathname + location.search);
    }
  }
}

// expose
window.__lacquer = {
  openEntry: openOverlay,
  closeEntry: closeOverlay,
  hasEntry: id => !!BY_NUM[String(id)],
  openSearch: null
};

// overlay events: close button + backdrop
overlay.addEventListener("click", e => {
  if (e.target === overlay) { closeOverlay(); return; }
  if (e.target.closest(".overlay-close")) { closeOverlay(); return; }
});

// any click on something with [data-id] opens that entry
document.addEventListener("click", e => {
  const trig = e.target.closest("[data-id]");
  if (!trig) return;
  const id = trig.getAttribute("data-id");
  if (BY_NUM[String(id)]) {
    e.preventDefault();
    // If we're currently in a folio view, remember it so we can return
    const m = location.hash.match(/^#folio\/([\w-]+)/);
    folioBeforeEntry = m ? m[1] : null;
    openOverlay(id);
  }
});

// global keys
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && overlay.classList.contains("is-open")) closeOverlay();
});

// hash routing
function applyHash() {
  const hash = location.hash || "";
  const mEntry = hash.match(/^#entry\/(\d+)/);
  const mFolio = hash.match(/^#folio\/([\w-]+)/);

  // Decide which view should be active.
  if (mEntry && BY_NUM[mEntry[1]]) {
    // Entry overlay; folio view stays as it was (or hides if not relevant)
    openOverlay(mEntry[1], { skipHash: true });
  } else if (mFolio) {
    const key = mFolio[1];
    if (overlay.classList.contains("is-open")) closeOverlay({ skipHash: true });
    if (key === "ALL") renderAllPage();
    else if (categoryByKey(key)) showFolioPage(key);
    else hideFolioPage();
  } else {
    // No hash: clear both views
    if (overlay.classList.contains("is-open")) closeOverlay({ skipHash: true });
    hideFolioPage();
  }
}

// ---------- folio page renderer ----------
const FOLIO_DESCRIPTIONS = {
  "mantra-japa": "On the form of mantra, the count, the breath; on the inward mechanics of repetition and the moment a sound becomes a doorway.",
  "puja-aarti": "Ācamana, offerings, the lamp, the prasādam. What may be substituted, what must not, and why the small details matter most.",
  "mandala": "The forty-eight-day cycle of transformation — vows undertaken, vows broken, what to do when the count slips, and how to begin again without despair.",
  "experiences": "Peace and sleep, the night sweats, yoga-nidrā, the unprovoked tears, the signs of progress — and whether to make anything of them at all.",
  "advanced": "Yantra, nyāsa, homa, the worship of one's kuladevatā — the practices that wait until the foundation is steady.",
  "women": "On the body's seasons and the practice that must accommodate them — menstruation, menopause, the ground of women's devotion.",
};

function renderFolioPage(catKey) {
  const cat = categoryByKey(catKey);
  if (!cat) return false;
  const entries = DATA.entries
    .filter(e => e.category_key === catKey)
    .sort((a, b) => b.num - a.num);

  const sktFirst = cat.skt.split(" ")[0];
  document.getElementById("folio-meta").textContent =
    `FOLIO ${cat.roman} · ${entries.length} ENTRIES`;
  document.getElementById("folio-divider-skt").textContent = cat.skt;
  document.getElementById("folio-divider-label").textContent = cat.name.toUpperCase();
  document.getElementById("folio-skt").textContent = cat.skt;
  document.getElementById("folio-name").textContent = cat.name;
  document.getElementById("folio-desc").textContent = FOLIO_DESCRIPTIONS[catKey] || "";

  const list = document.getElementById("folio-entries");
  list.innerHTML = entries.map(e => {
    const dateBits = e.date ? e.date.split(" ") : [];
    const dateShort = e.date
      ? `${dateBits[0]} · ${(dateBits[1] || "").slice(0, 3).toUpperCase()} · ${dateBits[2] || ""}`
      : "—";
    return `
      <div class="row" data-id="${e.num}" data-cat-key="${e.category_key}">
        <div class="num">№ ${e.num}</div>
        <div class="skt">${escapeHtml(sktFirst)}</div>
        <div class="q">${escapeHtml(asciiTitle(e.title))}</div>
        <div class="meta">
          <div class="meta-cat">${escapeHtml(e.asker || "—")}</div>
          <div class="date">${escapeHtml(dateShort)}</div>
        </div>
        <div class="arr">→</div>
      </div>`;
  }).join("");
  return true;
}

function showFolioPage(catKey) {
  if (!renderFolioPage(catKey)) return false;
  const page = document.getElementById("folio-page");
  page.removeAttribute("hidden");
  document.body.classList.add("is-folio-view");
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  return true;
}
function hideFolioPage() {
  document.body.classList.remove("is-folio-view");
  const page = document.getElementById("folio-page");
  if (page) page.setAttribute("hidden", "");
}

// Build a special "ALL" view: every entry, newest first.
function renderAllPage() {
  const entries = DATA.entries.slice().sort((a, b) => b.num - a.num);
  document.getElementById("folio-meta").textContent =
    `THE FULL CODEX · ${entries.length} ENTRIES`;
  document.getElementById("folio-divider-skt").textContent = "सर्वम्";
  document.getElementById("folio-divider-label").textContent = "EVERY ENTRY · NEWEST FIRST";
  document.getElementById("folio-skt").textContent = "सर्वम्";
  document.getElementById("folio-name").textContent = "The full Codex";
  document.getElementById("folio-desc").textContent =
    `All ${entries.length} entries in chronological order, as they were asked and answered — the manuscript without the chapter divisions.`;

  const list = document.getElementById("folio-entries");
  list.innerHTML = entries.map(e => {
    const cat = categoryByKey(e.category_key);
    const skt = cat ? cat.skt.split(" ")[0] : "";
    const dateBits = e.date ? e.date.split(" ") : [];
    const dateShort = e.date
      ? `${dateBits[0]} · ${(dateBits[1] || "").slice(0, 3).toUpperCase()} · ${dateBits[2] || ""}`
      : "—";
    return `
      <div class="row" data-id="${e.num}" data-cat-key="${e.category_key}">
        <div class="num">№ ${e.num}</div>
        <div class="skt">${escapeHtml(skt)}</div>
        <div class="q">${escapeHtml(asciiTitle(e.title))}</div>
        <div class="meta">
          <div class="meta-cat">${escapeHtml(cat ? cat.name.toUpperCase() : "")}</div>
          <div class="date">${escapeHtml(dateShort)}</div>
        </div>
        <div class="arr">→</div>
      </div>`;
  }).join("");
  document.getElementById("folio-page").removeAttribute("hidden");
  document.body.classList.add("is-folio-view");
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  return true;
}

// ---------- search palette ----------
function buildSearchIndex() {
  const idx = [];
  // categories first
  DATA.categories.forEach(c => {
    idx.push({
      kind: `FOLIO ${c.roman}`,
      skt: c.skt,
      titleHTML: c.name,
      titleText: c.name,
      desc: `${c.count} entries`,
      type: "category",
      catKey: c.key,
    });
  });
  // entries
  DATA.entries.forEach(e => {
    const cat = categoryByKey(e.category_key);
    idx.push({
      kind: `№ ${e.num}`,
      skt: cat ? cat.skt.split(" ")[0] : "",
      titleHTML: e.title,
      titleText: e.title + " " + (e.question || ""),
      desc: (cat ? cat.name : "") + (e.asker ? " — " + e.asker : ""),
      type: "entry",
      entryId: String(e.num),
    });
  });
  return idx;
}

// ---------- bootstrap ----------
(async function () {
  await loadData();
  // Re-index for lookups after load
  DATA.entries.forEach(e => { BY_NUM[String(e.num)] = e; });
  // Update folio-card counts dynamically (in case the CSV has changed counts)
  DATA.categories.forEach(c => {
    document.querySelectorAll(`.cat-grid .cat[data-cat-key="${c.key}"] .count`).forEach(el => {
      el.textContent = `${c.count} entries`;
    });
  });
  // Update hero stat / footer / view-all references that depended on the count
  const total = DATA.entries.length;
  document.querySelectorAll("[data-total]").forEach(el => { el.textContent = total; });

  renderRecent();
  renderFeatured();
  applyHash();
  window.addEventListener("hashchange", applyHash);

  if (location.search.includes("search=true")) {
    setTimeout(() => {
      if (window.__lacquer.openSearch) {
        window.__lacquer.openSearch();
        const cleanUrl = location.pathname + location.hash;
        history.replaceState(null, "", cleanUrl);
      }
    }, 150);
  }
})();

// ---------- nav, hero CTAs, folio cards ----------
document.addEventListener("click", e => {
  const trig = e.target.closest("[data-scroll]");
  if (!trig) return;
  e.preventDefault();
  smoothScrollTo(trig.getAttribute("data-scroll"));
});

document.querySelectorAll(".cat-grid .cat[data-folio]").forEach(card => {
  card.addEventListener("click", e => {
    e.preventDefault();
    const folio = card.getAttribute("data-folio");
    const catKey = card.getAttribute("data-cat-key") || "";
    if (folio === "ALL") {
      location.hash = "#folio/ALL";
    } else if (catKey) {
      location.hash = "#folio/" + catKey;
    }
  });
});

// "Return to the index" link inside the folio page
document.getElementById("folio-back-link").addEventListener("click", e => {
  e.preventDefault();
  // Clear hash → applyHash() will hide the folio page
  history.replaceState(null, "", location.pathname + location.search);
  hideFolioPage();
});

// ---------- search palette controller ----------
(function () {
  const palette = document.getElementById("palette");
  const input = document.getElementById("palette-input");
  const results = document.getElementById("palette-results");
  const countEl = document.getElementById("palette-count");
  const trigger = document.getElementById("chrome-search");
  const isOverlayOpen = () => overlay.classList.contains("is-open");
  const isOpen = () => palette.classList.contains("is-open");

  let idx = [];
  let filtered = [];
  let active = 0;

  const tokenize = q => q.toLowerCase().split(/\s+/).filter(Boolean);
  function score(item, tokens) {
    if (tokens.length === 0) return 0.001;
    const title = norm(item.titleText);
    const desc = norm(item.desc);
    const skt = item.skt.toLowerCase();
    const kind = item.kind.toLowerCase();
    let total = 0;
    for (const tRaw of tokens) {
      const t = norm(tRaw);
      let hit = 0;
      if (title.includes(t)) hit += 4;
      if (skt.includes(tRaw)) hit += 3;
      if (desc.includes(t)) hit += 2;
      if (kind.includes(t)) hit += 1;
      if (hit === 0) return 0;
      total += hit;
    }
    return total;
  }

  function render(query) {
    const tokens = tokenize(query);
    if (tokens.length === 0) {
      // Default view: 6 categories + most recent 8 entries
      filtered = idx.filter(x => x.type === "category")
        .concat(idx.filter(x => x.type === "entry").slice(0, 8));
    } else {
      filtered = idx
        .map(item => ({ item, s: score(item, tokens) }))
        .filter(x => x.s > 0)
        .sort((a, b) => b.s - a.s)
        .map(x => x.item);
    }
    active = 0;
    if (filtered.length === 0) {
      results.innerHTML = `
        <li class="palette-empty">
          <span class="skt-empty">— ॐ —</span>
          No entry matches "${escapeHtml(query)}". Try <em>mantra</em>, <em>japa</em>, <em>ghee</em>, or a question word.
        </li>`;
      countEl.textContent = `0 of ${DATA.entries.length}`;
      return;
    }
    results.innerHTML = filtered.map((item, i) => `
      <li class="palette-result${i === 0 ? " is-active" : ""}"
          role="option" aria-selected="${i === 0}" data-i="${i}">
        <span class="kind">${escapeHtml(item.kind)}</span>
        <span class="skt">${escapeHtml(item.skt)}</span>
        <span class="title">${escapeHtml(item.titleHTML)}</span>
        <span class="meta">${escapeHtml(item.desc).slice(0, 32)}${item.desc.length > 32 ? "…" : ""}</span>
      </li>
    `).join("");
    countEl.textContent = tokens.length === 0
      ? `${DATA.entries.length} entries indexed · showing newest`
      : `${filtered.length} of ${DATA.entries.length}`;
  }

  function setActive(i) {
    if (filtered.length === 0) return;
    active = (i + filtered.length) % filtered.length;
    results.querySelectorAll(".palette-result").forEach((el, j) => {
      const on = j === active;
      el.classList.toggle("is-active", on);
      el.setAttribute("aria-selected", on ? "true" : "false");
      if (on) el.scrollIntoView({ block: "nearest" });
    });
  }

  function activate(item) {
    closePalette();
    setTimeout(() => {
      if (item.type === "entry" && item.entryId) {
        // Capture folio context if any, then open
        const m = location.hash.match(/^#folio\/([\w-]+)/);
        folioBeforeEntry = m ? m[1] : null;
        openOverlay(item.entryId);
      } else if (item.type === "category" && item.catKey) {
        location.hash = "#folio/" + item.catKey;
      }
    }, 60);
  }

  function openPalette() {
    if (isOverlayOpen()) return;
    idx = buildSearchIndex();
    filtered = idx.slice();
    countEl.textContent = `${DATA.entries.length} entries indexed`;
    palette.classList.add("is-open");
    document.body.style.overflow = "hidden";
    input.value = "";
    render("");
    setTimeout(() => input.focus(), 30);
  }
  function closePalette() {
    palette.classList.remove("is-open");
    if (!isOverlayOpen()) document.body.style.overflow = "";
  }

  trigger?.addEventListener("click", openPalette);
  input.addEventListener("input", () => render(input.value));
  results.addEventListener("click", e => {
    const li = e.target.closest(".palette-result");
    if (!li) return;
    const i = parseInt(li.dataset.i, 10);
    if (!isNaN(i) && filtered[i]) activate(filtered[i]);
  });
  results.addEventListener("mousemove", e => {
    const li = e.target.closest(".palette-result");
    if (!li) return;
    const i = parseInt(li.dataset.i, 10);
    if (!isNaN(i) && i !== active) setActive(i);
  });
  palette.addEventListener("click", e => { if (e.target === palette) closePalette(); });

  document.addEventListener("keydown", e => {
    const k = e.key;
    if ((e.metaKey || e.ctrlKey) && (k === "k" || k === "K")) {
      e.preventDefault();
      if (isOpen()) closePalette(); else openPalette();
      return;
    }
    if (k === "/" && !isOpen() && !isOverlayOpen()) {
      const tag = (document.activeElement?.tagName || "").toLowerCase();
      const editing = tag === "input" || tag === "textarea" || document.activeElement?.isContentEditable;
      if (!editing) { e.preventDefault(); openPalette(); return; }
    }
    if (!isOpen()) return;
    if (k === "Escape") { e.preventDefault(); closePalette(); }
    else if (k === "ArrowDown") { e.preventDefault(); setActive(active + 1); }
    else if (k === "ArrowUp") { e.preventDefault(); setActive(active - 1); }
    else if (k === "Enter") { e.preventDefault(); if (filtered[active]) activate(filtered[active]); }
  });
  window.__lacquer.openSearch = openPalette;
})();
