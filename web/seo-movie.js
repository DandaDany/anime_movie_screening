(() => {
  const citySelect = document.querySelector("#movieFilterCity");
  const formatSelect = document.querySelector("#movieFilterFormat");
  const timeSelect = document.querySelector("#movieFilterTime");
  const empty = document.querySelector("#filterEmpty");
  const status = document.querySelector("#distanceStatus");
  const retry = document.querySelector("#distanceRetry");

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

  function matchesTime(chip, mode) {
    if (!mode || mode === "all") return true;
    const minute = Number(chip.dataset.minute);
    if (!Number.isFinite(minute)) return mode !== "now";
    if (mode === "morning") return minute < 720;
    if (mode === "afternoon") return minute >= 720 && minute < 1080;
    if (mode === "evening") return minute >= 1080;
    if (mode === "now") {
      const now = taipeiNowParts();
      const showDate = chip.dataset.showDate || "";
      if (showDate > now.date) return true;
      if (showDate < now.date) return false;
      return minute > now.minute;
    }
    return true;
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
    if (!cta) return;
    cta.addEventListener("click", (event) => {
      if (cta.getAttribute("aria-disabled") === "true") event.preventDefault();
    });
    for (const chip of card.querySelectorAll(".showtime-chip.is-bookable")) {
      chip.addEventListener("click", () => {
        const wasSelected = chip.getAttribute("aria-pressed") === "true";
        resetBooking(card);
        if (wasSelected) return;
        chip.classList.add("is-selected");
        chip.setAttribute("aria-pressed", "true");
        const url = chip.dataset.bookingUrl || "";
        if (!url) return;
        cta.href = url;
        cta.classList.remove("is-disabled");
        cta.setAttribute("aria-disabled", "false");
      });
    }
  }

  function applyFilters() {
    const city = citySelect?.value || "";
    const format = formatSelect?.value || "";
    const time = timeSelect?.value || "all";
    let visibleCards = 0;

    for (const card of document.querySelectorAll(".cinema-card")) {
      const cityOk = !city || card.dataset.city === city;
      let visibleShowtimes = 0;
      for (const chip of card.querySelectorAll(".showtime-chip")) {
        const formats = (chip.dataset.formats || "").split("|").filter(Boolean);
        const formatOk = !format || formats.includes(format);
        const show = cityOk && formatOk && matchesTime(chip, time);
        chip.hidden = !show;
        if (show) visibleShowtimes += 1;
      }
      const showCard = cityOk && visibleShowtimes > 0;
      card.hidden = !showCard;
      if (showCard) visibleCards += 1;
      resetBooking(card);
    }

    for (const section of document.querySelectorAll(".schedule-day")) {
      section.hidden = !section.querySelector(".cinema-card:not([hidden])");
    }
    if (empty) empty.hidden = visibleCards > 0;
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
    const userLat = position.coords.latitude;
    const userLong = position.coords.longitude;

    for (const list of document.querySelectorAll(".cinema-list")) {
      const cards = [...list.querySelectorAll(".cinema-card")];
      for (const card of cards) {
        const lat = Number(card.dataset.lat);
        const long = Number(card.dataset.long);
        const distance = Number.isFinite(lat) && Number.isFinite(long)
          ? distanceKm(userLat, userLong, lat, long)
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
      cards
        .sort((a, b) => Number(a.dataset.distance) - Number(b.dataset.distance))
        .forEach((card) => list.appendChild(card));
    }
    if (status) status.textContent = "已依你目前的位置，由近到遠排序影城。";
  }

  function requestLocation() {
    if (!navigator.geolocation) {
      if (status) status.textContent = "此瀏覽器無法取得位置，先維持預設排序。";
      return;
    }
    if (status) status.textContent = "正在取得位置，將最近的影城排在前面…";
    navigator.geolocation.getCurrentPosition(
      sortByDistance,
      () => {
        if (status) status.textContent = "未取得位置，先維持預設排序；可按「重新定位」再試一次。";
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  }

  for (const card of document.querySelectorAll(".cinema-card")) bindBooking(card);
  citySelect?.addEventListener("change", applyFilters);
  formatSelect?.addEventListener("change", applyFilters);
  timeSelect?.addEventListener("change", applyFilters);
  retry?.addEventListener("click", requestLocation);

  applyFilters();
  requestLocation();
})();
