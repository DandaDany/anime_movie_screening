(() => {
  const app = document.querySelector(".movie-map-app");
  const workspace = document.querySelector("#movieWorkspace");
  const sheetGrabber = document.querySelector("#movieSheetGrabber");
  const mapElement = document.querySelector("#movieMap");
  const searchInput = document.querySelector("#movieSearch");
  const nowToggle = document.querySelector("#movieNowToggle");
  const retryLocation = document.querySelector("#distanceRetry");
  const distanceStatus = document.querySelector("#distanceStatus");
  const resultCount = document.querySelector("#movieResultCount");
  const emptyState = document.querySelector("#filterEmpty");

  if (!app) return;

  const cards = [...document.querySelectorAll(".cinema-card")];
  const sections = [...document.querySelectorAll(".schedule-day")];
  const dateButtons = [...document.querySelectorAll("[data-filter-date]")];
  const cityButtons = [...document.querySelectorAll("[data-filter-city]")];
  const formatButtons = [...document.querySelectorAll("[data-filter-format]")];
  const chainButtons = [...document.querySelectorAll("[data-filter-chain]")];
  const periodButtons = [...document.querySelectorAll("[data-filter-period]")];

  let selectedDate = app.dataset.defaultDate || dateButtons[0]?.dataset.filterDate || "";
  let selectedCity = "";
  let selectedFormat = "";
  let selectedChain = "";
  let selectedPeriod = "all";
  let nowOnly = true;
  let keyword = "";
  let activeCard = null;
  let map = null;
  let markerLayer = null;
  let chainLogos = new Map();
  let markerByCard = new Map();
  let userPosition = null;

  const periodRanges = {
    all: [0, 1440],
    morning: [0, 720],
    afternoon: [720, 1080],
    evening: [1080, 1440],
  };

  function normalize(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replaceAll("臺", "台");
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function taipeiNowParts() {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Taipei",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(new Date());
    const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return {
      date: `${value.year}-${value.month}-${value.day}`,
      minute: Number(value.hour) * 60 + Number(value.minute),
    };
  }

  function cardDate(card) {
    return card.closest(".schedule-day")?.dataset.showDate || "";
  }

  function showtimeChips(card) {
    return [...card.querySelectorAll(".showtime-chip")];
  }

  function cardSearchText(card) {
    return normalize([
      card.dataset.name,
      card.dataset.chain,
      card.dataset.city,
      card.querySelector(".cinema-address")?.textContent,
    ].join(" "));
  }

  function cardMatchesBase(card, {
    date = selectedDate,
    city = selectedCity,
    chain = selectedChain,
    query = keyword,
  } = {}) {
    if (date && cardDate(card) !== date) return false;
    if (city && card.dataset.city !== city) return false;
    if (chain && card.dataset.chain !== chain) return false;
    if (query && !cardSearchText(card).includes(normalize(query))) return false;
    return true;
  }

  function chipMatchesTime(chip, {
    period = selectedPeriod,
    onlyFuture = nowOnly,
  } = {}) {
    const minute = Number(chip.dataset.minute);
    if (!Number.isFinite(minute)) return false;

    const [start, end] = periodRanges[period] || periodRanges.all;
    if (minute < start || minute >= end) return false;

    if (!onlyFuture) return true;
    const now = taipeiNowParts();
    const showDate = chip.dataset.showDate || "";
    if (showDate > now.date) return true;
    if (showDate < now.date) return false;
    return minute > now.minute;
  }

  function chipMatchesFormat(chip, format = selectedFormat) {
    if (!format) return true;
    return (chip.dataset.formats || "").split("|").filter(Boolean).includes(format);
  }

  function countShowtimes({
    date = selectedDate,
    city = selectedCity,
    chain = selectedChain,
    format = selectedFormat,
    period = selectedPeriod,
    onlyFuture = nowOnly,
    query = keyword,
  } = {}) {
    let count = 0;
    for (const card of cards) {
      if (!cardMatchesBase(card, { date, city, chain, query })) continue;
      for (const chip of showtimeChips(card)) {
        if (!chipMatchesFormat(chip, format)) continue;
        if (!chipMatchesTime(chip, { period, onlyFuture })) continue;
        count += 1;
      }
    }
    return count;
  }

  function updateButtonState(buttons, attribute, value) {
    for (const button of buttons) {
      const selected = button.dataset[attribute] === value;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    }
  }

  function updateFilterCounts() {
    for (const button of dateButtons) {
      const value = button.dataset.filterDate || "";
      const count = countShowtimes({ date: value });
      const badge = button.querySelector("strong");
      if (badge) badge.textContent = String(count);
    }

    for (const button of cityButtons) {
      const value = button.dataset.filterCity || "";
      const count = countShowtimes({ city: value });
      const badge = button.querySelector("strong");
      if (badge) badge.textContent = String(count);
      button.hidden = Boolean(value && count === 0 && value !== selectedCity);
    }

    for (const button of formatButtons) {
      const value = button.dataset.filterFormat || "";
      const count = countShowtimes({ format: value });
      const badge = button.querySelector("strong");
      if (badge) badge.textContent = String(count);
      button.hidden = Boolean(value && count === 0 && value !== selectedFormat);
    }

    for (const button of chainButtons) {
      const value = button.dataset.filterChain || "";
      const count = countShowtimes({ chain: value });
      const badge = button.querySelector("strong");
      if (badge) badge.textContent = String(count);
      button.hidden = Boolean(value && count === 0 && value !== selectedChain);
    }
  }

  function resetBooking(card) {
    for (const chip of card.querySelectorAll(".showtime-chip.is-bookable")) {
      chip.classList.remove("is-selected");
      chip.setAttribute("aria-pressed", "false");
    }
    const cta = card.querySelector("[data-booking-cta]");
    if (!cta) return;
    cta.removeAttribute("href");
    cta.classList.add("is-disabled");
    cta.setAttribute("aria-disabled", "true");
  }

  function bindBooking(card) {
    const cta = card.querySelector("[data-booking-cta]");
    if (cta) {
      cta.addEventListener("click", (event) => {
        event.stopPropagation();
        if (cta.getAttribute("aria-disabled") === "true") event.preventDefault();
      });
    }

    for (const link of card.querySelectorAll(".cinema-action")) {
      link.addEventListener("click", (event) => event.stopPropagation());
    }

    for (const chip of card.querySelectorAll(".showtime-chip.is-bookable")) {
      chip.addEventListener("click", (event) => {
        event.stopPropagation();
        const wasSelected = chip.getAttribute("aria-pressed") === "true";
        resetBooking(card);
        if (wasSelected) return;
        chip.classList.add("is-selected");
        chip.setAttribute("aria-pressed", "true");
        const url = chip.dataset.bookingUrl || "";
        if (!cta || !url) return;
        cta.href = url;
        cta.classList.remove("is-disabled");
        cta.setAttribute("aria-disabled", "false");
      });
    }
  }

  function applyFilters({ fitMap = true } = {}) {
    let visibleCards = 0;

    for (const section of sections) {
      const sectionSelected = section.dataset.showDate === selectedDate;
      section.hidden = !sectionSelected;

      for (const card of section.querySelectorAll(".cinema-card")) {
        const baseMatch = sectionSelected && cardMatchesBase(card);
        let visibleShowtimes = 0;

        for (const chip of showtimeChips(card)) {
          const show = baseMatch && chipMatchesFormat(chip) && chipMatchesTime(chip);
          chip.hidden = !show;
          if (show) visibleShowtimes += 1;
        }

        const showCard = baseMatch && visibleShowtimes > 0;
        card.hidden = !showCard;
        if (showCard) visibleCards += 1;
        resetBooking(card);
      }
    }

    if (resultCount) resultCount.textContent = String(visibleCards);
    if (emptyState) emptyState.hidden = visibleCards > 0;

    if (activeCard?.hidden) clearActiveCard();
    updateFilterCounts();
    renderMap({ fit: fitMap });
  }

  function markerClass(chain) {
    if (/國賓|秀泰|新光/.test(chain)) return "marker-red";
    if (/in89|喜樂|美麗新/.test(chain)) return "marker-yellow";
    return "";
  }

  function markerLabel(chain) {
    const cleaned = String(chain || "")
      .replace("影城", "")
      .replace("CINEMAS", "")
      .trim();
    return cleaned.slice(0, 1).toUpperCase() || "影";
  }

  function markerIcon(card, count) {
    const chain = card.dataset.chain || "";
    const logo = chainLogos.get(chain) || "";
    const size = Math.round(Math.min(46, 28 + Math.sqrt(Math.max(count, 1)) * 4.2));
    const totalHeight = size + 10;
    const logoStyle = logo
      ? `--marker-logo:url("${String(logo).replaceAll('"', "%22")}");`
      : "";
    const logoClass = logo ? "" : " no-logo";
    const className = markerClass(chain);
    const html = `
      <span class="movie-marker-wrap" style="--marker-size:${size}px">
        <span class="movie-marker ${className}${logoClass}" style="${logoStyle}">
          ${logo ? "" : escapeHtml(markerLabel(chain))}
        </span>
        <span class="movie-marker-count">${count}</span>
        <span class="movie-marker-stem"></span>
        <span class="movie-marker-ground"></span>
      </span>
    `;
    return L.divIcon({
      className: "",
      html,
      iconSize: [size + 16, totalHeight],
      iconAnchor: [(size + 16) / 2, totalHeight],
      tooltipAnchor: [0, -totalHeight + 4],
    });
  }

  function ensureMap() {
    if (map || !mapElement) return;
    if (!window.L) {
      mapElement.innerHTML = '<p class="map-error">地圖載入失敗，影城列表仍可正常使用。</p>';
      return;
    }

    map = L.map(mapElement, {
      zoomControl: false,
      attributionControl: true,
      minZoom: 6,
      maxZoom: 18,
    }).setView([23.75, 120.95], 7);

    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
      {
        subdomains: "abcd",
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap &copy; CARTO',
      },
    ).addTo(map);

    L.control.zoom({ position: "topleft" }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);

    const HomeControl = L.Control.extend({
      options: { position: "topleft" },
      onAdd() {
        const container = L.DomUtil.create("div", "leaflet-bar");
        const link = L.DomUtil.create("a", "", container);
        link.href = "#";
        link.title = "顯示目前篩選的所有影城";
        link.setAttribute("aria-label", "顯示目前篩選的所有影城");
        link.textContent = "⌂";
        L.DomEvent.disableClickPropagation(container);
        L.DomEvent.on(link, "click", (event) => {
          L.DomEvent.preventDefault(event);
          fitVisibleMarkers();
        });
        return container;
      },
    });
    new HomeControl().addTo(map);
  }

  function visibleCards() {
    return cards.filter((card) => !card.hidden && cardDate(card) === selectedDate);
  }

  function cardCoordinates(card) {
    const lat = card.dataset.lat ? Number(card.dataset.lat) : Number.NaN;
    const lng = card.dataset.long ? Number(card.dataset.long) : Number.NaN;
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    return [lat, lng];
  }

  function renderMap({ fit = true } = {}) {
    ensureMap();
    if (!map || !markerLayer) return;

    markerLayer.clearLayers();
    markerByCard = new Map();

    for (const card of visibleCards()) {
      const coords = cardCoordinates(card);
      if (!coords) continue;
      const count = card.querySelectorAll(".showtime-chip:not([hidden])").length;
      if (count <= 0) continue;

      const marker = L.marker(coords, {
        icon: markerIcon(card, count),
        riseOnHover: true,
      }).addTo(markerLayer);

      marker.bindTooltip(card.dataset.name || card.dataset.chain || "影城", {
        direction: "top",
        opacity: 0.9,
      });
      marker.on("click", () => focusCard(card, { source: "map" }));
      markerByCard.set(card, marker);
    }

    refreshActiveMarker();
    if (fit) fitVisibleMarkers();
  }

  function fitVisibleMarkers() {
    if (!map) return;
    const latLngs = [...markerByCard.values()].map((marker) => marker.getLatLng());
    if (!latLngs.length) {
      map.setView([23.75, 120.95], 7);
      return;
    }
    if (latLngs.length === 1) {
      map.setView(latLngs[0], 13, { animate: false });
      return;
    }

    const mobile = window.matchMedia("(max-width: 820px)").matches;
    map.fitBounds(L.latLngBounds(latLngs), {
      paddingTopLeft: [36, 36],
      paddingBottomRight: [36, mobile ? Math.min(300, workspace?.getBoundingClientRect().height || 220) : 36],
      maxZoom: 12,
      animate: false,
    });
  }

  function clearActiveCard() {
    if (activeCard) activeCard.classList.remove("is-map-active");
    activeCard = null;
    refreshActiveMarker();
  }

  function refreshActiveMarker() {
    for (const [card, marker] of markerByCard) {
      const element = marker.getElement()?.querySelector(".movie-marker");
      element?.classList.toggle("is-selected", card === activeCard);
    }
  }

  function focusCard(card, { source = "list" } = {}) {
    if (card.hidden) return;
    if (activeCard && activeCard !== card) activeCard.classList.remove("is-map-active");
    activeCard = card;
    card.classList.add("is-map-active");
    refreshActiveMarker();

    const marker = markerByCard.get(card);
    if (marker && map) {
      map.setView(marker.getLatLng(), Math.max(map.getZoom(), 14), { animate: false });
    }

    if (source === "map") {
      if (window.matchMedia("(max-width: 820px)").matches) {
        setMobileSheetHeight(window.innerHeight * 0.72);
      }
      card.scrollIntoView({ block: "center", behavior: "smooth" });
      card.focus({ preventScroll: true });
    } else if (window.matchMedia("(max-width: 820px)").matches) {
      setMobileSheetHeight(window.innerHeight * 0.48);
    }
  }

  function bindCardFocus(card) {
    card.addEventListener("click", (event) => {
      if (event.target.closest("a, button")) return;
      focusCard(card);
    });
    card.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.target.closest("a, button") && event.target !== card) return;
      event.preventDefault();
      focusCard(card);
    });
  }

  function distanceKm(lat1, lon1, lat2, lon2) {
    const toRad = (value) => value * Math.PI / 180;
    const earth = 6371;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * earth * Math.asin(Math.sqrt(a));
  }

  function sortByDistance(position) {
    userPosition = position;
    const userLat = position.coords.latitude;
    const userLng = position.coords.longitude;

    for (const section of sections) {
      const list = section.querySelector(".cinema-list");
      if (!list) continue;
      const sectionCards = [...list.querySelectorAll(".cinema-card")];

      for (const card of sectionCards) {
        const coords = cardCoordinates(card);
        const distance = coords
          ? distanceKm(userLat, userLng, coords[0], coords[1])
          : Number.POSITIVE_INFINITY;
        card.dataset.distance = String(distance);
        const label = card.querySelector(".distance-label");
        if (label && Number.isFinite(distance)) {
          label.textContent = distance < 1
            ? `${Math.round(distance * 1000)} 公尺`
            : `${distance.toFixed(1)} 公里`;
          label.hidden = false;
        }
      }

      sectionCards
        .sort((a, b) => Number(a.dataset.distance) - Number(b.dataset.distance))
        .forEach((card) => list.appendChild(card));
    }

    if (distanceStatus) distanceStatus.textContent = "已依你目前的位置，由近到遠排序影城。";
  }

  function requestLocation() {
    if (!navigator.geolocation) {
      if (distanceStatus) distanceStatus.textContent = "此瀏覽器無法取得位置，先維持預設排序。";
      return;
    }
    if (distanceStatus) distanceStatus.textContent = "正在取得位置，將最近的影城排在前面…";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        sortByDistance(position);
        applyFilters({ fitMap: false });
      },
      () => {
        if (distanceStatus) distanceStatus.textContent = "未取得位置，先維持預設排序；可按「重新定位」再試一次。";
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  }

  function setMobileSheetHeight(px) {
    if (!workspace || !window.matchMedia("(max-width: 820px)").matches) return;
    const min = window.innerHeight * 0.38;
    const max = window.innerHeight * 0.86;
    workspace.style.height = `${Math.max(min, Math.min(max, px))}px`;
  }

  function initSheetDrag() {
    if (!workspace || !sheetGrabber) return;
    let startY = 0;
    let startHeight = 0;
    let dragging = false;

    sheetGrabber.addEventListener("pointerdown", (event) => {
      if (!window.matchMedia("(max-width: 820px)").matches) return;
      dragging = true;
      startY = event.clientY;
      startHeight = workspace.getBoundingClientRect().height;
      sheetGrabber.setPointerCapture(event.pointerId);
      event.preventDefault();
    });

    sheetGrabber.addEventListener("pointermove", (event) => {
      if (!dragging) return;
      setMobileSheetHeight(startHeight + startY - event.clientY);
    });

    const finish = (event) => {
      if (!dragging) return;
      dragging = false;
      if (sheetGrabber.hasPointerCapture(event.pointerId)) {
        sheetGrabber.releasePointerCapture(event.pointerId);
      }
      const ratio = workspace.getBoundingClientRect().height / window.innerHeight;
      const snaps = [0.44, 0.64, 0.84];
      const target = snaps.reduce((best, value) =>
        Math.abs(value - ratio) < Math.abs(best - ratio) ? value : best,
      );
      setMobileSheetHeight(window.innerHeight * target);
    };

    sheetGrabber.addEventListener("pointerup", finish);
    sheetGrabber.addEventListener("pointercancel", finish);
  }

  function selectButtonGroup(buttons, key, value) {
    for (const button of buttons) {
      const selected = button.dataset[key] === value;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    }
  }

  for (const card of cards) {
    bindBooking(card);
    bindCardFocus(card);
  }

  for (const button of dateButtons) {
    button.addEventListener("click", () => {
      selectedDate = button.dataset.filterDate || selectedDate;
      selectButtonGroup(dateButtons, "filterDate", selectedDate);
      clearActiveCard();
      applyFilters();
    });
  }

  for (const button of cityButtons) {
    button.addEventListener("click", () => {
      selectedCity = button.dataset.filterCity || "";
      selectButtonGroup(cityButtons, "filterCity", selectedCity);
      clearActiveCard();
      applyFilters();
    });
  }

  for (const button of formatButtons) {
    button.addEventListener("click", () => {
      selectedFormat = button.dataset.filterFormat || "";
      selectButtonGroup(formatButtons, "filterFormat", selectedFormat);
      clearActiveCard();
      applyFilters();
    });
  }

  for (const button of chainButtons) {
    button.addEventListener("click", () => {
      selectedChain = button.dataset.filterChain || "";
      selectButtonGroup(chainButtons, "filterChain", selectedChain);
      clearActiveCard();
      applyFilters();
    });
  }

  for (const button of periodButtons) {
    button.addEventListener("click", () => {
      selectedPeriod = button.dataset.filterPeriod || "all";
      selectButtonGroup(periodButtons, "filterPeriod", selectedPeriod);
      clearActiveCard();
      applyFilters();
    });
  }

  nowToggle?.addEventListener("click", () => {
    nowOnly = !nowOnly;
    nowToggle.classList.toggle("is-selected", nowOnly);
    nowToggle.setAttribute("aria-pressed", nowOnly ? "true" : "false");
    clearActiveCard();
    applyFilters();
  });

  searchInput?.addEventListener("input", () => {
    keyword = searchInput.value || "";
    clearActiveCard();
    applyFilters();
  });

  retryLocation?.addEventListener("click", requestLocation);

  initSheetDrag();
  ensureMap();

  fetch("data/chain_logos.json", { cache: "force-cache" })
    .then((response) => response.ok ? response.json() : {})
    .then((data) => {
      chainLogos = new Map(Object.entries(data || {}));
      applyFilters();
    })
    .catch(() => applyFilters());

  requestLocation();

  window.addEventListener("resize", () => {
    map?.invalidateSize({ animate: false });
  });
})();
