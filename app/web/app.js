const IGNORE_TYPES = new Set([
  "task_tracker_update",
  "status_bar_update",
  "status_card",
  "chat_input_update",
  "progress_bar",
  "progress_display",
  "button",
  "button_group",
  "tool_execution",
  "log_viewer",
]);

const thread = document.getElementById("thread");
const emptyState = document.getElementById("empty-state");
const composer = document.getElementById("composer");
const promptEl = document.getElementById("prompt");
const sendBtn = document.getElementById("send");
const rail = document.getElementById("rail");
const scrim = document.getElementById("scrim");
const menuBtn = document.getElementById("menu-btn");

let conversationId = null;
let busy = false;

function formatDate(value) {
  if (!value) return "—";
  const d = String(value).slice(0, 10);
  return d;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMarkdown(raw) {
  let text = escapeHtml(raw || "");
  text = text.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  text = text.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  text = text.replace(/\n\n/g, "</p><p>");
  text = text.replace(/\n/g, "<br>");
  return `<div class="md"><p>${text}</p></div>`;
}

function hideEmpty() {
  if (emptyState) emptyState.remove();
}

function appendUser(text) {
  hideEmpty();
  const el = document.createElement("div");
  el.className = "msg msg-user";
  el.textContent = text;
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
}

function appendBotWrap() {
  hideEmpty();
  const el = document.createElement("div");
  el.className = "msg msg-bot";
  thread.appendChild(el);
  return el;
}

function setPending(on, parent) {
  const host = parent || thread;
  let node = host.querySelector(".pending");
  if (on) {
    if (!node) {
      node = document.createElement("p");
      node.className = "pending";
      node.setAttribute("role", "status");
      node.innerHTML =
        '<span class="spinner" aria-hidden="true"></span><span>Looking in the filings…</span>';
      host.appendChild(node);
    }
  } else if (node) {
    node.remove();
  }
  thread.scrollTop = thread.scrollHeight;
}

function insertIntoComposer(text) {
  const current = promptEl.value.trim();
  promptEl.value = current ? `${current} ${text}` : text;
  promptEl.focus();
  closeRail();
}

function renderCompanies(rows) {
  const root = document.getElementById("company-list");
  root.innerHTML = "";
  if (!rows.length) {
    root.innerHTML = '<p class="chip-empty">No companies match.</p>';
    return;
  }
  rows.forEach((row) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip";
    btn.setAttribute("role", "option");
    const symbol = row.symbol || "";
    btn.innerHTML = `<span class="chip-title">${escapeHtml(row.company_name || "")}</span>
      <span class="chip-meta">${escapeHtml(symbol || "no ticker")}</span>`;
    btn.addEventListener("click", () => insertIntoComposer(symbol || row.company_name));
    root.appendChild(btn);
  });
}

function renderTags(rows) {
  const root = document.getElementById("tag-list");
  root.innerHTML = "";
  if (!rows.length) {
    root.innerHTML = '<p class="chip-empty">No tags match.</p>';
    return;
  }
  rows.forEach((row) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip";
    btn.setAttribute("role", "option");
    const qname = row.qname || "";
    btn.innerHTML = `<span class="chip-title">${escapeHtml(qname)}</span>`;
    btn.addEventListener("click", () => insertIntoComposer(qname));
    root.appendChild(btn);
  });
}

async function loadSummary() {
  const res = await fetch("/api/catalog/summary");
  if (!res.ok) throw new Error("summary failed");
  const data = await res.json();
  document.getElementById("stat-companies").textContent = data.company_count ?? "—";
  document.getElementById("stat-filings").textContent = data.filing_count ?? "—";
  document.getElementById("stat-tags").textContent = data.tag_count ?? "—";
  const start = formatDate(data.period_start);
  const end = formatDate(data.period_end);
  document.getElementById("stat-period").textContent =
    start === "—" && end === "—" ? "—" : `${start} – ${end}`;
}

async function loadCompanies(q) {
  const url = new URL("/api/catalog/companies", window.location.origin);
  if (q) url.searchParams.set("q", q);
  const res = await fetch(url);
  const data = await res.json();
  renderCompanies(data.companies || []);
}

async function loadTags(q) {
  const url = new URL("/api/catalog/tags", window.location.origin);
  if (q) url.searchParams.set("q", q);
  const res = await fetch(url);
  const data = await res.json();
  renderTags(data.tags || []);
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function renderTable(payload, target) {
  const data = payload.data || {};
  const rows = data.data || data.rows || [];
  const columns = data.columns || (rows[0] ? Object.keys(rows[0]) : []);
  if (!columns.length) return;
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  const table = document.createElement("table");
  table.className = "data";
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
  const tbody = document.createElement("tbody");
  rows.slice(0, 100).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = columns
      .map((c) => `<td>${escapeHtml(row[c] == null ? "" : row[c])}</td>`)
      .join("");
    tbody.appendChild(tr);
  });
  table.appendChild(thead);
  table.appendChild(tbody);
  wrap.appendChild(table);
  target.appendChild(wrap);
}

function renderChart(payload, target) {
  const fig = payload.data || {};
  const traces = fig.data;
  const layout = fig.layout || {};
  if (!Array.isArray(traces)) return;
  const el = document.createElement("div");
  el.className = "chart";
  target.appendChild(el);
  const config = Object.assign(
    {
      responsive: true,
      displayModeBar: true,
      scrollZoom: true,
      displaylogo: false,
    },
    fig.config && typeof fig.config === "object" ? fig.config : {}
  );
  if (window.Plotly) {
    window.Plotly.newPlot(el, traces, layout, config);
  }
}

function renderText(payload, target) {
  const data = payload.data || {};
  const content = data.content || payload.content || "";
  if (!content || !String(content).trim()) return;
  const div = document.createElement("div");
  div.innerHTML = data.markdown ? renderMarkdown(content) : escapeHtml(content);
  target.appendChild(div);
}

function renderNotice(payload, target) {
  const data = payload.data || {};
  const message = data.message || "";
  if (!message) return;
  const el = document.createElement("div");
  el.className = "banner";
  el.textContent = message;
  target.appendChild(el);
}

function addProvenanceRow(dl, label, value) {
  if (value == null || value === "") return;
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = Array.isArray(value) ? value.join(", ") : String(value);
  dl.appendChild(dt);
  dl.appendChild(dd);
}

function renderProvenance(payload, target) {
  const data = payload.data || {};
  const details = document.createElement("details");
  details.className = "provenance";
  const summary = document.createElement("summary");
  summary.textContent = "How these numbers were produced";
  details.appendChild(summary);
  const dl = document.createElement("dl");
  addProvenanceRow(dl, "Source", data.source);
  addProvenanceRow(dl, "Formula", data.formula);
  addProvenanceRow(dl, "Tags", data.tags);
  addProvenanceRow(dl, "Metric", data.metric);
  addProvenanceRow(dl, "Period", data.period);
  addProvenanceRow(dl, "Rounding", data.rounding);
  details.appendChild(dl);
  if (data.sql) {
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.textContent = data.sql;
    pre.appendChild(code);
    details.appendChild(pre);
  }
  target.appendChild(details);
}

function handleChunk(payload, target) {
  if (!payload) return;
  if (payload.conversation_id) conversationId = payload.conversation_id;
  if (payload.type === "error") {
    const el = document.createElement("div");
    el.className = "banner";
    el.textContent = (payload.data && payload.data.message) || "Something went wrong.";
    target.appendChild(el);
    return;
  }
  const rich = payload.rich;
  if (!rich || typeof rich !== "object") return;
  const type = rich.type;
  if (IGNORE_TYPES.has(type)) return;
  if (type === "text") renderText(rich, target);
  else if (type === "dataframe" || type === "table") renderTable(rich, target);
  else if (type === "chart") renderChart(rich, target);
  else if (type === "notification" || type === "alert") renderNotice(rich, target);
  else if (type === "provenance") renderProvenance(rich, target);
}

async function sendMessage(text) {
  if (busy) return;
  busy = true;
  sendBtn.disabled = true;
  appendUser(text);
  const bot = appendBotWrap();
  bot.setAttribute("aria-busy", "true");
  setPending(true, bot);

  const body = { message: text };
  if (conversationId) body.conversation_id = conversationId;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) throw new Error("Chat request failed");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trim())
          .join("");
        if (!line || line === "[DONE]") continue;
        let payload;
        try {
          payload = JSON.parse(line);
        } catch (err) {
          continue;
        }
        handleChunk(payload, bot);
        thread.scrollTop = thread.scrollHeight;
      }
    }
  } catch (err) {
    setPending(false, bot);
    const el = document.createElement("div");
    el.className = "banner";
    el.textContent = "Could not reach StockJarvis. Try again.";
    bot.appendChild(el);
  } finally {
    setPending(false, bot);
    bot.removeAttribute("aria-busy");
    busy = false;
    sendBtn.disabled = false;
    promptEl.focus();
  }
}

function openRail() {
  rail.classList.add("open");
  scrim.hidden = false;
  menuBtn.setAttribute("aria-expanded", "true");
}

function closeRail() {
  rail.classList.remove("open");
  scrim.hidden = true;
  menuBtn.setAttribute("aria-expanded", "false");
}

menuBtn.addEventListener("click", () => {
  if (rail.classList.contains("open")) closeRail();
  else openRail();
});
scrim.addEventListener("click", closeRail);

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = promptEl.value.trim();
  if (!text) return;
  promptEl.value = "";
  sendMessage(text);
});

promptEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

document.getElementById("company-search").addEventListener(
  "input",
  debounce((event) => loadCompanies(event.target.value.trim()), 200)
);
document.getElementById("tag-search").addEventListener(
  "input",
  debounce((event) => loadTags(event.target.value.trim()), 200)
);

loadSummary().catch(() => {
  document.getElementById("stat-companies").textContent = "—";
});
loadCompanies("");
loadTags("");
