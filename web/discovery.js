(() => {
  const DATA_URL = "data/movie_discovery.json";
  const MAP_DATA_URL = "data/locations.geojson";
  const EXIT_MS = 190;

  const overlay = document.querySelector("#movieDiscovery");
  const nowGrid = document.querySelector("#nowShowingGrid");
  const upcomingGrid = document.querySelector("#comingSoonGrid");
  const upcomingEmpty = document.querySelector("#comingSoonEmpty");
  const toast = document.querySelector("#movieDiscoveryToast");
  const noTodayDialog = document.querySelector("#movieNoTodayDialog");
  const noTodayTitle = document.querySelector("#movieNoTodayTitle");
  const noTodayQuestion = document.querySelector("#movieNoTodayQuestion");
  const noTodayNo = document.querySelector("#movieNoTodayNo");
  const noTodayYes = document.querySelector("#movieNoTodayYes");
  const movieSelect = document.querySelector("#movieSelect");
  const dateChips = document.querySelector("#dateChips");

  if (
    !overlay ||
    !nowGrid ||
    !upcomingGrid ||
    !movieSelect ||
    !dateChips ||
    !noTodayDialog ||
    !noTodayNo ||
    !noTodayYes
  ) return;

  let catalog = [];
  let availabilityByTitle = new Map();
  let showtimeMinutesByTitleAndDate = new Map();
  let availabilityReady = false;
  let toastTimer = null;
  let renderTimer = null;
  let dialogResolve = null;
  let dialogPreviousFocus = null;

  function normalizeTitle(value) {
    return String(value || "")
      .normalize("NFKC")
      .toLowerCase()
      .replaceAll("臺", "台")
      .replace(/[\s：:!！?？〈〉《》「」『』（）()・．.、,，\-—_'"“”‘’♪]/g, "");
  }

  function aliasesFor(item) {
    return [item?.title, ...(Array.isArray(item?.aliases) ? item.aliases : [])]
      .filter(Boolean)
      .map(normalizeTitle);
  }

  function matchesItem(title, item) {
    const normalized = normalizeTitle(title);
    return aliasesFor(item).includes(normalized);
  }

  function findCatalogItem(title) {
    return catalog.find((item) => matchesItem(title, item)) || null;
  }

  function featureHasRealShowtime(feature) {
    const props = feature?.properties || {};
    return Number(props.showtime_count) > 0
      || (Array.isArray(props.showtimes) && props.showtimes.length > 0);
  }

  function parseShowtimeMinute(showtime) {
    const match = /^(\d{1,2}):(\d{2})$/.exec(String(showtime?.time || "").trim());
    if (!match) return null;
    const hour = Number(match[1]);
    const minute = Number(match[2]);
    if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
    return hour * 60 + minute;
  }

  function indexAvailability(mapData) {
    availabilityByTitle = new Map();
    showtimeMinutesByTitleAndDate = new Map();
    const byTitle = mapData?.movie_features_by_date || {};
    for (const [title, byDate] of Object.entries(byTitle)) {
      const normalizedTitle = normalizeTitle(title);
      const dates = [];
      const minutesByDate = new Map();
      for (const [showDate, features] of Object.entries(byDate || {})) {
        if (!showDate || !Array.isArray(features) || !features.some(featureHasRealShowtime)) continue;
        dates.push(showDate);
        const minutes = features
          .flatMap((feature) => Array.isArray(feature?.properties?.showtimes) ? feature.properties.showtimes : [])
          .map(parseShowtimeMinute)
          .filter(Number.isFinite);
        minutesByDate.set(showDate, minutes);
      }
      availabilityByTitle.set(normalizedTitle, dates.sort());
      showtimeMinutesByTitleAndDate.set(normalizedTitle, minutesByDate);
    }
    availabilityReady = true;
  }

  function availabilityDatesForItem(item) {
    const keys = new Set(aliasesFor(item));
    const dates = new Set();
    for (const [titleKey, titleDates] of availabilityByTitle) {
      if (!keys.has(titleKey)) continue;
      for (const showDate of titleDates) dates.add(showDate);
    }
    return [...dates].sort();
  }

  function showtimeMinutesForItemDate(item, showDate) {
    const keys = new Set(aliasesFor(item));
    const minutes = new Set();
    for (const [titleKey, minutesByDate] of showtimeMinutesByTitleAndDate) {
      if (!keys.has(titleKey)) continue;
      for (const minute of minutesByDate.get(showDate) || []) minutes.add(minute);
    }
    return [...minutes];
  }

  function canEnterMapForItem(item) {
    if (!availabilityReady) return true;
    const today = todayIso();
    const dates = availabilityDatesForItem(item);
    if (dates.some((showDate) => showDate > today)) return true;
    if (!dates.includes(today)) return false;
    const nowMinutes = window.MuseTimeFilter?.taipeiNowMinutes?.();
    if (!Number.isFinite(nowMinutes)) return true;
    return showtimeMinutesForItemDate(item, today).some((minute) => minute > nowMinutes);
  }

  function optionHasMovieValue(value) {
    const text = String(value || "").trim();
    return Boolean(text && text !== "今日無上映電影");
  }

  function currentOptionForItem(item) {
    return [...movieSelect.options].find((option) => {
      const value = option.value || option.textContent || "";
      return optionHasMovieValue(value) && matchesItem(value, item);
    });
  }

  function parseUtcDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
    if (!match) return null;
    return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  }

  function todayIso() {
    return window.MuseDateState?.taipeiToday?.() || new Date().toISOString().slice(0, 10);
  }

  function isNowShowing(item) {
    const target = parseUtcDate(item.target_date);
    const today = parseUtcDate(todayIso());
    return !target || !today || target <= today;
  }

  function isUpcoming(item) {
    const target = parseUtcDate(item.target_date);
    const today = parseUtcDate(todayIso());
    return Boolean(target && today && target > today);
  }

  function posterCard(item, displayTitle, kind) {
    const button = document.createElement("a");
    button.href = `movies/${encodeURIComponent(String(item?.id ?? ""))}/`;
    button.className = "movie-card";
    button.dataset.movieTitle = displayTitle;
    button.dataset.kind = kind;
    button.setAttribute("aria-label", displayTitle);

    const poster = document.createElement("span");
    poster.className = "movie-card__poster";
    poster.dataset.fallback = displayTitle;
    if (item?.poster_fit === "contain") poster.classList.add("is-contain");

    const img = document.createElement("img");
    img.src = item?.poster_url || "";
    img.alt = "";
    img.decoding = "async";
    img.loading = kind === "now" ? "eager" : "lazy";
    img.referrerPolicy = "no-referrer";
    if (!item?.poster_url) poster.classList.add("is-missing");
    img.addEventListener("load", () => poster.classList.remove("is-missing"));
    img.addEventListener("error", () => {
      const fallbackUrl = String(item?.poster_fallback_url || "").trim();
      if (fallbackUrl && img.dataset.posterFallbackTried !== "1") {
        img.dataset.posterFallbackTried = "1";
        img.src = fallbackUrl;
        return;
      }
      poster.classList.add("is-missing");
    });
    poster.appendChild(img);

    const title = document.createElement("span");
    title.className = "movie-card__title";
    title.textContent = displayTitle;

    button.append(poster, title);
    return button;
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.hidden = false;
    toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, 2200);
  }

  function resolveNoTodayDialog(value) {
    if (noTodayDialog.hidden) return;
    noTodayDialog.hidden = true;
    noTodayDialog.setAttribute("aria-hidden", "true");
    const resolve = dialogResolve;
    dialogResolve = null;
    const focusTarget = dialogPreviousFocus;
    dialogPreviousFocus = null;
    focusTarget?.focus?.({ preventScroll: true });
    resolve?.(value);
  }

  function confirmOtherDate({
    title = "今天沒有剩餘場次",
    question = "是否看其他日期？",
  } = {}) {
    if (dialogResolve) resolveNoTodayDialog(false);
    dialogPreviousFocus = document.activeElement;
    if (noTodayTitle) noTodayTitle.textContent = title;
    if (noTodayQuestion) noTodayQuestion.textContent = question;
    noTodayDialog.hidden = false;
    noTodayDialog.setAttribute("aria-hidden", "false");
    noTodayYes.focus({ preventScroll: true });
    return new Promise((resolve) => {
      dialogResolve = resolve;
    });
  }

  noTodayNo.addEventListener("click", () => resolveNoTodayDialog(false));
  noTodayYes.addEventListener("click", () => resolveNoTodayDialog(true));
  noTodayDialog.addEventListener("click", (event) => {
    if (event.target === noTodayDialog) resolveNoTodayDialog(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !noTodayDialog.hidden) {
      event.preventDefault();
      resolveNoTodayDialog(false);
    }
  });

  function closeDiscovery() {
    resolveNoTodayDialog(false);
    overlay.classList.add("is-leaving");
    window.setTimeout(() => {
      overlay.hidden = true;
      overlay.classList.remove("is-leaving");
      overlay.setAttribute("aria-hidden", "true");
      document.documentElement.classList.remove("discovery-active");
      window.dispatchEvent(new Event("resize"));
    }, EXIT_MS);
  }

  function openDiscovery() {
    resolveNoTodayDialog(false);
    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    overlay.classList.remove("is-leaving");
    overlay.scrollTop = 0;
    document.documentElement.classList.add("discovery-active");
    render();
    window.setTimeout(() => window.dispatchEvent(new Event("resize")), 0);
  }

  function selectOption(option) {
    if (!option) return false;
    movieSelect.value = option.value;
    movieSelect.dispatchEvent(new Event("change", { bubbles: true }));
    closeDiscovery();
    return true;
  }

  function findDateButton(showDate) {
    return [...dateChips.querySelectorAll("button[data-date]")].find(
      (button) => button.dataset.date === showDate,
    );
  }

  function selectedDate() {
    return dateChips.querySelector("button[data-date].is-selected")?.dataset.date || "";
  }

  function availableDateValues() {
    return [...dateChips.querySelectorAll("button[data-date]")]
      .map((button) => button.dataset.date)
      .filter(Boolean);
  }

  function waitForOption(item, timeoutMs = 320) {
    return new Promise((resolve) => {
      const immediate = currentOptionForItem(item);
      if (immediate) {
        resolve(immediate);
        return;
      }
      const observer = new MutationObserver(() => {
        const found = currentOptionForItem(item);
        if (!found) return;
        observer.disconnect();
        resolve(found);
      });
      observer.observe(movieSelect, { childList: true, subtree: true });
      window.setTimeout(() => {
        observer.disconnect();
        resolve(currentOptionForItem(item));
      }, timeoutMs);
    });
  }

  async function optionOnDate(item, showDate) {
    const button = findDateButton(showDate);
    if (!button) return null;
    if (showDate !== selectedDate()) button.click();
    return waitForOption(item);
  }

  async function restoreDate(showDate) {
    if (!showDate || showDate === selectedDate()) return;
    const button = findDateButton(showDate);
    if (!button) return;
    button.click();
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  }

  async function enterOtherDate(item, preferredDate = "") {
    const today = todayIso();
    const knownDates = availabilityReady
      ? availabilityDatesForItem(item)
      : availableDateValues();
    const dates = knownDates.filter((value) => value !== today);
    const candidates = [
      ...(preferredDate && preferredDate !== today && dates.includes(preferredDate)
        ? [preferredDate]
        : []),
      ...(item.target_date && item.target_date !== today && dates.includes(item.target_date)
        ? [item.target_date]
        : []),
      ...dates,
    ].filter((value, index, all) => all.indexOf(value) === index);

    for (const showDate of candidates) {
      const option = await optionOnDate(item, showDate);
      if (!option) continue;
      window.trackEvent?.("movie_discovery_select", {
        movie_title: item.title,
        source: "other_date",
        show_date: showDate,
      });
      selectOption(option);
      return true;
    }
    return false;
  }

  async function selectNowShowing(item) {
    const originalDate = selectedDate();
    const today = todayIso();
    const knownDates = availabilityReady ? availabilityDatesForItem(item) : availableDateValues();
    const hasTodaySchedule = knownDates.includes(today);
    const futureDates = knownDates.filter((showDate) => showDate > today);
    const todayButton = findDateButton(today);

    let todayOption = null;
    if (todayButton && (!availabilityReady || hasTodaySchedule)) {
      todayOption = await optionOnDate(item, today);
    }

    if (todayOption) {
      window.trackEvent?.("movie_discovery_select", {
        movie_title: item.title,
        source: "now_showing_today",
        show_date: today,
      });
      selectOption(todayOption);
      return;
    }

    await restoreDate(originalDate);

    if (availabilityReady && futureDates.length === 0) {
      render();
      showToast("目前沒有可查詢場次");
      return;
    }

    const shouldSeeOtherDate = await confirmOtherDate({
      title: hasTodaySchedule ? "今日剩餘場次已結束" : "今天沒有排映場次",
      question: "是否看其他日期？",
    });
    if (!shouldSeeOtherDate) {
      window.trackEvent?.("movie_discovery_other_date_declined", {
        movie_title: item.title,
      });
      return;
    }

    const entered = await enterOtherDate(item, originalDate);
    if (!entered) {
      await restoreDate(originalDate);
      showToast("其他日期也尚無上映資訊");
      window.trackEvent?.("movie_discovery_unavailable", {
        movie_title: item.title,
        source: "now_showing_other_date",
      });
    }
  }

  function upcomingReleaseLabel(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
    if (!match) return "";
    const todayMatch = /^(\d{4})-/.exec(todayIso());
    const currentYear = todayMatch ? todayMatch[1] : "";
    return match[1] === currentYear
      ? `${match[2]}/${match[3]}`
      : `${match[1]}/${match[2]}/${match[3]}`;
  }

  function selectUpcoming(item) {
    const releaseLabel = upcomingReleaseLabel(item.target_date);
    showToast(releaseLabel ? `預計${releaseLabel}上映，敬請期待！` : "敬請期待！");
    window.trackEvent?.("movie_discovery_upcoming_notice", {
      movie_title: item.title,
      target_date: item.target_date || "",
    });
  }

  function render() {
    const nowItems = catalog.filter((item) => isNowShowing(item) && canEnterMapForItem(item));
    nowGrid.replaceChildren(
      ...nowItems.map((item) => posterCard(item, item.title, "now")),
    );

    const upcomingItems = catalog
      .filter(isUpcoming)
      .sort((a, b) =>
        String(a.target_date || "").localeCompare(String(b.target_date || "")) ||
        String(a.title || "").localeCompare(String(b.title || ""), "zh-Hant"),
      );

    upcomingGrid.replaceChildren(
      ...upcomingItems.map((item) => posterCard(item, item.title, "upcoming")),
    );
    upcomingEmpty.hidden = upcomingItems.length > 0;

    if (!nowItems.length) {
      const empty = document.createElement("p");
      empty.className = "movie-grid-empty";
      empty.textContent = "目前沒有可顯示的上映電影";
      nowGrid.replaceChildren(empty);
    }
  }

  // Movie cards are real links. The homepage is the discovery layer; the
  // movie detail page is the next step, and the map is entered from there.

  const observer = new MutationObserver(() => {
    window.clearTimeout(renderTimer);
    renderTimer = window.setTimeout(render, 30);
  });
  observer.observe(movieSelect, { childList: true, subtree: true });

  window.MuseDiscovery = Object.freeze({
    open: openDiscovery,
    close: closeDiscovery,
  });

  const restoringMapState =
    new URLSearchParams(window.location.search).get("restore") === "1";
  if (restoringMapState) {
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    document.documentElement.classList.remove("discovery-active");
  } else {
    document.documentElement.classList.add("discovery-active");
  }
  window.setTimeout(() => window.dispatchEvent(new Event("resize")), 0);

  Promise.all([
    fetch(DATA_URL, { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error(`movie discovery ${response.status}`);
      return response.json();
    }),
    fetch(MAP_DATA_URL, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`map availability ${response.status}`);
        return response.json();
      })
      .catch((error) => {
        console.warn("Movie discovery availability feed failed", error);
        return null;
      }),
  ])
    .then(([data, mapData]) => {
      catalog = Array.isArray(data.movies) ? data.movies : [];
      if (mapData) indexAvailability(mapData);
      render();
    })
    .catch((error) => {
      console.error("Movie discovery feed failed", error);
      render();
    });
})();
