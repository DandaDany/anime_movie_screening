(() => {
  const panel = document.querySelector("#cinemaListPanel");
  const list = document.querySelector("#cinemaList");
  const count = document.querySelector("#cinemaListCount");
  if (!panel || !list) return;

  let lastFeatures = [];
  let userPosition = null;
  let activeLocationId = null;

  function coordinates(feature) {
    const coords = feature?.geometry?.coordinates;
    if (!Array.isArray(coords) || coords.length < 2) return null;
    const lng = Number(coords[0]);
    const lat = Number(coords[1]);
    return Number.isFinite(lat) && Number.isFinite(lng) ? [lat, lng] : null;
  }

  function distanceKm(lat1, lon1, lat2, lon2) {
    const toRad = (value) => (value * Math.PI) / 180;
    const earth = 6371;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * earth * Math.asin(Math.sqrt(a));
  }

  function sortedFeatures(features) {
    if (!userPosition) return [...features];
    const lat = Number(userPosition.coords?.latitude);
    const lng = Number(userPosition.coords?.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return [...features];

    return [...features].sort((a, b) => {
      const ac = coordinates(a);
      const bc = coordinates(b);
      const ad = ac ? distanceKm(lat, lng, ac[0], ac[1]) : Number.POSITIVE_INFINITY;
      const bd = bc ? distanceKm(lat, lng, bc[0], bc[1]) : Number.POSITIVE_INFINITY;
      return ad - bd;
    });
  }

  function renderTimes(feature) {
    const showtimes = Array.isArray(feature?.properties?.showtimes)
      ? feature.properties.showtimes
      : [];
    const wrap = document.createElement("div");
    wrap.className = "cinema-list-times";
    for (const showtime of showtimes) {
      const time = String(showtime?.time || "").trim();
      if (!time) continue;
      const chip = document.createElement("span");
      chip.className = "cinema-list-time";
      chip.textContent = time;
      wrap.appendChild(chip);
    }
    return wrap;
  }

  function render(features = lastFeatures) {
    lastFeatures = Array.isArray(features) ? features : [];
    const integration = window.MuseMapIntegration;
    if (!integration) return;

    const sorted = sortedFeatures(lastFeatures);
    const fragment = document.createDocumentFragment();

    for (const feature of sorted) {
      const props = feature?.properties || {};
      const locationId = Number(props.location_id);
      const article = document.createElement("article");
      article.className = "cinema-list-card";
      article.dataset.locationId = String(locationId || "");

      const name = document.createElement("h3");
      name.className = "cinema-list-name";
      name.textContent = props.location_name || props.map_name || "影城";
      article.append(name, renderTimes(feature));

      if (locationId === activeLocationId) article.classList.add("is-active");
      article.addEventListener("click", () => {
        activeLocationId = locationId;
        setActive(locationId);
        integration.focusLocation(locationId);
      });

      fragment.appendChild(article);
    }

    list.replaceChildren(fragment);
    if (count) count.textContent = String(sorted.length);
    panel.classList.toggle("is-empty", sorted.length === 0);

    if (!sorted.length) {
      const empty = document.createElement("p");
      empty.className = "cinema-list-empty";
      empty.textContent = "目前沒有符合篩選條件的影城";
      list.appendChild(empty);
    }
  }

  function setActive(locationId) {
    activeLocationId = Number(locationId) || null;
    for (const card of list.querySelectorAll(".cinema-list-card")) {
      const selected = Number(card.dataset.locationId) === activeLocationId;
      card.classList.toggle("is-active", selected);
      if (selected) card.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  window.addEventListener("muse:filtered-cinemas", (event) => {
    render(event.detail?.features || []);
  });

  window.addEventListener("muse:cinema-focus", (event) => {
    setActive(event.detail?.locationId);
  });

  if (navigator.geolocation?.getCurrentPosition) {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        userPosition = position;
        render();
      },
      () => {},
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  }
})();
