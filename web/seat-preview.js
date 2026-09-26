const DATA_URL = "data/vieshow_seat_previews.json";

function params() {
  const query = new URLSearchParams(window.location.search);
  return {
    cinema: query.get("cinemacode") || "",
    session: query.get("session") || "",
    movie: query.get("movie") || "",
    date: query.get("date") || "",
    format: query.get("format") || "",
    chain: query.get("chain") || "",
    city: query.get("city") || "",
    period: query.get("period") || "",
    timeMode: query.get("timeMode") || "",
    earliest: query.get("earliest") || "",
    q: query.get("q") || "",
    location: query.get("location") || "",
  };
}

function seatKey(cinema, session) {
  return cinema + ":" + session;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function formatUpdatedAt(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Taipei",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );

  return parts.month + "/" + parts.day + " " + parts.hour + ":" + parts.minute;
}

function officialBookingUrl(cinema, session) {
  if (!cinema || !session) return "";
  const query = new URLSearchParams({
    cinemacode: cinema,
    txtSessionId: session,
  });
  return "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?" + query.toString();
}

function mapReturnUrl(state) {
  const query = new URLSearchParams({ restore: "1" });
  for (const key of [
    "movie",
    "date",
    "format",
    "chain",
    "city",
    "period",
    "timeMode",
    "earliest",
    "q",
    "location",
  ]) {
    if (state[key]) query.set(key, state[key]);
  }
  return "./?" + query.toString();
}

function configureBackLink(state) {
  const link = document.getElementById("backToMap");
  if (link) link.href = mapReturnUrl(state);
}

function renderNotice(preview, state) {
  const notice = document.getElementById("notice");
  notice.replaceChildren();
  notice.classList.remove("error");

  const updated = formatUpdatedAt(preview.fetched_at);
  notice.appendChild(
    document.createTextNode(
      "座位資訊為" +
        (updated || "最近一次") +
        "更新的資訊，實際可售狀態仍以威秀訂票頁為準。",
    ),
  );

  const officialUrl = officialBookingUrl(state.cinema, state.session);
  if (officialUrl) {
    notice.appendChild(document.createTextNode(" "));
    const link = document.createElement("a");
    link.className = "official-entry";
    link.href = officialUrl;
    link.target = "_blank";
    link.rel = "noreferrer";

    const text = document.createTextNode("官網入口 ");
    const icon = document.createElement("span");
    icon.className = "official-entry-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "↗";

    link.append(text, icon);
    notice.appendChild(link);
  }
}

function seatCell(cell) {
  const el = document.createElement("span");
  el.className = "seat-cell " + (cell.type || "gap");

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
  el.title = seat + " " + (cell.type === "sold" ? "已售" : "可售");
  el.setAttribute("aria-label", el.title);
  return el;
}

function renderPreview(preview, state) {
  const content = document.getElementById("seatContent");
  renderNotice(preview, state);

  setText("movieTitle", preview.movie || "威秀座位表");
  setText(
    "sessionMeta",
    [preview.datetime, preview.cinema, preview.auditorium].filter(Boolean).join(" · "),
  );
  setText("availableCount", preview.available ?? "–");
  setText("soldCount", preview.sold ?? "–");
  setText("ordinaryCount", preview.ordinary_seats ?? "–");

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
  const state = params();
  const { cinema, session } = state;
  configureBackLink(state);

  if (!cinema || !session) {
    renderError("缺少場次資訊，請回到電影地圖重新選擇場次。");
    return;
  }

  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const payload = await response.json();
    const preview = payload.previews?.[seatKey(cinema, session)];
    if (!preview) {
      renderError("這個場次目前沒有座位快照，請以威秀訂票頁顯示為準。");
      return;
    }
    renderPreview(preview, state);
  } catch (error) {
    console.error(error);
    renderError("座位快照暫時無法載入，請稍後再試。");
  }
}

main();
