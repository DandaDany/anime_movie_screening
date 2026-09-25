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
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(helperSource, sandbox);

assert(
  sandbox.directVieshowBookingUrl({
    booking_url:
      "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode=1&txtSessionId=111",
  }).includes("txtSessionId=111"),
  "Direct VIESHOW booking URL should be accepted",
);
assert(
  sandbox.directVieshowBookingUrl({
    booking_url: "https://www.vscinemas.com.tw/ShowTimes/",
  }) === "",
  "Generic VIESHOW showtime URL must not be treated as direct booking",
);

class MockClassList {
  constructor(...names) {
    this.values = new Set(names);
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

function mockChip(time, url) {
  return {
    dataset: { showtimeTime: time, bookingUrl: url },
    classList: new MockClassList("st-chip-select"),
    attributes: { "aria-pressed": "false" },
    listeners: {},
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    addEventListener(name, fn) {
      this.listeners[name] = fn;
    },
  };
}

const chip1 = mockChip(
  "19:25",
  "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode=1&txtSessionId=111",
);
const chip2 = mockChip(
  "21:40",
  "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode=1&txtSessionId=222",
);
const label = { textContent: "場次入口" };
const cta = {
  href: "",
  attributes: { "aria-disabled": "true" },
  classList: new MockClassList("popup-booking-cta", "is-disabled"),
  listeners: {},
  querySelector(selector) {
    return selector === "[data-booking-cta-label]" ? label : null;
  },
  addEventListener(name, fn) {
    this.listeners[name] = fn;
  },
  getAttribute(name) {
    return this.attributes[name] ?? null;
  },
  setAttribute(name, value) {
    this.attributes[name] = value;
  },
};

const root = {
  querySelectorAll(selector) {
    return selector === ".st-chip-select[data-booking-url]" ? [chip1, chip2] : [];
  },
  querySelector(selector) {
    return selector === "[data-booking-cta]" ? cta : null;
  },
};

sandbox.bindShowtimeBookingInteraction(root);

let prevented = false;
cta.listeners.click({ preventDefault() { prevented = true; } });
assert(prevented, "CTA must be inert before a showtime is selected");

chip1.listeners.click();
assert(chip1.classList.contains("is-selected"), "First selected showtime should be highlighted");
assert(!chip2.classList.contains("is-selected"), "Other showtimes should not be selected");
assert(chip1.attributes["aria-pressed"] === "true", "Selected showtime aria-pressed should be true");
assert(cta.href.includes("txtSessionId=111"), "CTA should use selected first showtime URL");
assert(cta.attributes["aria-disabled"] === "false", "CTA should enable after selection");
assert(label.textContent === "前往訂票", "CTA label should become 前往訂票");
assert(!cta.classList.contains("is-disabled"), "CTA disabled style should be removed");

chip2.listeners.click();
assert(!chip1.classList.contains("is-selected"), "Previous showtime should be unselected");
assert(chip2.classList.contains("is-selected"), "Second showtime should become selected");
assert(cta.href.includes("txtSessionId=222"), "CTA should switch to the newly selected showtime URL");
assert(
  cta.attributes["aria-label"] === "21:40 場次前往訂票",
  "CTA aria-label should follow the selected time",
);

assert(
  source.includes('data-booking-cta-label>場次入口</span>'),
  "Initial CTA should still say 場次入口",
);
assert(
  source.includes('class="st-chip st-chip-select"'),
  "Direct showtimes should render as selectable chips, not outbound links",
);

console.log("frontend_showtime_booking_cta_test: ok");
