const fs = require("fs");
const vm = require("vm");
const path = require("path");

const appPath = path.join(__dirname, "..", "web", "app.js");
const source = fs.readFileSync(appPath, "utf8");

function section(startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  if (start < 0 || end < 0) {
    throw new Error(`Unable to extract section: ${startMarker}`);
  }
  return source.slice(start, end);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const helperSource = section(
  "function directShowtimeBookingUrl",
  "function popupHtml",
);
const sandbox = {
  URL,
  URLSearchParams,
  selectedMovieTitle: "測試電影",
  selectedDate: "2026-09-27",
  selectedFormat: "IMAX",
  selectedChain: "威秀影城 / VIESHOW",
  selectedCity: "臺北市",
  timePeriod: "all",
  timeMode: "auto",
  timeEarliest: 0,
  activeSearchInput: () => ({ value: "" }),
};
vm.createContext(sandbox);
vm.runInContext(helperSource, sandbox);

const booking1 =
  "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode=1&txtSessionId=111";
const booking2 =
  "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode=1&txtSessionId=222";

assert(
  sandbox.directVieshowBookingUrl({ booking_url: booking1 }).includes("txtSessionId=111"),
  "Direct VIESHOW booking URL should be accepted",
);
assert(
  sandbox.directVieshowBookingUrl({
    booking_url: "https://www.vscinemas.com.tw/ShowTimes/",
  }) === "",
  "Generic VIESHOW showtime URL must not be treated as direct booking",
);

assert(
  sandbox.directShowtimeBookingUrl({
    booking_url: "https://www.miramarcinemas.tw/Booking/TicketType?id=movie-id&session=437885",
  }).includes("session=437885"),
  "Miramar session-specific booking URL should be accepted",
);
assert(
  sandbox.directShowtimeBookingUrl({
    booking_url: "https://www.miramarcinemas.tw/timetable",
  }) === "",
  "Generic Miramar timetable must not be treated as direct booking",
);
assert(
  sandbox.directShowtimeBookingUrl({
    booking_url: "https://ticket.centuryasia.com.tw/Ximen/buyticket_process.aspx?ProgramID=0000215&eventsn=90&computerid=16358",
  }).includes("computerid=16358"),
  "Century Asia session-specific booking URL should be accepted",
);
assert(
  sandbox.directShowtimeBookingUrl({
    booking_url: "https://www.broadway-cineplex.com.tw/book.html?obj=Taipei",
  }) === "",
  "Broadway cinema landing URL must not be treated as direct booking",
);
const seatPreviewUrl = sandbox.vieshowSeatPreviewUrl(
  { booking_url: booking1 },
  { properties: { location_id: 7 } },
);
const seatPreviewQuery = new URL(
  seatPreviewUrl,
  "https://example.test/",
).searchParams;
assert(
  seatPreviewQuery.get("cinemacode") === "1" &&
    seatPreviewQuery.get("session") === "111",
  "Seat preview URL should preserve the selected VIESHOW session",
);
assert(
  seatPreviewQuery.get("movie") === "測試電影" &&
    seatPreviewQuery.get("date") === "2026-09-27" &&
    seatPreviewQuery.get("format") === "IMAX" &&
    seatPreviewQuery.get("location") === "7",
  "Seat preview URL should carry map return state",
);

class MockClassList {
  constructor(...names) {
    this.values = new Set(names);
  }
  add(name) {
    this.values.add(name);
  }
  toggle(name, force) {
    if (force) this.values.add(name);
    else this.values.delete(name);
  }
  remove(name) {
    this.values.delete(name);
  }
  contains(name) {
    return this.values.has(name);
  }
}

function mockChip(time, url, seatPreviewUrl) {
  return {
    dataset: {
      showtimeTime: time,
      bookingUrl: url,
      seatPreviewUrl,
    },
    classList: new MockClassList("st-chip-select"),
    attributes: { "aria-pressed": "false" },
    listeners: {},
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    getAttribute(name) {
      return this.attributes[name] ?? null;
    },
    addEventListener(name, fn) {
      this.listeners[name] = fn;
    },
  };
}

function mockLink({ href = "", labelSelector, labelText, dataset = {}, classes = [] }) {
  const label = { textContent: labelText };
  return {
    href,
    dataset: { ...dataset },
    attributes: href ? { href } : {},
    classList: new MockClassList(...classes),
    listeners: {},
    querySelector(selector) {
      return selector === labelSelector ? label : null;
    },
    addEventListener(name, fn) {
      this.listeners[name] = fn;
    },
    getAttribute(name) {
      if (name === "href") return this.href || null;
      return this.attributes[name] ?? null;
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
      if (name === "href") this.href = value;
    },
    removeAttribute(name) {
      delete this.attributes[name];
      if (name === "href") this.href = "";
    },
    _label: label,
  };
}

const chip1 = mockChip(
  "19:25",
  booking1,
  "seat-preview.html?cinemacode=1&session=111",
);
const chip2 = mockChip(
  "21:40",
  booking2,
  "seat-preview.html?cinemacode=1&session=222",
);

const broadwayPreview =
  "https://www.broadway-cineplex.com.tw/quick-view.html?obj=Zhubei,0000946,2026-09-27,19-20,0010";
const chip3 = mockChip("19:20", "", broadwayPreview);

const cta = mockLink({
  labelSelector: "[data-booking-cta-label]",
  labelText: "場次入口",
  classes: ["popup-booking-cta", "is-disabled"],
});
cta.attributes["aria-disabled"] = "true";

const officialUrl = "https://www.vscinemas.com.tw/";
const official = mockLink({
  href: officialUrl,
  labelSelector: "[data-official-cta-label]",
  labelText: "官方網站",
  dataset: { officialHref: officialUrl },
  classes: ["popup-link-ghost"],
});

const root = {
  querySelectorAll(selector) {
    return selector === ".st-chip-select" ? [chip1, chip2, chip3] : [];
  },
  querySelector(selector) {
    if (selector === "[data-booking-cta]") return cta;
    if (selector === "[data-official-cta]") return official;
    return null;
  },
};

sandbox.bindShowtimeBookingInteraction(root);

let prevented = false;
cta.listeners.click({
  preventDefault() {
    prevented = true;
  },
});
assert(prevented, "CTA must be inert before a showtime is selected");
assert(cta._label.textContent === "場次入口", "Initial booking CTA should say 場次入口");
assert(official._label.textContent === "官方網站", "Initial secondary CTA should say 官方網站");
assert(official.href === officialUrl, "Initial secondary CTA should keep official URL");

chip1.listeners.click();
assert(chip1.classList.contains("is-selected"), "First selected showtime should be highlighted");
assert(!chip2.classList.contains("is-selected"), "Other showtimes should not be selected");
assert(chip1.attributes["aria-pressed"] === "true", "Selected showtime aria-pressed should be true");
assert(cta.href.includes("txtSessionId=111"), "Booking CTA should use selected first showtime URL");
assert(cta.attributes["aria-disabled"] === "false", "Booking CTA should enable after selection");
assert(cta._label.textContent === "前往訂票", "Booking CTA label should become 前往訂票");
assert(!cta.classList.contains("is-disabled"), "Booking CTA disabled style should be removed");
assert(
  official._label.textContent === "座位表入口",
  "Official CTA should become 座位表入口 after selecting a showtime",
);
{
  const url = new URL(official.href, "https://example.test/");
  assert(
    url.searchParams.get("cinemacode") === "1" &&
      url.searchParams.get("session") === "111" &&
      url.searchParams.get("movie") === "測試電影" &&
      url.searchParams.get("date") === "2026-09-27" &&
      url.searchParams.get("format") === "IMAX" &&
      url.searchParams.get("location") === "7",
    "Seat preview CTA should follow selected session and preserve map state",
  );
}

chip2.listeners.click();
assert(!chip1.classList.contains("is-selected"), "Previous showtime should be unselected");
assert(chip2.classList.contains("is-selected"), "Second showtime should become selected");
assert(cta.href.includes("txtSessionId=222"), "Booking CTA should switch to newly selected showtime URL");
{
  const url = new URL(official.href, "https://example.test/");
  assert(
    url.searchParams.get("cinemacode") === "1" &&
      url.searchParams.get("session") === "222",
    "Seat preview CTA should switch to newly selected showtime",
  );
}
assert(
  cta.attributes["aria-label"] === "21:40 場次前往訂票",
  "Booking CTA aria-label should follow selected time",
);

chip3.listeners.click();
assert(!chip1.classList.contains("is-selected"), "Booking showtime should clear when preview-only showtime is selected");
assert(!chip2.classList.contains("is-selected"), "Previous booking showtime should clear when preview-only showtime is selected");
assert(chip3.classList.contains("is-selected"), "Preview-only showtime should be selectable");
assert(cta.href === "", "Preview-only showtime must not invent an official booking URL");
assert(cta.attributes["aria-disabled"] === "true", "Primary booking CTA should stay disabled for preview-only showtime");
assert(cta._label.textContent === "場次入口", "Primary CTA should remain generic for preview-only showtime");
assert(official.href === broadwayPreview, "Secondary CTA should point to the exact provider seat preview");
assert(official._label.textContent === "座位表入口", "Preview-only selection should expose 座位表入口");

chip3.listeners.click();
assert(!chip3.classList.contains("is-selected"), "Preview-only showtime should toggle off");
assert(official.href === officialUrl, "Toggling preview-only showtime off should restore official URL");

chip2.listeners.click();
chip2.listeners.click();
assert(!chip1.classList.contains("is-selected"), "No showtime should remain selected after toggling off");
assert(!chip2.classList.contains("is-selected"), "Selected showtime should toggle off on second click");
assert(chip2.attributes["aria-pressed"] === "false", "Toggled-off showtime aria-pressed should be false");
assert(cta.href === "", "Booking CTA href should be removed after toggling off");
assert(cta.attributes["aria-disabled"] === "true", "Booking CTA should disable after toggling off");
assert(cta._label.textContent === "場次入口", "Booking CTA should return to 場次入口");
assert(official.href === officialUrl, "Secondary CTA should return to official URL");
assert(official._label.textContent === "官方網站", "Secondary CTA should return to 官方網站");

const previewOnlyChip = mockChip("19:20", "", broadwayPreview);
const previewOnlyOfficial = mockLink({
  href: "https://www.broadway-cineplex.com.tw/",
  labelSelector: "[data-official-cta-label]",
  labelText: "官方網站",
  dataset: { officialHref: "https://www.broadway-cineplex.com.tw/" },
  classes: ["popup-link-ghost"],
});
const previewOnlyRoot = {
  querySelectorAll(selector) {
    return selector === ".st-chip-select" ? [previewOnlyChip] : [];
  },
  querySelector(selector) {
    if (selector === "[data-booking-cta]") return null;
    if (selector === "[data-official-cta]") return previewOnlyOfficial;
    return null;
  },
};
sandbox.bindShowtimeBookingInteraction(previewOnlyRoot);
previewOnlyChip.listeners.click();
assert(previewOnlyChip.classList.contains("is-selected"), "Preview-only showtime should work without a dynamic booking CTA");
assert(previewOnlyOfficial.href === broadwayPreview, "Preview-only cinema should expose the exact seat preview while keeping its static booking entry");
assert(previewOnlyOfficial._label.textContent === "座位表入口", "Preview-only cinema should relabel the secondary CTA");
assert(
  source.includes('data-booking-cta-label>場次入口</span>'),
  "Initial booking CTA should still render 場次入口",
);
assert(
  source.includes('data-official-cta-label>官方網站</span>'),
  "Initial secondary CTA should render 官方網站",
);
assert(
  source.includes('class="st-chip st-chip-select"'),
  "Booking or seat-preview showtimes should render as selectable chips, not outbound links",
);
assert(
  source.includes("const locationLink = hasDirectBooking"),
  "Preview-only cinemas should keep their normal booking entry instead of rendering a disabled primary CTA",
);

console.log("frontend_showtime_booking_cta_test: ok");
