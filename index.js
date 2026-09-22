// ============================================================
//  Bhairava Anugraha · Lacquer — controller
//  Reads its data from <script id="qna-data" type="application/json">
//  and renders the recent list, featured entry, and reading overlay.
// ============================================================

// ---------- CSV → DATA pipeline ----------
// Categories the site knows about, with their Sanskrit marks and roman numerals.
const CATEGORY_META = {
  "Mantra & Japa": { key: "mantra-japa", skt: "मन्त्र · जप", roman: "I" },
  "Puja, Aarti & Rituals": { key: "puja-aarti", skt: "पूजा · आरती", roman: "II" },
  "Mandala & Anushthana": { key: "mandala", skt: "मण्डल · अनुष्ठान", roman: "III" },
  "Experiences in Sādhanā": { key: "experiences", skt: "अनुभव", roman: "IV" },
  "Advanced Topics": { key: "advanced", skt: "गूढ विद्या", roman: "V" },
  "Women & Sādhanā": { key: "women", skt: "स्त्री · साधना", roman: "VI" },
};
const CAT_ORDER = ["mantra-japa", "puja-aarti", "mandala", "experiences", "advanced", "women"];

function normalizeCategory(rawCat) {
  if (!rawCat) return "Mantra & Japa";
  let s = String(rawCat).trim();
  // Remove XML hex escapes like _x0081_, _x008d_, etc.
  s = s.replace(/_x[0-9a-fA-F]{4}_/g, "");
  // Remove soft hyphens and invisible chars
  s = s.replace(/[\u00ad\u200b\u200c\u200d]/g, "");
  const norm = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

  if (norm.includes("advanced") || norm.includes("gudha")) {
    return "Advanced Topics";
  }
  if (norm.includes("experience") || norm.includes("anubhava") || norm.includes("anubhav")) {
    return "Experiences in Sādhanā";
  }
  if (norm.includes("women") || norm.includes("stri") || norm.includes("stree")) {
    return "Women & Sādhanā";
  }
  if (norm.includes("mandala") || norm.includes("anusthan") || norm.includes("anushthan") || (norm.includes("m") && norm.includes("ala") && (norm.includes("anu") || norm.includes("na") || norm.includes("ala")))) {
    return "Mandala & Anushthana";
  }
  if (norm.includes("puja") || norm.includes("arati") || norm.includes("aarti") || norm.includes("ritual") || norm.includes("puj")) {
    return "Puja, Aarti & Rituals";
  }
  if (norm.includes("mantra") || norm.includes("japa")) {
    return "Mantra & Japa";
  }
  if (CATEGORY_META[s]) return s;
  return s;
}

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
function capitalizeFirstLetter(str) {
  if (!str) return "";
  const match = str.match(/\p{L}/u);
  if (!match) return str;
  const index = match.index;
  return str.slice(0, index) + str.charAt(index).toUpperCase() + str.slice(index + 1);
}
function stripEmojis(str) {
  if (!str) return "";
  return str.replace(/\p{Extended_Pictographic}/gu, "")
            .replace(/[\uFE0E\uFE0F]/g, "")
            .replace(/[\u{1F3FB}-\u{1F3FF}]/gu, "")
            .replace(/\u200D/g, "")
            .replace(/[ \t]{2,}/g, " ");
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
  // Clean dangling unclosed markdown tokens from truncated titles
  if ((out.match(/\*\*/g) || []).length % 2 !== 0) {
    out = out.replace(/\*\*([^*]*)$/, (m, g1) => g1);
  }
  if ((out.match(/##/g) || []).length % 2 !== 0) {
    out = out.replace(/##([^#]*)$/, (m, g1) => g1);
  }
  out = out.replace(/(?:&lt;|<)u\b[^>]*?(?:&gt;|>)(?!.*(?:&lt;|<)\/u(?:&gt;|>))/gi, "");
  return out;
}
// Clean corrupted UTF-8 sequences that were previously decoded as Windows-1252 / CP1252
// or contain Excel escapes like _x009d_, _x0081_, etc.
function cleanMojibake(s) {
  if (!s) return "";
  let t = String(s);
  // Expand Excel escapes like _x009d_ -> chr(0x9d)
  t = t.replace(/_x([0-9a-fA-F]{4})_/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
  // Fix known damaged fragments before decoding
  t = t.replace(/â(?=["'])/g, "");
  t = t.replace(/â(?=\s*the child-form)/g, " —");
  t = t.replace(/â(?='s\b)/g, "");
  t = t.replace(/â(?=\*\*)/g, "");
  t = t.replace(/ä\x81/g, "ā");

  // If no mojibake indicators or control chars, return directly
  if (!/[âÃÄÅáéàè\u0080-\u009f]/.test(t)) {
    return t;
  }

  const cp1252Map = {
    0x20ac: 0x80, 0x201a: 0x82, 0x0192: 0x83, 0x201e: 0x84, 0x2026: 0x85, 0x2020: 0x86, 0x2021: 0x87,
    0x02c6: 0x88, 0x2030: 0x89, 0x0160: 0x8a, 0x2039: 0x8b, 0x0152: 0x8c, 0x017d: 0x8e, 0x2018: 0x91,
    0x2019: 0x92, 0x201c: 0x93, 0x201d: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97, 0x02dc: 0x98,
    0x2122: 0x99, 0x0161: 0x9a, 0x203a: 0x9b, 0x0153: 0x9c, 0x017e: 0x9e, 0x0178: 0x9f
  };

  try {
    const encoder = new TextEncoder();
    const bytes = [];
    for (let i = 0; i < t.length; i++) {
      const code = t.charCodeAt(i);
      if (cp1252Map[code] !== undefined) {
        bytes.push(cp1252Map[code]);
      } else if (code <= 0xff) {
        bytes.push(code);
      } else {
        const u = encoder.encode(t[i]);
        for (let j = 0; j < u.length; j++) bytes.push(u[j]);
      }
    }
    let dec = new TextDecoder("utf-8", { fatal: false }).decode(new Uint8Array(bytes));
    dec = dec.replace(/\bÄchamanam\b/g, "Āchamanam");
    dec = dec.replace(/\bÄhuti\b/g, "Āhuti");
    dec = dec.replace(/\bÄsana\b/g, "Āsana");
    return dec;
  } catch (_) {
    return t;
  }
}

// ---------- Rich Text Formatter (Frontend formatting rules) ----------
// 1. Bold: **text** -> <strong>text</strong>
// 2. Italics: ##text## -> <em>text</em>
// 3. Bold + Italics: **##Text##** -> <strong><em>Text</em></strong>
// 4. Single Inverted Commas: 'text' (straight quotes) -> No markdown code (plain text)
// 5. Bold + Single Inverted Commas: ‘text’ (curly quotes) -> <strong>‘text’</strong>
// 6. Bold + Italics + Single Inverted Commas: ##'text'## -> <strong><em>'text'</em></strong>
// 7. Double Inverted Commas: "text" (straight quotes) -> No markdown code (plain text)
// 8. Bold + Double Inverted Commas: “text” (curly quotes) -> <strong>“text”</strong>
// 9. Bold + Italics + Double Inverted Commas: ##“text”## -> <strong><em>“text”</em></strong>
// 10. Underline: <u>text</u> -> <u>text</u>
// 11. Bold + Underline: **<u>text</u>** -> <strong><u>text</u></strong>
// 12. Italic + Underline: *<u>text</u>* -> <em><u>text</u></em>
// 13. Bold + Italic + Underline: ***<u>text</u>*** -> <strong><em><u>text</u></em></strong>
function formatRichText(s) {
  if (!s) return "";
  let out = String(s);

  // Helper patterns for <u> and closing </u> or <u> (with or without HTML entity escaping)
  const U_OPEN = '(?:&lt;|<)u\\b[^>]*?(?:&gt;|>)';
  const U_CLOSE = '(?:&lt;|<)\\/?u\\b[^>]*?(?:&gt;|>)';

  // 1. Bold + Italic + Underline
  out = out.replace(new RegExp('\\*\\*\\*' + U_OPEN + '([\\s\\S]+?)' + U_CLOSE + '\\s*\\*\\*\\*', 'gi'), "<strong><em><u>$1</u></em></strong>");
  out = out.replace(new RegExp('\\*\\*##' + U_OPEN + '([\\s\\S]+?)' + U_CLOSE + '\\s*(?:##\\*\\*|\\*\\*)', 'gi'), "<strong><em><u>$1</u></em></strong>");
  out = out.replace(new RegExp('##\\*\\*' + U_OPEN + '([\\s\\S]+?)' + U_CLOSE + '\\s*(?:\\*\\*##|##)', 'gi'), "<strong><em><u>$1</u></em></strong>");
  out = out.replace(new RegExp(U_OPEN + '\\*\\*\\*([\\s\\S]+?)\\*\\*\\*' + U_CLOSE, 'gi'), "<strong><em><u>$1</u></em></strong>");
  out = out.replace(new RegExp(U_OPEN + '\\*\\*##([\\s\\S]+?)##\\*\\*' + U_CLOSE, 'gi'), "<strong><em><u>$1</u></em></strong>");
  out = out.replace(new RegExp(U_OPEN + '##\\*\\*([\\s\\S]+?)\\*\\*##' + U_CLOSE, 'gi'), "<strong><em><u>$1</u></em></strong>");

  // 2. Bold + Underline
  // Handles **<u>text</u>**, **<u>text<u>**, **<u>text<u> **, <u>**text**</u>, <u>**text**<u>
  out = out.replace(new RegExp('\\*\\*' + U_OPEN + '([\\s\\S]+?)' + U_CLOSE + '\\s*\\*\\*', 'gi'), "<strong><u>$1</u></strong>");
  out = out.replace(new RegExp(U_OPEN + '\\*\\*([\\s\\S]+?)\\*\\*' + U_CLOSE, 'gi'), "<strong><u>$1</u></strong>");

  // 3. Italic + Underline
  out = out.replace(new RegExp('\\*' + U_OPEN + '([\\s\\S]+?)' + U_CLOSE + '\\s*\\*', 'gi'), "<em><u>$1</u></em>");
  out = out.replace(new RegExp('##' + U_OPEN + '([\\s\\S]+?)' + U_CLOSE + '\\s*##?', 'gi'), "<em><u>$1</u></em>");
  out = out.replace(new RegExp(U_OPEN + '\\*([\\s\\S]+?)\\*' + U_CLOSE, 'gi'), "<em><u>$1</u></em>");
  out = out.replace(new RegExp(U_OPEN + '##([\\s\\S]+?)##' + U_CLOSE, 'gi'), "<em><u>$1</u></em>");

  // 4. Plain Underline: <u>text</u> or <u>text<u>
  out = out.replace(new RegExp(U_OPEN + '([\\s\\S]+?)' + U_CLOSE, 'gi'), "<u>$1</u>");

  // 5. Bold + Italics + Double Inverted Commas
  out = out.replace(/(?:\*\*##|##\*\*)“([^”\n]+)”(?:##\*\*|\*\*)*/g, "<strong><em>“$1”</em></strong>");
  out = out.replace(/(?:\*\*##|##\*\*)(?:"|&quot;)([^"\n]+)(?:"|&quot;)(?:##\*\*|\*\*)*/g, "<strong><em>\"$1\"</em></strong>");
  out = out.replace(/##“([^”\n]+)”##/g, "<strong><em>“$1”</em></strong>");
  out = out.replace(/##(?:"|&quot;)([^"\n]+)(?:"|&quot;)##/g, "<strong><em>\"$1\"</em></strong>");
  out = out.replace(/“##([^#\n]+)##”/g, "<strong><em>“$1”</em></strong>");
  out = out.replace(/(?:"|&quot;)##([^#\n]+)##(?:"|&quot;)/g, "<strong><em>\"$1\"</em></strong>");

  // 6. Bold + Italics + Single Inverted Commas
  out = out.replace(/(?:\*\*##|##\*\*)(?:'|&#39;|&#x27;)([^'\n]+)(?:'|&#39;|&#x27;)(?:##\*\*|\*\*)*/g, "<strong><em>'$1'</em></strong>");
  out = out.replace(/(?:\*\*##|##\*\*)‘((?:[a-zA-Z]’[a-zA-Z]|[^’\n])+)’(?:##\*\*|\*\*)*/g, "<strong><em>‘$1’</em></strong>");
  out = out.replace(/##(?:'|&#39;|&#x27;)([^'\n]+)(?:'|&#39;|&#x27;)##/g, "<strong><em>'$1'</em></strong>");
  out = out.replace(/##‘((?:[a-zA-Z]’[a-zA-Z]|[^’\n])+)’##/g, "<strong><em>‘$1’</em></strong>");
  out = out.replace(/(?:'|&#39;|&#x27;)##([^#\n]+)##(?:'|&#39;|&#x27;)/g, "<strong><em>'$1'</em></strong>");
  out = out.replace(/‘##([^#\n]+)##’/g, "<strong><em>‘$1’</em></strong>");

  // 7. Bold + Italics general
  out = out.replace(/\*\*##([^#\n]+?)##\*\*/g, "<strong><em>$1</em></strong>");
  out = out.replace(/##\*\*([^*\n]+?)\*\*##/g, "<strong><em>$1</em></strong>");
  out = out.replace(/\*\*##([^#\n]+?)##/g, "<strong><em>$1</em></strong>");
  out = out.replace(/\*\*\*([^*\n]+?)\*\*\*/g, "<strong><em>$1</em></strong>");

  // 8. Bold + Double Inverted Commas
  out = out.replace(/(?<!<strong>(?:<em>)?)“([^”\n]+)”(?!(?:<\/em>)?<\/strong>)/g, "<strong>“$1”</strong>");

  // 9. Bold + Single Inverted Commas
  out = out.replace(/(?<!<strong>(?:<em>)?)‘((?:[a-zA-Z]’[a-zA-Z]|[^’\n])+)’(?!(?:<\/em>)?<\/strong>)/g, "<strong>‘$1’</strong>");

  // 10. Bold: **text**
  out = out.replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>");

  // 11. Italics: ##text##
  out = out.replace(/##([^#\n]+?)##/g, "<em>$1</em>");

  // 12. Standard markdown italics fallback: *text*
  out = out.replace(/(?<!\*)\*([^*\n\s][^*\n]*?[^*\n\s]|[^*\n\s])\*(?!\*)/g, "<em>$1</em>");

  return out;
}

function stripOuterQuotes(s) {
  if (!s) return "";
  let str = String(s).trim();
  while (
    (str.startsWith('"') && str.endsWith('"') && str.length >= 2) ||
    (str.startsWith('“') && str.endsWith('”') && str.length >= 2) ||
    (str.startsWith('‘') && str.endsWith('’') && str.length >= 2) ||
    (str.startsWith("'") && str.endsWith("'") && str.length >= 2)
  ) {
    str = str.slice(1, -1).trim();
  }
  return str;
}

function formatLinesToHtml(rawText, isQuestion) {
  if (!rawText) return "";
  const cleaned = isQuestion ? stripOuterQuotes(rawText) : rawText;
  const escape = t => t.replace(/&(?!#?\w+;)/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  
  const paras = cleaned.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
  return paras.map(para => {
    const lines = para.split("\n").map(l => l.trim()).filter(Boolean);
    const chunks = [];
    let currentType = null; // 'p', 'ul', 'ol'
    let currentItems = [];

    const flush = () => {
      if (!currentType || currentItems.length === 0) return;
      if (currentType === "ul") {
        chunks.push("<ul>" + currentItems.map(i => "<li>" + formatRichText(escape(i)) + "</li>").join("") + "</ul>");
      } else if (currentType === "ol") {
        chunks.push("<ol>" + currentItems.map((item, idx) => {
          const numText = item.num || ((idx + 1) + ".");
          return `<li><span class="item-num">${escape(numText)}</span>` + formatRichText(escape(item.text)) + "</li>";
        }).join("") + "</ol>");
      } else {
        chunks.push("<p>" + currentItems.map(i => formatRichText(escape(i))).join("<br />") + "</p>");
      }
      currentItems = [];
      currentType = null;
    };

    for (const line of lines) {
      // Bullet list items starting with •, -, *, –, —
      const bulletMatch = line.match(/^([•\u2022\u2013\u2014\-]|â€¢|\*(?!\*))\s*(.*)$/);
      // Numbered list items starting with 1., 2), 1:, (1), 1 -, etc. (allowing optional markdown bold around number)
      const numMatch = line.match(/^(\*{0,2}\d+[.):]\*{0,2}|\(\d+\)|\d+\s*[-–—])\s+(.*)$/);

      if (bulletMatch) {
        if (currentType !== "ul") {
          flush();
          currentType = "ul";
        }
        currentItems.push(bulletMatch[2]);
      } else if (numMatch) {
        if (currentType !== "ol") {
          flush();
          currentType = "ol";
        }
        const cleanNum = numMatch[1].replace(/\*/g, "").trim();
        currentItems.push({ text: numMatch[2], num: cleanNum });
      } else {
        if (currentType !== "p") {
          flush();
          currentType = "p";
        }
        currentItems.push(line);
      }
    }
    flush();
    return chunks.join("");
  }).join("");
}

function formatQuestionHtml(s) {
  return formatLinesToHtml(s, true);
}

function paragraphsToHtml(s) {
  return formatLinesToHtml(s, false);
}

function buildData(csvText) {
  const rows = parseCSV(csvText);
  if (rows.length < 2) return { categories: [], entries: [] };
  const header = rows[0].map(h => h.trim().toLowerCase());
  const col = name => header.indexOf(name);
  const entries = [];
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    const rawCat = cleanMojibake((r[col("category")] || "").trim());
    if (!rawCat) continue;
    const cat = normalizeCategory(rawCat);
    let meta = CATEGORY_META[cat];
    if (!meta) {
      const key = cat.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
      meta = { key: key, skt: "साधना", roman: "•" };
      CATEGORY_META[cat] = meta;
      if (!CAT_ORDER.includes(key)) {
        CAT_ORDER.push(key);
      }
    }
    const question = capitalizeFirstLetter(cleanMojibake(stripEmojis((r[col("question")] || "").trim())));
    const answer = capitalizeFirstLetter(cleanMojibake(stripEmojis((r[col("answer")] || "").trim())));
    if (!question || !answer) continue;

    const rephrasedCol = col("rephrased");
    const rephrased = rephrasedCol !== -1 ? capitalizeFirstLetter(cleanMojibake(stripEmojis((r[col("rephrased")] || "").trim()))) : "";
    const displayedQuestion = rephrased !== "" ? rephrased : question;

    // Filter out unapproved entries
    const approvedCol = col("approved");
    const approved = approvedCol !== -1 ? (r[approvedCol] || "").trim().toLowerCase() : "true";
    if (approved === "false" || approved === "0") continue;

    // Read followup links (comma-separated nums)
    const followupCol = col("followup");
    const followupRaw = followupCol !== -1 ? (r[followupCol] || "").trim() : "";
    const followupNums = followupRaw
      ? followupRaw.split(",").map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n))
      : [];

    const date = (r[col("date")] || "").trim();
    const time = (r[col("time")] || "").trim();
    const tagsCol = col("tags");
    const tags = tagsCol !== -1 ? cleanMojibake((r[tagsCol] || "").trim()) : "";
    const linksCol = col("links") !== -1 ? col("links") : col("link");
    const links = linksCol !== -1 ? cleanMojibake((r[linksCol] || "").trim()) : "";
    entries.push({
      num: parseInt(r[col("num")], 10) || 0,
      asker: cleanMojibake((r[col("asker")] || "Anonymous").trim()) || "Anonymous",
      date: formatDate(date),
      time: time,
      iso: toIso(date, time),
      category_key: meta.key,
      title: firstSentence(displayedQuestion.replace(/\n+/g, " ")),
      question: displayedQuestion,
      original: question,
      rephrased: rephrased,
      answer: paragraphsToHtml(answer),
      followupNums,          // array of followup entry nums
      tags,
      links,
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
  // Renumbering removed so entry numbers match the database/CSV/rephrase portal exactly and permalinks are stable.
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

function buildDataFromJson(jsonList) {
  const entries = [];
  for (let i = 0; i < jsonList.length; i++) {
    const item = jsonList[i];
    const rawCat = cleanMojibake((item.category || "").trim());
    if (!rawCat) continue;
    const cat = normalizeCategory(rawCat);
    let meta = CATEGORY_META[cat];
    if (!meta) {
      const key = cat.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
      meta = { key: key, skt: "साधना", roman: "•" };
      CATEGORY_META[cat] = meta;
      if (!CAT_ORDER.includes(key)) {
        CAT_ORDER.push(key);
      }
    }
    const question = capitalizeFirstLetter(cleanMojibake(stripEmojis((item.question || "").trim())));
    const answer = capitalizeFirstLetter(cleanMojibake(stripEmojis((item.answer || "").trim())));
    if (!question || !answer) continue;

    const rephrased = capitalizeFirstLetter(cleanMojibake(stripEmojis((item.rephrased || "").trim())));
    const displayedQuestion = rephrased !== "" ? rephrased : question;

    // Filter out unapproved entries
    const approved = (item.approved || "").trim().toLowerCase();
    if (approved === "false" || approved === "0") continue;

    // Read followup links (comma-separated nums)
    const followupRaw = (item.followup || "").trim();
    const followupNums = followupRaw
      ? followupRaw.split(",").map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n))
      : [];

    const date = (item.date || "").trim();
    const time = (item.time || "").trim();
    const tags = cleanMojibake((item.tags || "").trim());
    const links = cleanMojibake((item.links || item.link || "").trim());
    entries.push({
      num: parseInt(item.num, 10) || 0,
      asker: cleanMojibake((item.asker || "Anonymous").trim()) || "Anonymous",
      date: formatDate(date),
      time: time,
      iso: toIso(date, time),
      category_key: meta.key,
      title: firstSentence(displayedQuestion.replace(/\n+/g, " ")),
      question: displayedQuestion,
      original: question,
      rephrased: rephrased,
      answer: paragraphsToHtml(answer),
      followupNums,
      tags,
      links,
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

  const totals = {};
  entries.forEach(e => { totals[e.category_key] = (totals[e.category_key] || 0) + 1; });
  const categories = CAT_ORDER.map(k => {
    const found = Object.entries(CATEGORY_META).find(entry => entry[1].key === k);
    return { key: k, name: found[0], skt: found[1].skt, roman: found[1].roman, count: totals[k] || 0 };
  });
  return { categories, entries };
}

async function loadData() {
  try {
    // Try loading live data from API first
    const activeDb = localStorage.getItem('bhairava_active_db') || 'prod';
    const resp = await fetch("/api/qna", { cache: "no-cache", headers: { "x-active-db": activeDb } });
    if (!resp.ok) throw new Error("HTTP Status " + resp.status);
    const json = await resp.json();
    if (json && json.error) throw new Error(json.error);
    DATA = buildDataFromJson(json);
    DATA.entries.forEach(e => { BY_NUM[String(e.num)] = e; });
  } catch (apiErr) {
    console.warn("[Lacquer] live API load failed, falling back to static CSV:", apiErr);
    try {
      const resp = await fetch("qna.csv", { cache: "no-cache" });
      if (!resp.ok) throw new Error("Failed to load qna.csv (HTTP " + resp.status + ")");
      const text = await resp.text();
      DATA = buildData(text);
      DATA.entries.forEach(e => { BY_NUM[String(e.num)] = e; });
    } catch (csvErr) {
      console.error("[Lacquer] CSV fallback load failed:", csvErr);
      showLoadError(csvErr);
    }
  }
}

// ---------- followup chain index ----------
// FOLLOWUP_OF[childNum] = parentNum  (any entry whose parent lists it as a followup)
// Built after data loads because we need all nums resolved.
const FOLLOWUP_OF = Object.create(null);

function buildFollowupIndex() {
  // Clear
  Object.keys(FOLLOWUP_OF).forEach(k => delete FOLLOWUP_OF[k]);
  DATA.entries.forEach(e => {
    (e.followupNums || []).forEach(childNum => {
      FOLLOWUP_OF[String(childNum)] = e.num;
    });
  });
}

// Returns the full ordered chain starting from the root ancestor of any entry.
function getChain(numStr) {
  const e = BY_NUM[String(numStr)];
  if (!e) return null;

  // Walk up to root
  let root = e;
  const visited = new Set();
  while (FOLLOWUP_OF[String(root.num)] !== undefined) {
    const parentNum = FOLLOWUP_OF[String(root.num)];
    if (visited.has(parentNum)) break; // guard against cycles
    visited.add(parentNum);
    const parent = BY_NUM[String(parentNum)];
    if (!parent) break;
    root = parent;
  }

  // Walk down the chain from root
  const chain = [];
  function walk(node) {
    chain.push(node);
    (node.followupNums || []).forEach(n => {
      const child = BY_NUM[String(n)];
      if (child && !chain.includes(child)) walk(child);
    });
  }
  walk(root);
  return chain.length > 1 ? chain : null; // null if no chain
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
        <div class="q">${formatRichText(escapeHtml(asciiTitle(e.title)))}</div>
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
      <h2>${formatRichText(escapeHtml(asciiTitle(e.title)))}</h2>
      <p class="qbody">"${formatRichText(escapeHtml(e.question.replace(/\n+/g, " ")))}"</p>
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

// ---------- link parsing & rendering helpers ----------
function normalizeUrl(u) {
  u = String(u || "").trim();
  if (!u) return "";
  if (/^https?:\/\//i.test(u)) return u;
  if (/^https?:/i.test(u)) {
    return u.replace(/^https?:[\/]*\/*/i, (m) => m.toLowerCase().startsWith("http:") ? "http://" : "https://");
  }
  return "https://" + u;
}

function friendlyUrlLabel(u) {
  try {
    const parsed = new URL(normalizeUrl(u));
    let host = parsed.hostname.replace(/^www\./i, "");
    if (host.includes("youtube.com") || host.includes("youtu.be")) return "YouTube";
    if (host.includes("t.me") || host.includes("telegram")) return "Telegram";
    if (host.includes("bhairavaanugraha.com")) return "Bhairava Anugraha";
    return host;
  } catch (err) {
    return u;
  }
}

function parseEntryLinks(rawLinks) {
  if (!rawLinks) return [];
  const text = String(rawLinks).trim();
  if (!text) return [];

  // Split by newlines or semicolons
  const rawItems = text.split(/\r?\n|;/).map(s => s.trim()).filter(Boolean);
  const results = [];

  for (const item of rawItems) {
    let label = "";
    let rawUrl = "";

    if (/^https?:\/\//i.test(item)) {
      rawUrl = item;
      label = friendlyUrlLabel(item);
    } else {
      // Check for dash separator e.g. "Daiva Anugraha - https://..."
      const dashMatch = item.match(/^(.*?)\s+-\s+(https?:\/\/.*)$/i);
      // Check for colon separator e.g. "abc:https:abc.com" or "Website: https://..."
      const colonIdx = item.indexOf(":");

      if (dashMatch) {
        label = dashMatch[1].trim();
        rawUrl = dashMatch[2].trim();
      } else if (colonIdx !== -1) {
        label = item.slice(0, colonIdx).trim();
        rawUrl = item.slice(colonIdx + 1).trim();
      } else {
        rawUrl = item;
        label = friendlyUrlLabel(item);
      }
    }

    if (!rawUrl) continue;
    const url = normalizeUrl(rawUrl);
    if (!label) label = friendlyUrlLabel(url);

    // Strip wrapping quotes from label if any
    label = label.replace(/^["'‘“]+|["'’”]+$/g, "").trim();

    results.push({ label, url, rawUrl });
  }
  return results;
}

function linkifyMentions(htmlStr, links) {
  if (!htmlStr || !links || !links.length) return htmlStr;

  const targets = [];
  const seenLabels = new Set();

  links.forEach(l => {
    if (!l.label || !l.url) return;
    const cleanLabel = l.label.trim();
    if (cleanLabel.length < 2) return;
    if (!seenLabels.has(cleanLabel.toLowerCase())) {
      seenLabels.add(cleanLabel.toLowerCase());
      targets.push({ phrase: cleanLabel, url: l.url });
    }
    // If label has trailing descriptors like "Website", "YouTube Channel", "Video", "Channel", "Group"
    const stripped = cleanLabel.replace(/\s+(website|youtube(\s+channel)?|video|channel|group|portal|link)$/i, "").trim();
    if (stripped.length >= 3 && !seenLabels.has(stripped.toLowerCase())) {
      seenLabels.add(stripped.toLowerCase());
      targets.push({ phrase: stripped, url: l.url });
    }
  });

  targets.sort((a, b) => b.phrase.length - a.phrase.length);
  if (!targets.length) return htmlStr;

  let result = "";
  const tagRegex = /<[^>]+>/g;
  let lastIndex = 0;
  let match;
  let inAnchor = 0;

  while ((match = tagRegex.exec(htmlStr)) !== null) {
    const textChunk = htmlStr.slice(lastIndex, match.index);
    if (textChunk && inAnchor === 0) {
      result += _linkifyTextChunk(textChunk, targets);
    } else {
      result += textChunk;
    }

    const tag = match[0];
    if (/^<a\b/i.test(tag)) {
      inAnchor++;
    } else if (/^<\/a>/i.test(tag)) {
      inAnchor = Math.max(0, inAnchor - 1);
    }

    result += tag;
    lastIndex = tagRegex.lastIndex;
  }

  const remainingText = htmlStr.slice(lastIndex);
  if (remainingText && inAnchor === 0) {
    result += _linkifyTextChunk(remainingText, targets);
  } else {
    result += remainingText;
  }

  return result;
}

function _linkifyTextChunk(text, targets) {
  let res = text;
  for (const t of targets) {
    const escaped = t.phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const startsWord = /^\w/.test(t.phrase);
    const endsWord = /\w$/.test(t.phrase);
    const pattern = (startsWord ? "\\b" : "") + escaped + (endsWord ? "\\b" : "");
    const re = new RegExp(pattern, "gi");
    res = res.replace(re, (matched) => {
      return `<a href="${escapeHtml(t.url)}" class="entry-inline-link" target="_blank" rel="noopener noreferrer" title="${escapeHtml(t.url)}">${matched}</a>`;
    });
  }
  return res;
}

function _buildLinksSectionHtml(parsedLinks) {
  if (!parsedLinks || !parsedLinks.length) return "";

  const seenUrls = new Set();
  const uniqueLinks = parsedLinks.filter(l => {
    if (seenUrls.has(l.url)) return false;
    seenUrls.add(l.url);
    return true;
  });

  const chipsHtml = uniqueLinks.map(l => {
    let icon = "🔗";
    const uLow = l.url.toLowerCase();
    if (uLow.includes("youtube.com") || uLow.includes("youtu.be")) {
      icon = "▶";
    } else if (uLow.includes("t.me") || uLow.includes("telegram")) {
      icon = "✈";
    } else if (uLow.includes("bhairavaanugraha.com")) {
      icon = "◈";
    }

    return `
      <a class="entry-link-chip" href="${escapeHtml(l.url)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(l.url)}">
        <span class="chip-icon">${icon}</span>
        <span class="chip-label">${escapeHtml(l.label)}</span>
        <span class="chip-arrow">↗</span>
      </a>`;
  }).join("");

  return `
    <div class="entry-links-section">
      <div class="entry-links-heading">
        <span class="entry-links-icon">◈</span>
        <span class="entry-links-title">REFERENCES &amp; SOURCES</span>
      </div>
      <div class="entry-links-grid">
        ${chipsHtml}
      </div>
    </div>`;
}

// ---------- detail overlay ----------
const overlay = document.getElementById("overlay");
const overlayCard = overlay.querySelector(".overlay-card");

function renderEntry(id) {
  const e = BY_NUM[String(id)];
  if (!e) return false;

  const chain = getChain(String(id));

  if (chain && chain.length > 1) {
    // ---- THREAD VIEW ----
    overlayCard.innerHTML = _buildThreadHtml(chain, e.num);
  } else {
    // ---- SINGLE ENTRY VIEW ----
    overlayCard.innerHTML = _buildSingleEntryHtml(e);
  }
  return true;
}

function _buildSingleEntryHtml(e) {
  const cat = categoryByKey(e.category_key);
  const folioRoman = cat ? cat.roman : "";
  const folioName = cat ? cat.name.toUpperCase() : "";
  const inFolioRoman = toRoman(e.in_folio);

  const parsedLinks = parseEntryLinks(e.links);

  let answerHtml = e.answer || "";
  if (parsedLinks.length > 0) {
    answerHtml = linkifyMentions(answerHtml, parsedLinks);
  }
  const leadMatch = answerHtml.match(/^<p>(.*?)<\/p>/);
  if (leadMatch) {
    answerHtml = `<p class="lead">${leadMatch[1]}</p>` + answerHtml.slice(leadMatch[0].length);
  }

  let questionHtml = formatQuestionHtml(e.question);
  if (parsedLinks.length > 0) {
    questionHtml = linkifyMentions(questionHtml, parsedLinks);
  }

  const linksHtml = _buildLinksSectionHtml(parsedLinks);

  return `
    <button class="overlay-close" aria-label="Close">×</button>
    <div class="breadcrumb">
      <span>BHAIRAVA ANUGRAHA</span>
      <span class="sep">/</span>
      <span>FOLIO ${escapeHtml(folioRoman)} · ${escapeHtml(folioName)}</span>
      <span class="sep">/</span>
      <span>ENTRY ${escapeHtml(inFolioRoman || String(e.num))}</span>
    </div>
    <h1>${formatRichText(escapeHtml(asciiTitle(e.title)))}</h1>
    <div class="meta-row">
      ${e.asker ? `<span>SEEKER <span class="v">${escapeHtml(e.asker)}</span></span>` : ""}
      ${e.date ? `<span><span class="v">${escapeHtml(e.date)}</span></span>` : ""}
      <span style="margin-left:auto;">№ <span class="v">${e.num}</span></span>
    </div>
    <div class="layout">
      <aside class="original">
        <div class="head">
          <span>QUESTION</span>
        </div>
        <div class="body">${questionHtml}</div>
      </aside>
      <div class="answer">
        ${answerHtml}
        ${linksHtml}
        <div class="signoff">
          <span>— Guruji</span>
          <span class="om-mark">ॐ</span>
        </div>
      </div>
    </div>`;
}

function _buildThreadHtml(chain, activeNum) {
  const firstEntry = chain[0];
  const cat = categoryByKey(firstEntry.category_key);
  const folioRoman = cat ? cat.roman : "";
  const folioName = cat ? cat.name.toUpperCase() : "";

  const sections = chain.map((e, idx) => {
    const isActive = e.num === activeNum;
    const parsedLinks = parseEntryLinks(e.links);

    let answerHtml = e.answer || "";
    if (parsedLinks.length > 0) {
      answerHtml = linkifyMentions(answerHtml, parsedLinks);
    }
    const leadMatch = answerHtml.match(/^<p>(.*?)<\/p>/);
    if (leadMatch) {
      answerHtml = `<p class="lead">${leadMatch[1]}</p>` + answerHtml.slice(leadMatch[0].length);
    }

    let questionHtml = formatQuestionHtml(e.question);
    if (parsedLinks.length > 0) {
      questionHtml = linkifyMentions(questionHtml, parsedLinks);
    }

    const linksHtml = _buildLinksSectionHtml(parsedLinks);
    const isFollowup = idx > 0;
    const inFolioRoman = toRoman(e.in_folio);
    const divider = isFollowup
      ? `<div class="thread-divider" id="thread-entry-${e.num}">
           <span class="thread-divider-icon">↓</span>
           <span class="thread-divider-label">FOLLOW-UP · № ${e.num}</span>
           <button class="thread-back-btn" onclick="document.getElementById('thread-entry-${firstEntry.num}').scrollIntoView({behavior:'smooth',block:'start'})">↑ Back to Question</button>
         </div>`
      : `<div class="thread-divider thread-root" id="thread-entry-${e.num}">
           <span class="thread-divider-label">ORIGINAL QUESTION · № ${e.num}</span>
           ${chain.length > 1 ? `<button class="thread-back-btn" onclick="document.getElementById('thread-entry-${chain[1].num}').scrollIntoView({behavior:'smooth',block:'start'})">↓ See Follow-up</button>` : ""}
         </div>`;

    return `
      ${divider}
      <div class="thread-entry${isActive ? " thread-active" : ""}"
           data-entry-num="${e.num}">
        <div class="meta-row">
          ${e.asker ? `<span>SEEKER <span class="v">${escapeHtml(e.asker)}</span></span>` : ""}
          ${e.date ? `<span><span class="v">${escapeHtml(e.date)}</span></span>` : ""}
          <span style="margin-left:auto;">№ <span class="v">${e.num}</span></span>
        </div>
        <div class="layout">
          <aside class="original">
            <div class="head"><span>${isFollowup ? "FOLLOW-UP QUESTION" : "QUESTION"}</span></div>
            <div class="body">${questionHtml}</div>
          </aside>
          <div class="answer">
            ${answerHtml}
            ${linksHtml}
            <div class="signoff">
              <span>— Guruji</span>
              <span class="om-mark">ॐ</span>
            </div>
          </div>
        </div>
      </div>`;
  }).join("");

  return `
    <button class="overlay-close" aria-label="Close">×</button>
    <div class="breadcrumb">
      <span>BHAIRAVA ANUGRAHA</span>
      <span class="sep">/</span>
      <span>FOLIO ${escapeHtml(folioRoman)} · ${escapeHtml(folioName)}</span>
      <span class="sep">/</span>
      <span>THREAD · ${chain.length} ENTRIES</span>
    </div>
    <h1 class="thread-title">${formatRichText(escapeHtml(asciiTitle(firstEntry.title)))}</h1>
    <div class="thread-meta">
      <span class="thread-badge">🔗 ${chain.length}-PART THREAD</span>
    </div>
    ${sections}`;
}

// Track whether the user opened an entry from a folio page
// so we can return them there on close.
let folioBeforeEntry = null;
let currentFolioKey = null;

function openOverlay(id, opts) {
  opts = opts || {};
  if (!renderEntry(id)) return;
  overlay.classList.add("is-open");
  document.body.style.overflow = "hidden";
  overlay.scrollTop = 0;
  if (!opts.skipHash) {
    history.pushState({ view: "entry", id: String(id) }, "", "#entry/" + id);
  }
  const closer = overlayCard.querySelector(".overlay-close");
  if (closer) closer.focus();
}

function closeOverlay(opts) {
  opts = opts || {};
  if (!overlay.classList.contains("is-open")) return;
  overlay.classList.remove("is-open");
  document.body.style.overflow = "";
  if (!opts.skipHash) {
    if (location.hash.startsWith("#entry/")) {
      const m = location.hash.match(/^#entry\/(\d+)/);
      const eObj = m ? BY_NUM[m[1]] : null;
      const targetFolio = folioBeforeEntry || (eObj ? eObj.category_key : null);
      folioBeforeEntry = null;

      if (window.history.length > 1) {
        history.back();
      } else if (targetFolio) {
        location.hash = "#folio/" + targetFolio;
      } else {
        history.replaceState(null, "", location.pathname + location.search);
      }
    } else if (folioBeforeEntry) {
      location.hash = "#folio/" + folioBeforeEntry;
      folioBeforeEntry = null;
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
    const eObj = BY_NUM[String(id)];
    const catKey = eObj ? eObj.category_key : null;
    const mFolio = location.hash.match(/^#folio\/([\w-]+)/);
    const mEntry = location.hash.match(/^#entry\/(\d+)/);

    folioBeforeEntry = mFolio ? mFolio[1] : catKey;
    window.__entryNavigatedInternally = true;
    window.__currentHistoryEntry = String(id);

    if ((!mFolio || (mFolio[1] !== catKey && mFolio[1] !== "ALL")) && !mEntry && catKey) {
      showFolioPage(catKey);
      history.pushState({ view: "folio", catKey }, "", "#folio/" + catKey);
    }
    history.pushState({ view: "entry", id: String(id) }, "", "#entry/" + id);
    openOverlay(id, { skipHash: true });
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
    const id = mEntry[1];
    const eObj = BY_NUM[id];
    const catKey = eObj ? eObj.category_key : null;
    folioBeforeEntry = catKey;

    // Ensure the entry's parent folio page is rendered and active under the overlay
    if (catKey && (!document.body.classList.contains("is-folio-view") || currentFolioKey !== catKey)) {
      showFolioPage(catKey);
    }

    // Direct landing or external URL change: seed history stack so browser back goes to parent folio
    if (catKey && window.__currentHistoryEntry !== id) {
      window.__currentHistoryEntry = id;
      if (!window.__entryNavigatedInternally) {
        if (!window.__historySeeded) {
          window.__historySeeded = true;
          history.replaceState({ view: "home" }, "", location.pathname + location.search);
          history.pushState({ view: "folio", catKey }, "", "#folio/" + catKey);
          history.pushState({ view: "entry", id }, "", "#entry/" + id);
        } else {
          history.replaceState({ view: "folio", catKey }, "", "#folio/" + catKey);
          history.pushState({ view: "entry", id }, "", "#entry/" + id);
        }
      }
    }
    window.__entryNavigatedInternally = false;

    openOverlay(id, { skipHash: true });
  } else if (mFolio) {
    const key = mFolio[1];
    if (overlay.classList.contains("is-open")) closeOverlay({ skipHash: true });
    if (key === "ALL") {
      if (!document.body.classList.contains("is-folio-view") || currentFolioKey !== "ALL") {
        renderAllPage();
      }
    } else if (categoryByKey(key)) {
      if (!document.body.classList.contains("is-folio-view") || currentFolioKey !== key) {
        showFolioPage(key);
      }
    } else {
      hideFolioPage();
    }
  } else {
    // No hash: clear both views
    if (overlay.classList.contains("is-open")) closeOverlay({ skipHash: true });
    hideFolioPage();
  }
}

// ---------- folio page renderer ----------
const FOLIO_DESCRIPTIONS = {
  "mantra-japa": "On the form of mantra, the count, the breath; on the inward mechanics of repetition and the moment a sound becomes a doorway.",
  "puja-aarti": "Āchamana, offerings, the lamp, the Prasādam. What may be substituted, what must not, and why the small details matter most.",
  "mandala": "The forty-eight-day cycle of transformation — vows undertaken, vows broken, what to do when the count slips, and how to begin again without despair.",
  "experiences": "Peace and sleep, the night sweats, yoga-nidrā, the unprovoked tears, the signs of progress — and whether to make anything of them at all.",
  "advanced": "Yantra, nyāsa, homa, the worship of one's kuladevatā — the practices that wait until the foundation is steady.",
  "women": "On the body's seasons and the practice that must accommodate them — menstruation, menopause, the ground of women's devotion.",
};

function renderFolioPage(catKey) {
  const cat = categoryByKey(catKey);
  if (!cat) return false;
  currentFolioKey = catKey;
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
        <div class="q">${formatRichText(escapeHtml(asciiTitle(e.title)))}</div>
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
  currentFolioKey = null;
  document.body.classList.remove("is-folio-view");
  const page = document.getElementById("folio-page");
  if (page) page.setAttribute("hidden", "");
}

// Build a special "ALL" view: every entry, newest first.
function renderAllPage() {
  currentFolioKey = "ALL";
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
        <div class="q">${formatRichText(escapeHtml(asciiTitle(e.title)))}</div>
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
      titleText: e.title + " " + (e.question || "") + " " + (e.original || "") + (e.tags ? " " + e.tags : "") + (e.links ? " " + e.links : ""),
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
  // Build followup chain index
  buildFollowupIndex();
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
  window.addEventListener("popstate", applyHash);

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
        <span class="title">${formatRichText(escapeHtml(item.titleHTML))}</span>
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
        const id = String(item.entryId);
        const eObj = BY_NUM[id];
        const catKey = eObj ? eObj.category_key : null;
        const mFolio = location.hash.match(/^#folio\/([\w-]+)/);
        const mEntry = location.hash.match(/^#entry\/(\d+)/);

        folioBeforeEntry = mFolio ? mFolio[1] : catKey;
        window.__entryNavigatedInternally = true;
        window.__currentHistoryEntry = id;

        if ((!mFolio || (mFolio[1] !== catKey && mFolio[1] !== "ALL")) && !mEntry && catKey) {
          showFolioPage(catKey);
          history.pushState({ view: "folio", catKey }, "", "#folio/" + catKey);
        }
        history.pushState({ view: "entry", id }, "", "#entry/" + id);
        openOverlay(id, { skipHash: true });
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
