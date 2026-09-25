(() => {
  const FORMAT_RULES = [
    ["IMAX", /imax/i],
    ["4DX", /4dx/i],
    ["4D+", /4d\+/i],
    ["MX4D", /mx-?4d/i],
    ["ScreenX", /screen\s*-?\s*x/i],
    ["TITAN", /titan/i],
    ["ULTRA", /ultra/i],
    ["LUXE", /luxe/i],
    ["Dolby", /dolby|\bdva\b/i],
    ["ATMOS", /atmos/i],
    ["INFINITY VISION", /infinity\s*vision/i],
    ["HFR", /\bhfr\b/i],
    ["REMMI", /remmi/i],
    ["GC", /\bgc\b|gold\s*class/i],
    ["MUCROWN", /mucrown/i],
    ["A+", /a\+/i],
    ["皇家廳", /皇家廳/],
    ["COACH廳", /coach廳/i],
    ["BOOM廳", /boom廳/i],
    ["Pink Sofa", /pink\s*sofa/i],
    ["VIP", /\bvip\b/i],
    ["水影威尼斯", /水影威尼斯/],
    ["V廳", /v[-\s]?hall|v廳/i],
    ["FreeLaxx", /free\s*laxx|跨腳廳/i],
    ["跨電癮", /跨電癮/],
    ["KIDS+", /kids\+?|親子/i],
    ["XL", /\bxl\b/i],
    ["巨幕", /巨幕/],
    ["3D", /3d/i],
    ["數位", /數位/],
    ["2D", /2d/i],
  ];

  const FORMAT_ORDER = FORMAT_RULES.map(([name]) => name);

  const LANG_RULES = [
    ["日語", /日語|日文|JPN|[（(]\s*日\s*[)）]/i],
    ["英語", /英語|英文|ENG|[（(]\s*英\s*[)）]/i],
    ["國語", /國語|中文|CHT|[（(]\s*中\s*[)）]/i],
    ["台語", /台語|臺語/],
    ["粵語", /粵語/],
  ];

  function subLabel(showtime) {
    const label = showtime?.label || "";
    const rest = showtime?.time ? label.replace(showtime.time, "").trim() : label;
    return rest || showtime?.format || "";
  }

  function formatTags(showtime) {
    const raw = subLabel(showtime);
    if (!raw) return [];

    const formats = [];
    for (const [name, re] of FORMAT_RULES) {
      if (re.test(raw) && !formats.includes(name)) formats.push(name);
    }

    // 數位與 2D 同義時只保留「數位」；Dolby 字樣若同時含 ATMOS，
    // 兩者代表不同維度（Dolby Cinema / Atmos），搜尋時保留兩個。
    if (formats.includes("數位")) {
      const i = formats.indexOf("2D");
      if (i !== -1) formats.splice(i, 1);
    }

    return formats;
  }

  function languageTag(showtime) {
    const raw = subLabel(showtime);
    if (!raw) return "";

    for (const [name, re] of LANG_RULES) {
      if (re.test(raw)) return name;
    }

    const paren = /[（(]([^（()）]*)[)）]/.exec(raw);
    const inside = paren ? paren[1] : "";
    if (/日/.test(inside)) return "日語";
    if (/英/.test(inside)) return "英語";
    if (/[國中]/.test(inside)) return "國語";
    if (/台/.test(inside)) return "台語";
    return "";
  }

  function displayTag(showtime) {
    const formats = formatTags(showtime);
    const lang = languageTag(showtime);
    return [...formats.slice(0, 2), lang].filter(Boolean).join(" ");
  }

  window.MuseVersionFilter = {
    FORMAT_ORDER,
    FORMAT_RULES,
    LANG_RULES,
    displayTag,
    formatTags,
    languageTag,
    subLabel,
  };
})();
