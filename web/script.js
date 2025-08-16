// ================= Core UI & App =================
document.addEventListener("DOMContentLoaded", () => {
  const qInput   = document.getElementById("q");
  const sendBtn  = document.getElementById("send");
  const board    = document.getElementById("board");
  const histList = document.getElementById("histList");
  const examples = document.querySelectorAll(".chip");
  const welcome  = document.getElementById("welcomeModal");
  const clearBtn = document.getElementById("clearLastBtn");

  // ---- API_BASE (meta'dan) ----
  const META_API   = document.querySelector('meta[name="api-base"]')?.content?.trim() || "";
  const API_BASE   = (META_API || "").replace(/\/+$/, "");
  const ADVICE_URL = API_BASE ? `${API_BASE}/advice` : "/advice";
  console.log("[Cortexa] ADVICE_URL =", ADVICE_URL);

  // ================= Geçmiş (soru + cevap) =================
  function getHistory() {
    try { return JSON.parse(localStorage.getItem("cx_hist") || "[]"); }
    catch { return []; }
  }
  function setHistory(list) {
    try { localStorage.setItem("cx_hist", JSON.stringify(list.slice(0, 20))); } catch {}
  }
  // entry: { q: string, a?: string, t?: number }
  function pushHistory(entry) {
    const list = getHistory();
    const t = entry.t || Date.now();
    const filtered = list.filter(it => it.q !== entry.q); // aynı soru varsa eskisini çıkar
    filtered.unshift({ q: entry.q, a: entry.a || "", t });
    setHistory(filtered);
    renderHistory();
    return t; // UI'de hid olarak kullanacağız
  }
  function popLastHistory() {
    const list = getHistory();
    if (!list.length) return null;
    const removed = list.shift(); // en güncel
    setHistory(list);
    renderHistory();
    return removed; // {q, a, t}
  }
  function renderHistory() {
    const list = getHistory();
    histList.innerHTML = list.length
      ? list.map((x, i) =>
          `<div class="hist-item" data-idx="${i}" title="Kaydı görüntüle">${x.q}</div>`
        ).join("")
      : `<div class="hist-item" style="opacity:.7">Kayıt yok</div>`;
  }
  renderHistory();

  // ================= Welcome (ilk açılış) =================
  if (!localStorage.getItem("welcomeAccepted")) {
    welcome?.setAttribute("aria-hidden", "false");
  }
  document.getElementById("welcomeAccept")?.addEventListener("click", () => {
    localStorage.setItem("welcomeAccepted", "1");
    welcome?.setAttribute("aria-hidden", "true");
  });
  document.querySelectorAll("[data-close]").forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.close;
      document.querySelector(target)?.setAttribute("aria-hidden", "true");
    });
  });

  // ================= Örnek chipler =================
  examples.forEach(chip => {
    chip.addEventListener("click", () => {
      examples.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      qInput.value = chip.dataset.q || "";
      autoRows();
      qInput.focus();
    });
  });

  // ================= Enter ile gönder =================
  qInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
  sendBtn.addEventListener("click", send);

  // ================= Otosize =================
  function autoRows() {
    qInput.style.height = "auto";
    qInput.style.height = Math.min(qInput.scrollHeight, 180) + "px";
  }
  qInput.addEventListener("input", autoRows);
  autoRows();

  // ================= Fetch yardımcıları =================
  async function robustFetch(url, options = {}, retries = 1, timeoutMs = 10000) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(url, { mode: "cors", ...options, signal: ctrl.signal });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        const err  = new Error(`HTTP ${res.status} ${res.statusText} — ${text.slice(0,180)}`);
        err.status = res.status;
        throw err;
      }
      return res;
    } catch (e) {
      if (retries > 0) {
        await new Promise(r => setTimeout(r, 400));
        return robustFetch(url, options, retries - 1, timeoutMs);
      }
      throw e;
    } finally { clearTimeout(t); }
  }

  // ================= Balon ekleme (hid ile grupla) =================
  function addMsg(html, type = "ai", hid = "") {
    const row = document.createElement("div");
    row.className = `row ${type === "user" ? "user" : "ai"}`;
    if (hid) row.dataset.hid = String(hid);

    const bubble  = document.createElement("div");
    bubble.className = "bubble";
    const card = document.createElement("div");
    card.className = "card";
    const content = document.createElement("div");
    content.className = "md";
    content.innerHTML = html;

    card.appendChild(content);
    bubble.appendChild(card);
    row.appendChild(bubble);
    board.appendChild(row);
    board.scrollTop = board.scrollHeight;

    return row;
  }

  // ================= Gönder =================
  async function send() {
    const text = qInput.value.trim();
    if (!text) return;

    // Bu konuşmanın hid'i olarak zaman damgasını önceden al
    const hid = Date.now();

    addMsg(marked.parseInline(text), "user", hid);
    qInput.value = "";
    autoRows();

    const loaderRow = addMsg(marked.parseInline("_yazıyor…_"), "ai", hid);

    const payload = {
      user_query: text,
      horizon: "",
      risk: "",
      capital: null,
      stop_pct: null,
      show_prices: true,
      suppress_disclaimer: true
    };

    sendBtn.disabled = true;
    try {
      const res = await robustFetch(ADVICE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      let data;
      try { data = await res.json(); }
      catch { throw new Error("Geçersiz JSON yanıtı"); }

      loaderRow.remove();
      const answer = data?.answer || "⚠️ Sunucu yanıtında **answer** alanı yok.";
      addMsg(marked.parse(answer), "ai", hid);

      // geçmişe (hid ile) yaz
      pushHistory({ q: text, a: answer, t: hid });

    } catch (e) {
      console.error("[Cortexa] Hata:", e);
      loaderRow.remove();
      const detail = (e?.message || "Bilinmeyen hata").slice(0, 200);
      addMsg(marked.parse(`⚠️ Yanıt alınamadı.\n\n\`\`\`\n${detail}\n\`\`\`\n`), "ai", hid);
    } finally {
      sendBtn.disabled = false;
      qInput.focus();
    }
  }

  // ================= Son Sorular Tıklama (API'ye gitmeden göster) =================
  document.getElementById("historyPanel")?.addEventListener("click", (e) => {
    const it = e.target.closest(".hist-item");
    if (!it) return;
    const idx = Number(it.dataset.idx);
    const rec = getHistory()[idx];
    if (!rec) return;

    // Kayıtlı hid yoksa güvenli taraf: yeni hid üret (replay grubu)
    const hid = rec.t || Date.now();

    addMsg(marked.parseInline(rec.q), "user", hid);
    addMsg(marked.parse(rec.a || "_Bu kayıt için cevap bulunamadı._"), "ai", hid);

    // input'a da taşı (göndermeden)
    qInput.value = rec.q;
    autoRows();
  });

  // ================= Son konuşmayı sil =================
  clearBtn?.addEventListener("click", () => {
    const removed = popLastHistory(); // en güncel kayıt
    if (!removed) return;

    const hid = removed.t ? String(removed.t) : "";
    if (hid) {
      // Bu hid'e ait tüm balonları kaldır
      [...board.querySelectorAll(`[data-hid="${hid}"]`)].forEach(n => n.remove());
    } else {
      // Güvenli fallback: sondaki 2 balonu kaldır
      const rows = board.querySelectorAll(".row");
      if (rows.length) rows[rows.length - 1].remove();
      if (rows.length > 1) rows[rows.length - 2].remove();
    }
  });
});

// ================= Theme (Açık / Koyu) =================
const THEME_KEY = "cx_theme";
function setTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(THEME_KEY, t); } catch {}
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", t === "dark" ? "#0b1220" : "#f6f7fb");
}
(function initTheme(){
  let initial = "light";
  try { initial = localStorage.getItem(THEME_KEY) || "light"; } catch {}
  setTheme(initial);
})();
(function bindThemeButton(){
  const btn = document.getElementById("themeBtn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "light";
    setTheme(cur === "light" ? "dark" : "light");
  });
})();

// ================= Footer yılı (opsiyonel alan varsa) =================
(function setYear(){
  const y = document.getElementById("year");
  if (y) y.textContent = new Date().getFullYear();
})();