(() => {
  const DATA_URL = "data/movie_discovery.json";
  const EXIT_MS = 190;

  const overlay = document.querySelector("#movieDiscovery");
  const nowGrid = document.querySelector("#nowShowingGrid");
  const upcomingGrid = document.querySelector("#comingSoonGrid");
  const upcomingEmpty = document.querySelector("#comingSoonEmpty");
  const toast = document.querySelector("#movieDiscoveryToast");
  const movieSelect = document.querySelector("#movieSelect");
  const dateChips = document.querySelector("#dateChips");

  if (!overlay || !nowGrid || !upcomingGrid || !movieSelect || !dateChips) return;

  let catalog = [];
  let lookaheadDays = 7;
  let toastTimer = null;
  let renderTimer = null;

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

  function upcomingWithinWindow(item) {
    const target = parseUtcDate(item.target_date);
    const today = parseUtcDate(todayIso());
    if (!target || !today) return false;
    const diffDays = Math.round((target - today) / 86400000);
    return diffDays >= 0 && diffDays <= lookaheadDays;
  }

  function posterCard(item, displayTitle, kind) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "movie-card";
    button.dataset.movieTitle = displayTitle;
    button.dataset.kind = kind;
    button.setAttribute("aria-label", displayTitle);

    const poster = document.createElement("span");
    poster.className = "movie-card__poster";
    poster.dataset.fallback = displayTitle;

    const img = document.createElement("img");
    img.src = item?.poster_url || "";
    img.alt = "";
    img.decoding = "async";
    img.loading = kind === "now" ? "eager" : "lazy";
    img.referrerPolicy = "no-referrer";
    if (!item?.poster_url) poster.classList.add("is-missing");
    img.addEventListener("error", () => poster.classList.add("is-missing"));
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

  function closeDiscovery() {
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

  async function selectUpcoming(item) {
    const directOption = currentOptionForItem(item);
    if (directOption) {
      window.trackEvent?.("movie_discovery_select", {
        movie_title: item.title,
        source: "upcoming_current_date",
      });
      selectOption(directOption);
      return;
    }

    const originalDate = selectedDate();
    const dates = availableDateValues();
    const candidates = [
      ...(item.target_date && dates.includes(item.target_date) ? [item.target_date] : []),
      ...dates.filter((value) => value !== item.target_date),
    ];

    for (const showDate of candidates) {
      const button = findDateButton(showDate);
      if (!button) continue;
      if (showDate !== selectedDate()) button.click();
      const option = await waitForOption(item);
      if (option) {
        window.trackEvent?.("movie_discovery_select", {
          movie_title: item.title,
          source: "upcoming_future_date",
          show_date: showDate,
        });
        selectOption(option);
        return;
      }
    }

    if (originalDate && originalDate !== selectedDate()) {
      findDateButton(originalDate)?.click();
    }
    showToast("尚未有上映資訊");
    window.trackEvent?.("movie_discovery_unavailable", { movie_title: item.title });
  }

  function render() {
    const optionRows = [...movieSelect.options]
      .map((option) => ({ option, title: option.value || option.textContent || "" }))
      .filter(({ title }) => optionHasMovieValue(title));

    const nowCards = [];
    const nowNormalized = new Set();

    for (const { title } of optionRows) {
      const item = findCatalogItem(title);
      nowCards.push(posterCard(item, title, "now"));
      if (item) aliasesFor(item).forEach((alias) => nowNormalized.add(alias));
      else nowNormalized.add(normalizeTitle(title));
    }
    nowGrid.replaceChildren(...nowCards);

    const upcomingItems = catalog
      .filter((item) => upcomingWithinWindow(item))
      .filter((item) => !aliasesFor(item).some((alias) => nowNormalized.has(alias)))
      .sort((a, b) =>
        String(a.target_date || "").localeCompare(String(b.target_date || "")) ||
        String(a.title || "").localeCompare(String(b.title || ""), "zh-Hant"),
      );

    upcomingGrid.replaceChildren(
      ...upcomingItems.map((item) => posterCard(item, item.title, "upcoming")),
    );
    upcomingEmpty.hidden = upcomingItems.length > 0;

    if (!nowCards.length) {
      const empty = document.createElement("p");
      empty.className = "movie-grid-empty";
      empty.textContent = "目前沒有可顯示的上映電影";
      nowGrid.replaceChildren(empty);
    }
  }

  nowGrid.addEventListener("click", (event) => {
    const card = event.target.closest(".movie-card");
    if (!card) return;
    const item = findCatalogItem(card.dataset.movieTitle);
    const option = item
      ? currentOptionForItem(item)
      : [...movieSelect.options].find(
          (candidate) =>
            normalizeTitle(candidate.value || candidate.textContent) ===
            normalizeTitle(card.dataset.movieTitle),
        );
    if (!option) return;
    window.trackEvent?.("movie_discovery_select", {
      movie_title: card.dataset.movieTitle,
      source: "now_showing",
    });
    selectOption(option);
  });

  upcomingGrid.addEventListener("click", (event) => {
    const card = event.target.closest(".movie-card");
    if (!card) return;
    const item = findCatalogItem(card.dataset.movieTitle);
    if (item) selectUpcoming(item);
  });

  const observer = new MutationObserver(() => {
    window.clearTimeout(renderTimer);
    renderTimer = window.setTimeout(render, 30);
  });
  observer.observe(movieSelect, { childList: true, subtree: true });

  window.MuseDiscovery = Object.freeze({
    open: openDiscovery,
    close: closeDiscovery,
  });

  document.documentElement.classList.add("discovery-active");
  window.setTimeout(() => window.dispatchEvent(new Event("resize")), 0);

  fetch(DATA_URL, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`movie discovery ${response.status}`);
      return response.json();
    })
    .then((data) => {
      catalog = Array.isArray(data.movies) ? data.movies : [];
      lookaheadDays = Number.isFinite(Number(data.lookahead_days))
        ? Number(data.lookahead_days)
        : 7;
      render();
    })
    .catch((error) => {
      console.error("Movie discovery feed failed", error);
      render();
    });
})();
