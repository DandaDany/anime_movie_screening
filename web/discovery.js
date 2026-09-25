(() => {
  const CATALOG_URL = "data/movie_posters.json";
  const UPCOMING_WINDOW_DAYS = 7;
  const EXIT_MS = 190;

  const overlay = document.querySelector("#movieDiscovery");
  const nowGrid = document.querySelector("#nowShowingGrid");
  const upcomingGrid = document.querySelector("#comingSoonGrid");
  const upcomingEmpty = document.querySelector("#comingSoonEmpty");
  const toast = document.querySelector("#movieDiscoveryToast");
  const movieSelect = document.querySelector("#movieSelect");
  const dateChips = document.querySelector("#dateChips");

  if (!overlay || !nowGrid || !upcomingGrid || !movieSelect || !dateChips) return;

  document.documentElement.classList.add("discovery-active");
  window.setTimeout(() => window.dispatchEvent(new Event("resize")), 0);

  let catalog = [];
  let toastTimer = null;
  let renderTimer = null;
  const params = new URLSearchParams(window.location.search);
  // UI review helper only: lets a screenshot show the historical "upcoming" shelf
  // without changing production data or the user's actual map date.
  const previewDate = /^\d{4}-\d{2}-\d{2}$/.test(params.get("discoveryPreviewDate") || "")
    ? params.get("discoveryPreviewDate")
    : "";
  const previewLayout = params.get("discoveryPreviewLayout") === "1";

  function normalizeTitle(value) {
    return String(value || "")
      .normalize("NFKC")
      .toLowerCase()
      .replaceAll("臺", "台")
      .replace(/[\s：:!！?？〈〉《》「」『』（）()・．.、,，\-—_'"“”‘’♪]/g, "");
  }

  function aliasesFor(item) {
    return [item.title, ...(Array.isArray(item.aliases) ? item.aliases : [])]
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

  function currentOptions() {
    return [...movieSelect.options]
      .map((option) => ({ title: option.value || option.textContent || "", option }))
      .filter(({ title }) => title && optionHasMovieValue(title));
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

  function discoveryToday() {
    if (previewDate) return previewDate;
    return window.MuseDateState?.taipeiToday?.() || new Date().toISOString().slice(0, 10);
  }

  function isUpcomingWithinWindow(item) {
    const release = parseUtcDate(item.release_date);
    const today = parseUtcDate(discoveryToday());
    if (!release || !today) return false;
    const diffDays = Math.round((release - today) / 86400000);
    return diffDays >= 1 && diffDays <= UPCOMING_WINDOW_DAYS;
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

  function hideDiscovery() {
    overlay.classList.add("is-leaving");
    window.setTimeout(() => {
      overlay.hidden = true;
      overlay.classList.remove("is-leaving");
      overlay.setAttribute("aria-hidden", "true");
      document.documentElement.classList.remove("discovery-active");
      window.dispatchEvent(new Event("resize"));
    }, EXIT_MS);
  }

  function selectOption(option) {
    if (!option) return false;
    movieSelect.value = option.value;
    movieSelect.dispatchEvent(new Event("change", { bubbles: true }));
    hideDiscovery();
    return true;
  }

  function findDateButton(showDate) {
    return [...dateChips.querySelectorAll("button[data-date]")].find(
      (button) => button.dataset.date === showDate,
    );
  }

  function selectedDateButton() {
    return dateChips.querySelector("button[data-date].is-selected");
  }

  function waitForOption(item, timeoutMs = 900) {
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
      selectOption(directOption);
      return;
    }

    const targetDateButton = findDateButton(item.release_date);
    if (!targetDateButton) {
      showToast("尚未有上映資訊");
      window.trackEvent?.("movie_discovery_unavailable", { movie_title: item.title });
      return;
    }

    const previousDateButton = selectedDateButton();
    targetDateButton.click();
    const option = await waitForOption(item);
    if (option) {
      window.trackEvent?.("movie_discovery_select", {
        movie_title: item.title,
        source: "upcoming",
      });
      selectOption(option);
      return;
    }

    if (previousDateButton && previousDateButton !== targetDateButton) {
      previousDateButton.click();
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
      if (!item) {
        nowCards.push(posterCard(null, title, "now"));
        nowNormalized.add(normalizeTitle(title));
        continue;
      }
      nowCards.push(posterCard(item, title, "now"));
      aliasesFor(item).forEach((alias) => nowNormalized.add(alias));
    }

    nowGrid.replaceChildren(...nowCards);

    let upcomingItems;
    if (previewLayout) {
      upcomingItems = catalog
        .filter((item) => !aliasesFor(item).some((alias) => nowNormalized.has(alias)))
        .slice(0, 4);
    } else {
      upcomingItems = catalog.filter((item) => {
        if (!isUpcomingWithinWindow(item)) return false;
        // In production, a movie that is already selectable in the map belongs only to "正在上映".
        if (previewDate) return true;
        return !aliasesFor(item).some((alias) => nowNormalized.has(alias));
      });
    }

    const upcomingCards = upcomingItems.map((item) => posterCard(item, item.title, "upcoming"));
    upcomingGrid.replaceChildren(...upcomingCards);
    upcomingEmpty.hidden = upcomingCards.length > 0;

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
    const title = card.dataset.movieTitle;
    const option = [...movieSelect.options].find(
      (candidate) => normalizeTitle(candidate.value || candidate.textContent) === normalizeTitle(title),
    );
    if (!option) return;
    window.trackEvent?.("movie_discovery_select", { movie_title: title, source: "now_showing" });
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

  fetch(CATALOG_URL, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`poster catalog ${response.status}`);
      return response.json();
    })
    .then((data) => {
      catalog = Array.isArray(data.movies) ? data.movies : [];
      render();
    })
    .catch((error) => {
      console.error("Movie discovery poster catalog failed", error);
      render();
    });
})();
