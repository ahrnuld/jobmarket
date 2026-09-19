// One tooltip for the whole page. Any element with data-tip shows it on hover and on keyboard
// focus (tooltips enhance, never gate: every value is also in the table view). Line charts get
// a crosshair that snaps to the nearest x and lists every series there.

let tip: HTMLDivElement | null = null;

function ensureTip(): HTMLDivElement {
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "tooltip";
    tip.setAttribute("role", "tooltip");
    tip.hidden = true;
    document.body.appendChild(tip);
  }
  return tip;
}

function place(x: number, y: number) {
  const el = ensureTip();
  const pad = 12;
  const { width, height } = el.getBoundingClientRect();
  let left = x + pad;
  let top = y - height - pad;
  if (left + width > window.innerWidth - 8) left = x - width - pad;
  if (left < 8) left = 8;
  if (top < 8) top = y + pad;
  el.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
}

function showText(text: string, x: number, y: number) {
  const el = ensureTip();
  el.replaceChildren(document.createTextNode(text)); // labels are data: never innerHTML
  el.hidden = false;
  place(x, y);
}

function hide() {
  if (tip) tip.hidden = true;
  document.querySelectorAll<HTMLElement>(".crosshair").forEach((c) => (c.hidden = true));
}

interface LinePayload {
  x: string[];
  series: { label: string; color: string; values: (string | null)[] }[];
}

function showLine(plot: HTMLElement, clientX: number, clientY: number) {
  const data = JSON.parse(plot.dataset.line ?? "{}") as LinePayload;
  if (!data.x?.length) return;
  const box = plot.getBoundingClientRect();
  const rel = Math.min(Math.max((clientX - box.left) / box.width, 0), 1);
  const i = Math.round(rel * (data.x.length - 1));
  const cross = plot.querySelector<HTMLElement>(".crosshair");
  if (cross) {
    cross.hidden = false;
    cross.style.left = `${(data.x.length > 1 ? i / (data.x.length - 1) : 0.5) * 100}%`;
  }
  const el = ensureTip();
  const rows = data.series.map((s) => {
    const row = document.createElement("div");
    row.className = "tooltip-row";
    const key = document.createElement("span");
    key.className = "key-line";
    key.style.setProperty("--c", `var(${s.color})`);
    const value = document.createElement("strong");
    value.textContent = s.values[i] ?? "–";
    const label = document.createElement("span");
    label.textContent = s.label;
    row.append(key, value, label);
    return row;
  });
  const head = document.createElement("div");
  head.className = "tooltip-head";
  head.textContent = data.x[i];
  el.replaceChildren(head, ...rows);
  el.hidden = false;
  place(clientX, clientY);
}

export function initTooltips() {
  document.addEventListener("pointerover", (e) => {
    const t = (e.target as Element).closest<HTMLElement>("[data-tip]");
    if (t) showText(t.dataset.tip ?? "", e.clientX, e.clientY);
  });
  document.addEventListener("pointermove", (e) => {
    const plot = (e.target as Element).closest<HTMLElement>("[data-line]");
    if (plot) return showLine(plot, e.clientX, e.clientY);
    const t = (e.target as Element).closest<HTMLElement>("[data-tip]");
    if (t && tip && !tip.hidden) place(e.clientX, e.clientY);
  });
  document.addEventListener("pointerout", (e) => {
    const from = (e.target as Element).closest("[data-tip], [data-line]");
    const to = (e.relatedTarget as Element | null)?.closest("[data-tip], [data-line]");
    if (from && from !== to) hide();
  });
  document.addEventListener("focusin", (e) => {
    const t = (e.target as Element).closest<HTMLElement>("[data-tip]");
    if (t) {
      const r = t.getBoundingClientRect();
      showText(t.dataset.tip ?? "", r.left + Math.min(r.width, 200) / 2, r.top);
    }
    const plot = (e.target as Element).closest<HTMLElement>("[data-line]");
    if (plot) {
      const r = plot.getBoundingClientRect();
      showLine(plot, r.right - 1, r.top + r.height / 2); // focus shows the latest value
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
    const plot = (e.target as Element).closest<HTMLElement>("[data-line]");
    if (plot && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      const data = JSON.parse(plot.dataset.line ?? "{}") as LinePayload;
      const cur = Number(plot.dataset.cursor ?? data.x.length - 1);
      const next = Math.min(Math.max(cur + (e.key === "ArrowRight" ? 1 : -1), 0), data.x.length - 1);
      plot.dataset.cursor = String(next);
      const r = plot.getBoundingClientRect();
      showLine(plot, r.left + (data.x.length > 1 ? next / (data.x.length - 1) : 0.5) * r.width, r.top + r.height / 2);
      e.preventDefault();
    }
  });
  document.addEventListener("focusout", hide);
}
