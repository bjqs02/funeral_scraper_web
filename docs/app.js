/**
 * Static site for 崇德館 告別式 + 致意排程 (GitHub Pages).
 * Reads ./data/latest.json (produced by GH Actions cron) and renders 5 tabs
 * with shared filters + a calendar pivot view + CSV download.
 *
 * No build step, no framework, no CDN — keeps the page loading even if
 * external networks are restricted.
 */
"use strict";

const DATA_URL = "./data/latest.json";
const TAIPEI_TZ_OFFSET_HOURS = 8;
const NORTH_KEYWORD = "北區";

const TAB_DEFS = [
  { id: "farewells",  label: "全部場次",  source: "farewells",      hasNote: true,  badge: "badge-farewells" },
  { id: "north",      label: "北區戶籍",  source: "farewells",      hasNote: true,  badge: "badge-north",      forceNorth: true },
  { id: "schedule",   label: "致意排程",  source: "visit_schedule", hasNote: false, badge: "badge-schedule" },
  { id: "calendar",   label: "行事曆視圖", source: "visit_schedule", hasNote: false, isCalendar: true },
  { id: "coffin",     label: "停柩室原始", source: "coffin_rooms",   hasNote: false, badge: "badge-coffin" },
];

const FAREWELL_COLUMNS = [
  ["farewell_date",       "告別式日期"],
  ["time_range",          "告別式時間"],
  ["public_ceremony",     "公祭時間"],
  ["name",                "亡者姓名"],
  ["gender",              "性別"],
  ["age",                 "年齡"],
  ["residence",           "戶籍地"],
  ["highlight_residence", "戶籍是否北區"],
  ["hall",                "禮廳"],
  ["visit_start_date",    "致意起始日"],
  ["visit_end_date",      "致意截止日"],
  ["visit_location",      "致意地點"],
  ["visit_note",          "致意說明"],
  ["unit",                "館別"],
];

const SCHEDULE_COLUMNS = [
  ["visit_date",      "可致意日期"],
  ["name",            "亡者姓名"],
  ["gender",          "性別"],
  ["age",             "年齡"],
  ["residence",       "戶籍地"],
  ["visit_location",  "致意地點"],
  ["farewell_date",   "告別式日期"],
  ["time_range",      "告別式時間"],
  ["public_ceremony", "公祭時間"],
  ["hall",            "禮廳"],
  ["visit_note",      "備註"],
];

const COFFIN_COLUMNS = [
  ["occupancy_date",  "日期"],
  ["room_number",     "停柩室"],
  ["name",            "亡者姓名"],
  ["gender",          "性別"],
  ["age",             "年齡"],
  ["residence",       "戶籍地"],
  ["mortician",       "禮儀業者"],
  ["unit",            "館別"],
];

const COLUMNS_BY_SOURCE = {
  farewells:      FAREWELL_COLUMNS,
  visit_schedule: SCHEDULE_COLUMNS,
  coffin_rooms:   COFFIN_COLUMNS,
};

const KEYWORD_FIELDS = ["name", "residence", "visit_location", "hall"];

const $ = (id) => document.getElementById(id);

const state = {
  data: null,
  activeTab: "farewells",
  filters: {
    dates: new Set(),
    halls: new Set(),
    notes: new Set(),
    onlyNorth: true,
    keyword: "",
  },
};

async function loadData() {
  try {
    // Bust cached JSON so a freshly-deployed payload shows up without a hard refresh.
    const url = `${DATA_URL}?t=${Date.now()}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
    renderMeta();
    renderBadges();
    render();
  } catch (err) {
    $("loading").innerHTML =
      `<p style="color:#c00">❌ 載入 <code>${DATA_URL}</code> 失敗: ${err.message}</p>` +
      `<p class="muted">確認 GH Actions 至少跑過一次 (此檔由 cron 寫入)。</p>`;
  }
}

function renderMeta() {
  const { meta } = state.data;
  $("meta-range").textContent = `${meta.date_range.start} ~ ${meta.date_range.end}`;
  const gen = new Date(meta.generated_at_utc);
  const local = new Date(gen.getTime() + TAIPEI_TZ_OFFSET_HOURS * 3600 * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  const human = `${local.getUTCFullYear()}-${pad(local.getUTCMonth() + 1)}-${pad(local.getUTCDate())} `
              + `${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())} (UTC+8)`;
  const ageHours = (Date.now() - gen.getTime()) / 3600 / 1000;
  const ageLabel = ageHours < 1   ? `${Math.round(ageHours * 60)} 分鐘前`
                  : ageHours < 48 ? `${ageHours.toFixed(1)} 小時前`
                  :                 `${Math.floor(ageHours / 24)} 天前`;
  $("meta-updated").textContent = `${human} · ${ageLabel}`;
  $("meta-source").href = meta.source.farewell_url;
}

function renderBadges() {
  const f = state.data.farewells;
  $("badge-farewells").textContent = f.length;
  $("badge-north").textContent = f.filter(isNorthResidence).length;
  $("badge-schedule").textContent = state.data.visit_schedule.length;
  $("badge-coffin").textContent = state.data.coffin_rooms.length;
}

function isNorthResidence(row) {
  const r = row.residence ?? "";
  return String(r).includes(NORTH_KEYWORD);
}

function activeTabDef() {
  return TAB_DEFS.find((t) => t.id === state.activeTab);
}

function sourceRows() {
  const tab = activeTabDef();
  return state.data[tab.source] ?? [];
}

function applyFilters(rows) {
  const tab = activeTabDef();
  const { dates, halls, notes, onlyNorth, keyword } = state.filters;
  const kw = keyword.trim().toLowerCase();
  return rows.filter((row) => {
    if (dates.size && !dates.has(row.farewell_date)) return false;
    if (halls.size && !halls.has(row.hall)) return false;
    if (notes.size && tab.hasNote && !notes.has(row.visit_note)) return false;
    // 「北區戶籍」tab 強制 on (forceNorth); 其他 tab 用 checkbox 控制
    if ((tab.forceNorth || onlyNorth) && !isNorthResidence(row)) return false;
    if (kw) {
      const hit = KEYWORD_FIELDS.some((f) => {
        const v = row[f];
        return v != null && String(v).toLowerCase().includes(kw);
      });
      if (!hit) return false;
    }
    return true;
  });
}

function repopulateFilterOptions() {
  // Filter dropdowns reflect the CURRENT tab's source rows, not all of them —
  // otherwise 致意排程 tab would show 告別式日期 options that aren't in its data.
  const rows = sourceRows();
  fillSelect("f-date", uniqueSorted(rows.map((r) => r.farewell_date)));
  fillSelect("f-hall", uniqueSorted(rows.map((r) => r.hall)));
  fillSelect("f-note", uniqueSorted(rows.map((r) => r.visit_note)));

  const tab = activeTabDef();
  $("f-note").parentElement.style.display = tab.hasNote ? "" : "none";
  $("f-north").disabled = !!tab.forceNorth;
  if (tab.forceNorth) $("f-north").checked = true;
}

function uniqueSorted(arr) {
  return [...new Set(arr.filter((v) => v != null && v !== ""))].sort();
}

function fillSelect(id, values) {
  const sel = $(id);
  const prevSelected = new Set(Array.from(sel.selectedOptions).map((o) => o.value));
  sel.innerHTML = "";
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    if (prevSelected.has(v)) opt.selected = true;
    sel.appendChild(opt);
  }
  sel.size = Math.min(Math.max(values.length, 1), 4);
}

function render() {
  repopulateFilterOptions();
  const tab = activeTabDef();
  const filtered = applyFilters(sourceRows());
  $("count-line").textContent = `顯示 ${filtered.length} / ${sourceRows().length} 筆`;

  const main = $("content");
  if (filtered.length === 0) {
    main.innerHTML = `<div class="empty"><p>沒有符合篩選條件的資料。</p></div>`;
    return;
  }

  if (tab.isCalendar) {
    main.innerHTML = "";
    main.appendChild(renderCalendar(filtered));
  } else {
    main.innerHTML = "";
    main.appendChild(renderTable(filtered, COLUMNS_BY_SOURCE[tab.source]));
  }
}

function renderTable(rows, columns) {
  const table = document.createElement("table");
  table.className = "data";

  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  for (const [, label] of columns) {
    const th = document.createElement("th");
    th.textContent = label;
    trh.appendChild(th);
  }
  thead.appendChild(trh);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const [key] of columns) {
      const td = document.createElement("td");
      const v = row[key];
      td.textContent = formatCell(key, v);
      if (key === "highlight_residence") {
        td.className = "col-north";
        td.dataset.true = String(!!v);
      }
      if (key === "visit_location" && row.visit_start_date) {
        td.className = "col-visit-loc has-window";
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  return table;
}

function formatCell(key, v) {
  if (v === null || v === undefined || v === "") return "";
  if (typeof v === "boolean") return v ? "✓" : "";
  return String(v);
}

function renderCalendar(rows) {
  // Pivot to date × hour. Hour comes from the start of 告別式時間 ("06:00 - 11:00" → "06").
  // Display hours are restricted to 06-18 (typical funeral hours); anything outside
  // is appended after, so we never silently drop a row.
  const pivot = new Map();      // date -> Map(hour -> [cellLabel,…])
  const hoursSeen = new Set();
  for (const r of rows) {
    const hour = String(r.time_range || "").slice(0, 2).padStart(2, "0");
    hoursSeen.add(hour);
    const label = `${r.name} (${r.gender}${r.age}) @ ${r.hall}`;
    if (!pivot.has(r.visit_date)) pivot.set(r.visit_date, new Map());
    const byHour = pivot.get(r.visit_date);
    if (!byHour.has(hour)) byHour.set(hour, []);
    byHour.get(hour).push(label);
  }
  const dates = [...pivot.keys()].sort();
  const preferred = Array.from({ length: 13 }, (_, i) => String(i + 6).padStart(2, "0"));
  const hours = [
    ...preferred.filter((h) => hoursSeen.has(h)),
    ...[...hoursSeen].filter((h) => !preferred.includes(h)).sort(),
  ];

  const table = document.createElement("table");
  table.className = "calendar";
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  trh.appendChild(document.createElement("th"));
  for (const h of hours) {
    const th = document.createElement("th");
    th.textContent = `${h}:00`;
    trh.appendChild(th);
  }
  thead.appendChild(trh);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const d of dates) {
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.textContent = d;
    tr.appendChild(th);
    for (const h of hours) {
      const td = document.createElement("td");
      const items = pivot.get(d).get(h) || [];
      for (const text of items) {
        const div = document.createElement("div");
        div.className = "person";
        div.textContent = text;
        td.appendChild(div);
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  return table;
}

function downloadCSV() {
  const tab = activeTabDef();
  if (tab.isCalendar) {
    alert("行事曆視圖請切到「致意排程」tab 下載 CSV。");
    return;
  }
  const columns = COLUMNS_BY_SOURCE[tab.source];
  const rows = applyFilters(sourceRows());
  const header = columns.map(([, label]) => csvCell(label)).join(",");
  const body = rows.map((r) => columns.map(([k]) => csvCell(formatCell(k, r[k]))).join(",")).join("\n");
  // Excel-friendly BOM so Chinese opens correctly without manual encoding step.
  const csv = "\uFEFF" + header + "\n" + body + "\n";
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `farewell_${tab.id}_${stamp}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function csvCell(v) {
  const s = v == null ? "" : String(v);
  // RFC 4180: wrap fields containing comma/quote/newline in quotes; double internal quotes.
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function switchTab(id) {
  state.activeTab = id;
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.setAttribute("aria-selected", String(btn.dataset.tab === id));
  });
  render();
}

function readFilterValues() {
  state.filters.dates    = new Set(Array.from($("f-date").selectedOptions).map((o) => o.value));
  state.filters.halls    = new Set(Array.from($("f-hall").selectedOptions).map((o) => o.value));
  state.filters.notes    = new Set(Array.from($("f-note").selectedOptions).map((o) => o.value));
  state.filters.onlyNorth = $("f-north").checked;
  state.filters.keyword  = $("f-kw").value;
}

function resetFilters() {
  for (const id of ["f-date", "f-hall", "f-note"]) {
    Array.from($(id).options).forEach((o) => (o.selected = false));
  }
  $("f-kw").value = "";
  $("f-north").checked = true;
  readFilterValues();
  render();
}

function bindUI() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  for (const id of ["f-date", "f-hall", "f-note", "f-north"]) {
    $(id).addEventListener("change", () => { readFilterValues(); render(); });
  }
  $("f-kw").addEventListener("input", () => { readFilterValues(); render(); });
  $("btn-reset").addEventListener("click", resetFilters);
  $("btn-download").addEventListener("click", downloadCSV);
}

bindUI();
loadData();
