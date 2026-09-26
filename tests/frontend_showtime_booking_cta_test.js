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
  "function directVieshowBookingUrl",
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
    return selector === ".st-chip-select[data-booking-url]" ? [chip1, chip2] : [];
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

chip2.listeners.click();
assert(!chip1.classList.contains("is-selected"), "No showtime should remain selected after toggling off");
assert(!chip2.classList.contains("is-selected"), "Selected showtime should toggle off on second click");
assert(chip2.attributes["aria-pressed"] === "false", "Toggled-off showtime aria-pressed should be false");
assert(cta.href === "", "Booking CTA href should be removed after toggling off");
assert(cta.attributes["aria-disabled"] === "true", "Booking CTA should disable after toggling off");
assert(cta._label.textContent === "場次入口", "Booking CTA should return to 場次入口");
assert(official.href === officialUrl, "Secondary CTA should return to official URL");
assert(official._label.textContent === "官方網站", "Secondary CTA should return to 官方網站");

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
  "Direct showtimes should render as selectable chips, not outbound links",
);

console.log("frontend_showtime_booking_cta_test: ok");
