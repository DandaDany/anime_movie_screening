const fs = require("fs");
const vm = require("vm");
const path = require("path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "web", "version-filter.js"),
  "utf8",
);

const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const {
  FORMAT_ORDER,
  displayTag,
  formatTags,
  languageTag,
} = sandbox.window.MuseVersionFilter;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function tags(format, auditorium = "", language = "") {
  return formatTags({
    time: "19:30",
    format,
    auditorium,
    language,
    label: ["19:30", format, auditorium].filter(Boolean).join(" / "),
  });
}

assert(tags("(IMAX)測試電影").includes("IMAX"), "IMAX should normalize");
assert(tags("(IV 4DX 3D)測試電影").includes("4DX"), "4DX should normalize");
assert(tags("(IV 4DX 3D)測試電影").includes("3D"), "3D should normalize");
assert(tags("(TITAN)測試電影").includes("TITAN"), "TITAN should normalize");
assert(
  tags("Dolby Cinema INFINITY VISION").includes("INFINITY VISION"),
  "INFINITY VISION should normalize",
);
assert(tags("Dolby Cinema HFR").includes("HFR"), "HFR should normalize");
assert(tags("(INFINITY VISION)測試電影", "XL").includes("XL"), "XL hall should normalize");
assert(tags("測試電影", "V-hall").includes("V廳"), "V-hall should normalize to V廳");
assert(tags("測試電影", "跨腳廳").includes("FreeLaxx"), "跨腳廳 should normalize to FreeLaxx");
assert(tags("測試電影", "親子").includes("KIDS+"), "親子 should normalize to KIDS+");
assert(tags("測試電影", "跨電癮").includes("跨電癮"), "跨電癮 should normalize");
assert(tags("測試電影(2D - 水影威尼斯)").includes("水影威尼斯"), "水影威尼斯 should normalize");
assert(tags("測試電影(4D+)").includes("4D+"), "4D+ should normalize");
assert(tags("REMMI 英語").includes("REMMI"), "REMMI should normalize");
assert(languageTag({ format: "數位 日文版" }) === "日語", "Japanese should normalize");
assert(
  displayTag({ format: "Dolby Cinema INFINITY VISION" }).includes("Dolby"),
  "display tag should include Dolby",
);
assert(FORMAT_ORDER.indexOf("IMAX") < FORMAT_ORDER.indexOf("數位"), "Premium formats should sort before standard 2D");

console.log("frontend_version_filter_test: ok");
