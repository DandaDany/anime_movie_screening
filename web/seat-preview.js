const DATA_URL = "data/vieshow_seat_previews.json";

function params() {
  const query = new URLSearchParams(window.location.search);
  return {
    cinema: query.get("cinemacode") || "",
    session: query.get("session") || "",
  };
}

function seatKey(cinema, session) {
  return `${cinema}:${session}`;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function formatUpdatedAt(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function seatCell(cell) {
  const el = document.createElement("span");
  el.className = `seat-cell ${cell.type || "gap"}`;

  if (cell.type === "gap") {
    el.setAttribute("aria-hidden", "true");
    return el;
  }

  if (cell.type === "wheelchair") {
    el.textContent = "♿";
    el.title = cell.seat || "輪椅位";
    el.setAttribute("aria-label", cell.seat || "輪椅位");
    return el;
  }

  const seat = cell.seat || "";
  el.textContent = seat.replace(/^[A-Z]+/i, "") || seat;
  el.title = `${seat} ${cell.type === "sold" ? "已售" : "可售"}`;
  el.setAttribute("aria-label", el.title);
  return el;
}

function renderPreview(preview) {
  const notice = document.getElementById("notice");
  const content = document.getElementById("seatContent");
  notice.textContent = "座位資訊為最近一次爬蟲更新的快照，實際可售狀態仍以威秀訂票頁為準。";
  notice.classList.remove("error");

  setText("movieTitle", preview.movie || "威秀座位表");
  setText(
    "sessionMeta",
    [preview.datetime, preview.cinema, preview.auditorium].filter(Boolean).join(" · "),
  );
  setText("availableCount", preview.available ?? "–");
  setText("soldCount", preview.sold ?? "–");
  setText("ordinaryCount", preview.ordinary_seats ?? "–");
  setText(
    "updatedAt",
    preview.fetched_at ? `座位快照更新：${formatUpdatedAt(preview.fetched_at)}` : "",
  );

  const map = document.getElementById("seatMap");
  map.replaceChildren();
  for (const row of preview.rows || []) {
    const rowEl = document.createElement("div");
    rowEl.className = "seat-row";
    for (const cell of row) rowEl.appendChild(seatCell(cell));
    map.appendChild(rowEl);
  }

  content.hidden = false;
}

function renderError(message) {
  setText("movieTitle", "目前沒有座位快照");
  setText("sessionMeta", "");
  const notice = document.getElementById("notice");
  notice.textContent = message;
  notice.classList.add("error");
  document.getElementById("seatContent").hidden = true;
}

async function main() {
  const { cinema, session } = params();
  if (!cinema || !session) {
    renderError("缺少場次資訊，請回到電影地圖重新選擇場次。");
    return;
  }

  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const preview = payload.previews?.[seatKey(cinema, session)];
    if (!preview) {
      renderError("這個場次目前沒有座位快照，請以威秀訂票頁顯示為準。");
      return;
    }
    renderPreview(preview);
  } catch (error) {
    console.error(error);
    renderError("座位快照暫時無法載入，請稍後再試。");
  }
}

main();
