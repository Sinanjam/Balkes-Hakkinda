(() => {
  "use strict";

  const SCORE_BASES = [
    "https://raw.githubusercontent.com/Sinanjam/Balkes-Hakkinda/main/data/",
    "https://cdn.jsdelivr.net/gh/Sinanjam/Balkes-Hakkinda@main/data/"
  ];
  const ARCHIVE_MANIFESTS = [
    "https://raw.githubusercontent.com/Sinanjam/Balkes-Arsivi/main/app/src/main/assets/archive/archive_items.json",
    "https://cdn.jsdelivr.net/gh/Sinanjam/Balkes-Arsivi@main/app/src/main/assets/archive/archive_items.json"
  ];
  const ARCHIVE_MEDIA_BASES = [
    "https://raw.githubusercontent.com/Sinanjam/Balkes-Arsivi/main/app/src/main/assets/",
    "https://cdn.jsdelivr.net/gh/Sinanjam/Balkes-Arsivi@main/app/src/main/assets/"
  ];
  const LOGO_URL = "https://raw.githubusercontent.com/Sinanjam/Balkes-Hakkinda/main/app/src/main/res/drawable-nodpi/balkes_logo.png";
  const FEEDBACK_URL = "https://forms.gle/PgRRAGpovH3tRWTM7";
  const ANDROID_URL = "https://github.com/Sinanjam/Balkes-Hakkinda/releases/latest";
  const REPOSITORY_URL = "https://github.com/Sinanjam/Balkes-Hakkinda";
  const GOATCOUNTER_TOTAL_URL = "https://sinanjam10.goatcounter.com/counter/TOTAL.json";
  const CACHE_PREFIX = "balkes-web:";
  const CACHE_TTL = 15 * 60 * 1000;
  const FETCH_TIMEOUT = 12_000;

  const main = document.querySelector("#main-content");
  const navLinks = [...document.querySelectorAll("[data-nav]")];
  const state = {
    routeToken: 0,
    scoreManifest: null,
    archiveManifest: null,
    forceOnce: false
  };

  function text(value, fallback = "") {
    if (value === null || value === undefined) return fallback;
    const result = String(value).trim();
    return result || fallback;
  }

  function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function asArray(value, property) {
    if (Array.isArray(value)) return value;
    if (value && property && Array.isArray(value[property])) return value[property];
    return [];
  }

  function h(tag, options = {}, ...children) {
    const element = document.createElement(tag);
    if (options.className) element.className = options.className;
    if (options.text !== undefined) element.textContent = text(options.text);
    if (options.href) element.setAttribute("href", options.href);
    if (options.type) element.setAttribute("type", options.type);
    if (options.value !== undefined) element.value = String(options.value);
    if (options.placeholder) element.setAttribute("placeholder", options.placeholder);
    if (options.ariaLabel) element.setAttribute("aria-label", options.ariaLabel);
    if (options.target) element.setAttribute("target", options.target);
    if (options.rel) element.setAttribute("rel", options.rel);
    if (options.loading) element.setAttribute("loading", options.loading);
    if (options.alt !== undefined) element.setAttribute("alt", options.alt);
    if (options.src) element.setAttribute("src", options.src);
    if (options.id) element.id = options.id;
    if (options.title) element.title = options.title;
    if (options.onClick) element.addEventListener("click", options.onClick);
    if (options.onInput) element.addEventListener("input", options.onInput);
    if (options.onChange) element.addEventListener("change", options.onChange);
    if (options.attrs) {
      Object.entries(options.attrs).forEach(([key, value]) => {
        if (value !== null && value !== undefined) element.setAttribute(key, String(value));
      });
    }
    children.flat(Infinity).forEach((child) => {
      if (child === null || child === undefined || child === false) return;
      element.append(child instanceof Node ? child : document.createTextNode(String(child)));
    });
    return element;
  }

  function fragment(...children) {
    const result = document.createDocumentFragment();
    children.flat(Infinity).forEach((child) => {
      if (child !== null && child !== undefined && child !== false) result.append(child);
    });
    return result;
  }

  function externalLink(label, href, className = "button") {
    return h("a", {
      className,
      text: label,
      href: safeExternalUrl(href),
      target: "_blank",
      rel: "noopener noreferrer"
    });
  }

  function safeExternalUrl(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : "#";
    } catch (_error) {
      return "#";
    }
  }

  function normalize(value) {
    return text(value)
      .toLocaleLowerCase("tr-TR")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function truncate(value, limit = 180) {
    const clean = text(value).replace(/\s+/g, " ");
    if (clean.length <= limit) return clean;
    return `${clean.slice(0, limit - 1).trim()}…`;
  }

  function routeHref(...parts) {
    return `#/${parts.map((part) => encodeURIComponent(text(part))).join("/")}`;
  }

  function pageShell(...children) {
    return h("div", { className: "page-shell" }, ...children);
  }

  function eyebrow(label, accent = "") {
    return h("p", { className: `eyebrow ${accent}`.trim(), text: label });
  }

  function buttonLink(label, href, tone = "") {
    return h("a", { className: `button ${tone}`.trim(), text: label, href });
  }

  function backLink(label, href) {
    return h("a", { className: "back-link", href }, "← ", label);
  }

  function sectionHead(kicker, title, subtitle, accent = "") {
    return h("div", { className: "section-head" },
      h("div", {},
        eyebrow(kicker, accent),
        h("h2", { text: title }),
        subtitle ? h("p", { className: "muted", text: subtitle }) : null
      )
    );
  }

  function stat(value, label) {
    return h("div", { className: "stat" },
      h("strong", { text: value }),
      h("span", { text: label })
    );
  }

  function notice(title, body, action) {
    return h("div", { className: "notice" },
      h("strong", { text: title }),
      h("p", { text: body }),
      action || null
    );
  }

  function renderLoading(message = "Veriler hazırlanıyor…") {
    document.title = "Yükleniyor — Balkes";
    main.replaceChildren(
      h("div", { className: "loading" },
        h("div", {},
          h("div", { className: "spinner", attrs: { "aria-hidden": "true" } }),
          h("strong", { text: message }),
          h("p", { className: "muted", text: "İlk açılıştan sonra veriler cihazında önbelleğe alınır." })
        )
      )
    );
  }

  function renderError(error, retry = route) {
    const message = error instanceof Error ? error.message : text(error, "Beklenmeyen bir hata oluştu.");
    document.title = "Veri alınamadı — Balkes";
    main.replaceChildren(
      pageShell(
        h("div", { className: "error-state card" },
          eyebrow("Bağlantı sorunu", "red"),
          h("h2", { text: "Veriler şu anda açılamadı" }),
          h("p", { className: "muted", text: message }),
          h("button", {
            className: "button",
            type: "button",
            text: "Yeniden dene",
            onClick: () => {
              state.forceOnce = true;
              retry();
            }
          })
        )
      )
    );
  }

  function readCache(key) {
    try {
      const raw = localStorage.getItem(CACHE_PREFIX + key);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !parsed.savedAt || parsed.data === undefined) return null;
      return parsed;
    } catch (_error) {
      return null;
    }
  }

  function writeCache(key, data) {
    try {
      localStorage.setItem(CACHE_PREFIX + key, JSON.stringify({ savedAt: Date.now(), data }));
    } catch (_error) {
      try {
        Object.keys(localStorage)
          .filter((item) => item.startsWith(CACHE_PREFIX))
          .forEach((item) => localStorage.removeItem(item));
        localStorage.setItem(CACHE_PREFIX + key, JSON.stringify({ savedAt: Date.now(), data }));
      } catch (_ignored) {
        // Private browsing or a full storage area must not stop the application.
      }
    }
  }

  async function fetchJson(url, force) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT);
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        cache: force ? "reload" : "default",
        headers: { Accept: "application/json" }
      });
      if (!response.ok) throw new Error(`Sunucu ${response.status} yanıtını verdi.`);
      return await response.json();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function loadJson(candidates, cacheKey, options = {}) {
    const force = Boolean(options.force || state.forceOnce);
    const cached = readCache(cacheKey);
    if (!force && cached && Date.now() - cached.savedAt < CACHE_TTL) return cached.data;

    let lastError = null;
    for (const candidate of [...new Set(candidates)]) {
      try {
        const data = await fetchJson(candidate, force);
        writeCache(cacheKey, data);
        return data;
      } catch (error) {
        lastError = error;
      }
    }
    if (cached) return cached.data;
    throw lastError || new Error("İnternet bağlantısı kurulamadı.");
  }

  async function scoreManifest() {
    if (state.scoreManifest && !state.forceOnce) return state.scoreManifest;
    const data = await loadJson(SCORE_BASES.map((base) => `${base}manifest.json`), "score:manifest");
    const seasons = asArray(data && data.availableSeasons);
    if (seasons.length < 32) throw new Error("Sezon manifesti eksik geldi. Lütfen yeniden deneyin.");
    state.scoreManifest = data;
    return data;
  }

  async function scoreFile(relativePath) {
    const clean = text(relativePath).replace(/^\/+/, "");
    if (!clean || clean.includes("..")) throw new Error("Geçersiz veri yolu.");
    return loadJson(SCORE_BASES.map((base) => base + clean), `score:${clean}`);
  }

  async function archiveManifest() {
    if (state.archiveManifest && !state.forceOnce) return state.archiveManifest;
    const data = await loadJson(ARCHIVE_MANIFESTS, "archive:manifest");
    if (asArray(data && data.items).length < 71) {
      throw new Error("Arşiv manifesti eksik geldi. Lütfen yeniden deneyin.");
    }
    state.archiveManifest = data;
    return data;
  }

  function archiveImage(asset, alt, eager = false) {
    const clean = text(asset).replace(/^\/+/, "");
    if (!clean || clean.includes("..")) return null;
    const image = h("img", {
      src: ARCHIVE_MEDIA_BASES[0] + clean,
      alt: text(alt, "Balkes Arşivi fotoğrafı"),
      loading: eager ? "eager" : "lazy",
      attrs: { decoding: "async" }
    });
    image.dataset.fallback = ARCHIVE_MEDIA_BASES[1] + clean;
    image.addEventListener("error", () => {
      if (image.dataset.fallback && image.src !== image.dataset.fallback) {
        image.src = image.dataset.fallback;
        image.dataset.fallback = "";
      } else {
        image.closest("figure")?.classList.add("hidden");
        if (image.classList.contains("archive-cover")) image.classList.add("hidden");
      }
    });
    return image;
  }

  function refreshCurrentRoute() {
    state.scoreManifest = null;
    state.archiveManifest = null;
    state.forceOnce = true;
    route();
  }

  function updateNavigation(section) {
    navLinks.forEach((link) => {
      if (link.dataset.nav === section) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function parseRoute() {
    const raw = location.hash.replace(/^#\/?/, "");
    return raw.split("/").filter(Boolean).map((part) => {
      try { return decodeURIComponent(part); } catch (_error) { return part; }
    });
  }

  async function route() {
    const token = ++state.routeToken;
    const parts = parseRoute();
    const section = parts[0] || "home";
    updateNavigation(section);
    window.scrollTo({ top: 0, behavior: "instant" });

    try {
      if (section === "score" && parts[2] === "match" && parts[1] && parts[3]) {
        renderLoading("Maç ayrıntıları alınıyor…");
        await renderMatch(parts[1], parts[3], token);
      } else if (section === "score" && parts[1]) {
        renderLoading("Sezon maçları ve puan durumu alınıyor…");
        await renderSeason(parts[1], token);
      } else if (section === "score") {
        renderLoading("32 sezon hazırlanıyor…");
        await renderScore(token);
      } else if (section === "archive" && parts[1]) {
        renderLoading("Arşiv kaydı açılıyor…");
        await renderArchiveDetail(parts[1], token);
      } else if (section === "archive") {
        renderLoading("71 arşiv kaydı hazırlanıyor…");
        await renderArchive(token);
      } else if (section === "about") {
        renderAbout();
      } else {
        renderLoading("Balkes hazırlanıyor…");
        await renderHome(token);
      }
    } catch (error) {
      if (token === state.routeToken) renderError(error);
    } finally {
      if (token === state.routeToken) state.forceOnce = false;
    }
  }

  function hasPlayed(match) {
    const score = match && match.score || {};
    return score.played !== false && (text(score.display) || score.home !== null && score.home !== undefined);
  }

  function shortDate(value) {
    const clean = text(value);
    if (!clean) return "Tarih bekleniyor";
    const parsed = new Date(`${clean}T12:00:00`);
    if (Number.isNaN(parsed.getTime())) return clean;
    return new Intl.DateTimeFormat("tr-TR", { day: "2-digit", month: "short" }).format(parsed);
  }

  function fixtureRow(match, seasonId) {
    const score = match.score || {};
    const played = hasPlayed(match);
    const result = text(match.balkes && match.balkes.result).toUpperCase();
    const tone = result === "W" ? "win" : result === "L" ? "loss" : result === "D" ? "draw" : "fixture";
    const status = played ? text(score.display, `${score.home}-${score.away}`) : text(match.time, shortDate(match.date));
    const week = number(match.week || match.standingsWeek);
    return h("a", { className: "fixture-row", href: routeHref("score", seasonId, "match", match.id) },
      h("span", { className: "fixture-round", text: week ? `${week}. HF` : text(match.matchTypeLabel, "MAÇ") }),
      h("span", { className: "fixture-clubs" },
        h("span", { className: normalize(match.homeTeam).includes("balikesirspor") ? "balkes-name" : "", text: text(match.homeTeam, "Ev sahibi") }),
        h("span", { className: normalize(match.awayTeam).includes("balikesirspor") ? "balkes-name" : "", text: text(match.awayTeam, "Deplasman") })
      ),
      h("span", { className: `fixture-result ${tone}`.trim() },
        h("strong", { text: status }),
        h("small", { text: played ? (result === "W" ? "Galibiyet" : result === "L" ? "Mağlubiyet" : "Beraberlik") : shortDate(match.date) })
      )
    );
  }

  function standingsPreview(snapshot, season) {
    const rows = asArray(snapshot && snapshot.standings);
    if (!rows.length) {
      return notice("Tablo hazırlanıyor", "Yeni sezonun puan durumu ilk lig maçlarıyla birlikte burada görünecek.");
    }
    const top = rows.slice(0, 5);
    const balkes = rows.find((row) => row.isBalkes);
    const visible = balkes && !top.includes(balkes) ? [...top, balkes] : top;
    return h("div", { className: "mini-table" },
      h("div", { className: "mini-table-head" },
        h("span", { text: "#" }),
        h("span", { text: "Takım" }),
        h("span", { text: "O" }),
        h("span", { text: "P" })
      ),
      ...visible.map((row, index) => h("a", {
        className: `mini-table-row ${row.isBalkes ? "balkes" : ""} ${index === 5 ? "separated" : ""}`.trim(),
        href: routeHref("score", season.id)
      },
        h("strong", { text: number(row.rank) }),
        h("span", { text: text(row.team) }),
        h("span", { text: number(row.played) }),
        h("strong", { text: number(row.points) })
      ))
    );
  }

  function sportsDashboard(currentSeason, currentMatches, tableSeason, standingWeeks) {
    const upcoming = currentMatches.filter((match) => !hasPlayed(match)).slice(0, 4);
    const recent = currentMatches.filter(hasPlayed).slice(-4).reverse();
    const featured = upcoming.length ? upcoming : recent;
    const snapshot = standingWeeks.length ? standingWeeks[standingWeeks.length - 1] : null;

    return h("section", { className: "section sports-center" },
      h("div", { className: "sports-center-head" },
        h("div", {},
          eyebrow("Maç merkezi", "red"),
          h("h2", { text: "Güncel sezon tek bakışta" }),
          h("p", { className: "muted", text: `${text(currentSeason.name)} · ${text(currentSeason.competition)}` })
        ),
        buttonLink("Tüm fikstür", routeHref("score", currentSeason.id), "ghost")
      ),
      h("div", { className: "sports-dashboard-grid" },
        h("article", { className: "sports-panel fixtures-panel" },
          h("div", { className: "panel-title" },
            h("div", {}, h("span", { className: "live-dot" }), h("strong", { text: upcoming.length ? "Sıradaki maçlar" : "Son sonuçlar" })),
            h("span", { className: "pill red", text: text(currentSeason.name) })
          ),
          h("div", { className: "fixture-list" },
            ...(featured.length
              ? featured.map((match) => fixtureRow(match, currentSeason.id))
              : [notice("Fikstür bekleniyor", "Bu sezonun maç programı henüz yayımlanmadı.")])
          )
        ),
        h("article", { className: "sports-panel standings-panel" },
          h("div", { className: "panel-title" },
            h("div", {}, h("span", { className: "table-icon", text: "≡" }), h("strong", { text: "Puan durumu" })),
            h("a", { className: "panel-link", href: routeHref("score", tableSeason.id), text: `${text(tableSeason.name)} →` })
          ),
          standingsPreview(snapshot, tableSeason)
        )
      )
    );
  }

  async function renderHome(token) {
    const manifest = await scoreManifest();
    const seasons = asArray(manifest.availableSeasons);
    const currentSeason = seasons[0];
    const tableSeason = seasons.find((season) => text(season.standingsByWeekUrl)) || currentSeason;
    const [currentMatchesResult, standingsResult] = await Promise.all([
      currentSeason ? scoreFile(text(currentSeason.matchesIndexUrl, `seasons/${currentSeason.id}/matches_index.json`)).catch(() => []) : Promise.resolve([]),
      tableSeason && text(tableSeason.standingsByWeekUrl)
        ? scoreFile(text(tableSeason.standingsByWeekUrl)).catch(() => [])
        : Promise.resolve([])
    ]);
    if (token !== state.routeToken) return;

    const currentMatches = asArray(currentMatchesResult, "matches");
    const standingWeeks = asArray(standingsResult, "weeks");
    const totalMatches = seasons.reduce((sum, season) => sum + number(season.matchCount), 0);

    document.title = "Balkes — Balıkesirspor Dijital Merkezi";
    const hero = h("section", { className: "hero premium-hero" },
      h("div", { className: "hero-copy" },
        eyebrow("Balıkesirspor Maç ve Arşiv Merkezi"),
        h("div", { className: "season-kicker" },
          h("span", { className: "live-dot" }),
          h("span", { text: `${text(currentSeason && currentSeason.name, "Güncel")} sezon verisi hazır` })
        ),
        h("h1", {}, "Balkes ", h("span", { className: "accent-red", text: "Maç" }), " Merkezi"),
        h("p", { className: "lead", text: "Fikstür, sonuç, hafta hafta puan durumu ve ayrıntılı maç kayıtları; kulübün dijital arşiviyle aynı yerde." }),
        h("div", { className: "actions" },
          buttonLink("Maç merkezini aç", "#/score", "red"),
          buttonLink("Arşivi keşfet", "#/archive")
        ),
        h("div", { className: "hero-metrics" },
          h("span", {}, h("strong", { text: seasons.length }), " sezon"),
          h("span", {}, h("strong", { text: totalMatches }), " maç"),
          h("span", {}, h("strong", { text: "71" }), " arşiv")
        )
      ),
      h("div", { className: "hero-visual" },
        h("div", { className: "hero-logo-shell" },
          h("img", { className: "hero-logo", src: LOGO_URL, alt: "Balkes logosu", attrs: { width: "350", height: "350" } }),
          h("span", { className: "hero-logo-caption", text: "BALIKESİRSPOR" })
        )
      )
    );

    const dashboard = currentSeason
      ? sportsDashboard(currentSeason, currentMatches, tableSeason, standingWeeks)
      : null;

    const choices = h("section", { className: "section quick-access" },
      sectionHead("Hızlı erişim", "Balkes'in bütün verisi", "İstediğin bölüme tek dokunuşla geç."),
      h("div", { className: "choice-grid" },
        choiceCard("Sonuçlar ve fikstür", "Skor Merkezi", "32 sezon, 1117 maç, haftalık tablolar ve bütün karşılaşma ayrıntıları.", "red", "#/score"),
        choiceCard("71 kayıt", "Balkes Arşivi", "Sezon hikâyeleri, tarihî yazılar, tablolar ve uzaktan yüklenen fotoğraflar.", "", "#/archive")
      )
    );

    const stats = h("section", { className: "section" },
      h("div", { className: "stat-grid premium-stats" },
        stat(seasons.length || "—", "erişilebilir sezon"),
        stat(totalMatches || "—", "ayrıntılı maç kaydı"),
        stat("1056", "haftalık puan tablosu"),
        stat("71", "korunan arşiv kaydı")
      )
    );

    main.replaceChildren(pageShell(hero, dashboard, choices, stats));
  }

  function choiceCard(kicker, title, body, tone, href) {
    return h("a", { className: `choice-card ${tone}`.trim(), href },
      eyebrow(kicker, tone),
      h("h2", { text: title }),
      h("p", { className: "muted", text: body }),
      h("span", { className: "arrow", text: "→", attrs: { "aria-hidden": "true" } })
    );
  }

  async function renderScore(token) {
    const manifest = await scoreManifest();
    if (token !== state.routeToken) return;
    const seasons = asArray(manifest.availableSeasons);
    const totalMatches = seasons.reduce((sum, season) => sum + number(season.matchCount), 0);
    const totalStandings = seasons.filter((season) => text(season.standingsByWeekUrl)).length;

    document.title = "Skor Merkezi — Balkes";
    const grid = h("div", { className: "card-grid season-grid", id: "season-grid" });
    const countLabel = h("p", { className: "muted", text: `${seasons.length} sezon gösteriliyor` });

    const paint = (query = "") => {
      const needle = normalize(query);
      const visible = seasons.filter((season) => normalize(`${season.name} ${season.competition}`).includes(needle));
      grid.replaceChildren(...visible.map((season) => seasonCard(season, season === seasons[0])));
      countLabel.textContent = `${visible.length} sezon gösteriliyor`;
      if (!visible.length) grid.append(notice("Sonuç bulunamadı", "Farklı bir sezon veya lig adı deneyin."));
    };

    const intro = h("div", { className: "page-intro" },
      h("div", {},
        eyebrow("Skor Merkezi", "red"),
        h("h1", { text: "Sezon merkezi" }),
        h("p", { className: "lead", text: "Fikstür, sonuçlar, lig performansı ve TFF kaynaklı hafta hafta puan tabloları." })
      ),
      h("button", { className: "button small", type: "button", text: "Veriyi yenile ↻", onClick: refreshCurrentRoute })
    );

    const summary = h("div", { className: "stat-grid" },
      stat(seasons.length, "sezon"),
      stat(totalMatches, "toplam maç"),
      stat(totalStandings, "puan tablosu olan sezon"),
      stat(text(manifest.appVersion, "güncel"), "veri sürümü")
    );

    const toolbar = h("div", { className: "toolbar" },
      h("input", {
        className: "search",
        type: "search",
        placeholder: "Sezon veya lig ara…",
        ariaLabel: "Sezonlarda ara",
        onInput: (event) => paint(event.currentTarget.value)
      }),
      countLabel
    );

    paint();
    main.replaceChildren(pageShell(intro, summary,
      h("section", { className: "section" }, sectionHead("Arşivlenen dönemler", "32 sezonun tamamı", "Bir sezonu açarak maçları ve haftalık tabloyu görüntüleyin.", ""), toolbar, grid)
    ));
  }

  function seasonCard(season, isCurrent = false) {
    const id = text(season.id);
    const summary = season.summary || {};
    const wins = number(summary.wins);
    const draws = number(summary.draws);
    const losses = number(summary.losses);
    const played = wins + draws + losses;
    return h("article", { className: `card season-card ${isCurrent ? "current" : ""}`.trim() },
      h("div", { className: "season-card-top" },
        h("div", { className: "chip-row" },
          h("span", { className: "pill", text: text(season.name, id) }),
          isCurrent ? h("span", { className: "pill live", text: "Güncel" }) : null
        ),
        summary.finalRank ? h("span", { className: "rank-chip", text: `${number(summary.finalRank)}. sıra` }) : null
      ),
      h("h3", { text: text(season.competition, "Profesyonel takım") }),
      h("div", { className: "season-scoreline" },
        h("span", {}, h("strong", { text: wins }), h("small", { text: "G" })),
        h("span", {}, h("strong", { text: draws }), h("small", { text: "B" })),
        h("span", {}, h("strong", { text: losses }), h("small", { text: "M" })),
        h("span", { className: "season-points" }, h("strong", { text: summary.points !== undefined ? number(summary.points) : "—" }), h("small", { text: "P" }))
      ),
      h("p", { className: "meta" },
        h("span", { text: `${number(season.matchCount)} maç` }),
        played ? h("span", { text: `${played} oynandı` }) : h("span", { text: "fikstür hazır" }),
        text(season.standingsByWeekUrl) ? h("span", { text: "haftalık tablo" }) : null
      ),
      h("a", { className: "card-link red", href: routeHref("score", id) }, "Sezon merkezini aç →")
    );
  }

  async function renderSeason(seasonId, token) {
    const manifest = await scoreManifest();
    const seasons = asArray(manifest.availableSeasons);
    const season = seasons.find((item) => text(item.id) === seasonId);
    if (!season) throw new Error("Bu sezon veri manifestinde bulunamadı.");

    const matchesPath = text(season.matchesIndexUrl, `seasons/${seasonId}/matches_index.json`);
    const standingsPath = text(season.standingsByWeekUrl);
    const [matchesResult, standingsResult] = await Promise.all([
      scoreFile(matchesPath),
      standingsPath ? scoreFile(standingsPath).catch(() => null) : Promise.resolve(null)
    ]);
    if (token !== state.routeToken) return;

    const matches = asArray(matchesResult, "matches");
    const standings = asArray(standingsResult, "weeks");
    const summary = season.summary || {};
    const displayName = text(season.name, seasonId);
    document.title = `${displayName} Sezonu — Balkes`;

    const intro = fragment(
      backLink("Tüm sezonlar", "#/score"),
      h("div", { className: "page-intro" },
        h("div", {},
          eyebrow("Skor Merkezi", "red"),
          h("h1", { text: `${displayName} Sezonu` }),
          h("p", { className: "lead", text: text(season.competition, "Maç sonuçları ve sezon ayrıntıları") })
        ),
        h("button", { className: "button small", type: "button", text: "Yenile ↻", onClick: refreshCurrentRoute })
      ),
      h("div", { className: "stat-grid" },
        stat(matches.length, "maç kaydı"),
        stat(number(summary.wins, "—"), "galibiyet"),
        stat(number(summary.draws, "—"), "beraberlik"),
        stat(number(summary.losses, "—"), "mağlubiyet")
      )
    );

    const standingsSection = buildStandingsSection(standings, season);
    const matchesSection = buildMatchesSection(matches, seasonId);
    main.replaceChildren(pageShell(intro, standingsSection, matchesSection));
  }

  function buildStandingsSection(weeks, season) {
    const section = h("section", { className: "section" });
    if (!weeks.length) {
      section.append(
        sectionHead("Puan durumu", "Haftalık tablo henüz yok", "Bu sezonda yayımlanmış resmî bir haftalık tablo bulunmuyor."),
        notice("Puan durumu oluşmadı", "Fikstür ve maç kayıtları aşağıda görüntülenmeye devam eder.")
      );
      return section;
    }

    const tableHost = h("div");
    const selector = h("select", { className: "select", ariaLabel: "Puan durumu haftasını seç" });
    weeks.forEach((snapshot, index) => {
      const label = snapshot.stageLabel
        ? `${text(snapshot.stageLabel)} · ${number(snapshot.week)}. hafta`
        : `${number(snapshot.week, index + 1)}. hafta`;
      const option = h("option", { value: index, text: label });
      if (index === weeks.length - 1) option.selected = true;
      selector.append(option);
    });
    const renderSelected = () => renderStandingsTable(weeks[number(selector.value, weeks.length - 1)], tableHost);
    selector.addEventListener("change", renderSelected);

    section.append(
      h("div", { className: "section-head" },
        h("div", {},
          eyebrow("Puan durumu"),
          h("h2", { text: "Hafta hafta resmî tablo" }),
          h("p", { className: "muted", text: `${weeks.length} haftalık kayıt · ${text(season.competition)}` })
        ),
        h("div", { attrs: { style: "min-width: 180px" } }, selector)
      ),
      tableHost
    );
    renderSelected();
    return section;
  }

  function renderStandingsTable(snapshot, host) {
    if (!snapshot) {
      host.replaceChildren(notice("Tablo bulunamadı", "Bu hafta için kayıt yok."));
      return;
    }
    const rows = asArray(snapshot.standings);
    const table = h("table", {},
      h("thead", {}, h("tr", {},
        ...["#", "Takım", "O", "G", "B", "M", "A", "Y", "AV", "P"].map((label, index) =>
          h("th", { className: index === 1 ? "team-cell" : "", text: label, attrs: { scope: "col" } })
        )
      )),
      h("tbody", {}, ...rows.map((row) => h("tr", { className: row.isBalkes ? "balkes" : "" },
        h("td", { text: number(row.rank) }),
        h("td", { className: "team-cell", text: text(row.team), title: text(row.penaltyNote) }),
        h("td", { text: number(row.played) }),
        h("td", { text: number(row.won) }),
        h("td", { text: number(row.drawn) }),
        h("td", { text: number(row.lost) }),
        h("td", { text: number(row.goalsFor) }),
        h("td", { text: number(row.goalsAgainst) }),
        h("td", { text: signed(row.goalDifference) }),
        h("td", { text: number(row.points) })
      )))
    );
    const source = safeExternalUrl(snapshot.sourceUrl);
    host.replaceChildren(
      h("div", { className: "table-wrap" }, table),
      h("p", { className: "source-note" },
        `${number(snapshot.week)}. hafta · Kaynak: TFF`,
        source !== "#" ? h("a", { href: source, target: "_blank", rel: "noopener noreferrer" }, " · Resmî tabloyu aç ↗") : null
      )
    );
  }

  function signed(value) {
    const parsed = number(value);
    return parsed > 0 ? `+${parsed}` : String(parsed);
  }

  function buildMatchesSection(matches, seasonId) {
    const section = h("section", { className: "section" });
    const list = h("div", { className: "match-list" });
    const resultLabel = h("p", { className: "muted" });
    let activeType = "all";
    let query = "";

    const types = [
      ["all", "Tümü"],
      ["league", "Lig"],
      ["cup", "Kupa"],
      ["playoff", "Play-off"]
    ];
    const filters = h("div", { className: "filter-row" });

    const paint = () => {
      const needle = normalize(query);
      const visible = matches.filter((match) => {
        const type = text(match.matchType || match.competitionType || match.type).toLowerCase();
        const typeMatches = activeType === "all" || type === activeType;
        const searchMatches = normalize(`${match.homeTeam} ${match.awayTeam} ${match.competition} ${match.stage}`).includes(needle);
        return typeMatches && searchMatches;
      });
      list.replaceChildren(...visible.map((match) => matchCard(match, seasonId)));
      resultLabel.textContent = `${visible.length} maç gösteriliyor`;
      if (!visible.length) list.append(notice("Maç bulunamadı", "Filtreyi veya arama metnini değiştirin."));
    };

    types.forEach(([value, label]) => {
      const button = h("button", {
        className: `filter-button ${value === "all" ? "active" : ""}`,
        type: "button",
        text: label,
        onClick: () => {
          activeType = value;
          [...filters.children].forEach((child) => child.classList.toggle("active", child === button));
          paint();
        }
      });
      filters.append(button);
    });

    const toolbar = h("div", { className: "toolbar" },
      h("input", {
        className: "search",
        type: "search",
        placeholder: "Rakip, kupa veya lig ara…",
        ariaLabel: "Sezon maçlarında ara",
        onInput: (event) => { query = event.currentTarget.value; paint(); }
      }),
      resultLabel
    );

    section.append(
      sectionHead("Tüm maçlar", `${matches.length} karşılaşma`, "Kartı açarak kadro, hakem, gol, kart ve oyuncu değişikliklerini görüntüleyin.", "red"),
      filters,
      toolbar,
      list
    );
    paint();
    return section;
  }

  function matchCard(match, seasonId) {
    const score = match.score || {};
    const played = hasPlayed(match);
    const result = text(match.balkes && match.balkes.result).toUpperCase();
    const scoreClass = result === "W" ? "win" : result === "L" ? "loss" : result === "D" ? "draw" : "fixture";
    const week = number(match.week || match.standingsWeek);
    const round = text(match.roundLabel || match.stageLabel || match.stage);
    const weekLabel = week ? `${week}. hafta` : round || text(match.matchTypeLabel, "Maç");
    const resultLabel = !played ? "Fikstür" : result === "W" ? "G" : result === "L" ? "M" : "B";

    return h("a", { className: "card match-card premium-match", href: routeHref("score", seasonId, "match", match.id) },
      h("div", { className: "match-info" },
        h("span", { className: "match-week", text: weekLabel }),
        h("span", { className: "match-date", text: [shortDate(match.date), text(match.time)].filter(Boolean).join(" · ") })
      ),
      h("div", { className: "match-team-stack" },
        h("div", { className: normalize(match.homeTeam).includes("balikesirspor") ? "match-team-row balkes-name" : "match-team-row" },
          h("span", { text: text(match.homeTeam, "Ev sahibi") }),
          h("strong", { text: played ? number(score.home) : "—" })
        ),
        h("div", { className: normalize(match.awayTeam).includes("balikesirspor") ? "match-team-row balkes-name" : "match-team-row" },
          h("span", { text: text(match.awayTeam, "Deplasman") }),
          h("strong", { text: played ? number(score.away) : "—" })
        )
      ),
      h("div", { className: `match-result-chip ${scoreClass}`.trim() },
        h("strong", { text: resultLabel }),
        h("small", { text: text(match.matchTypeLabel || match.competitionLabel || match.competition, "Maç") })
      )
    );
  }

  async function renderMatch(seasonId, matchId, token) {
    const detailPath = `seasons/${seasonId}/matches/${matchId}.json`;
    let match;
    try {
      match = await scoreFile(detailPath);
    } catch (_detailError) {
      const manifest = await scoreManifest();
      const season = asArray(manifest.availableSeasons).find((item) => text(item.id) === seasonId);
      const index = await scoreFile(text(season && season.matchesIndexUrl, `seasons/${seasonId}/matches_index.json`));
      match = asArray(index, "matches").find((item) => text(item.id) === matchId);
    }
    if (token !== state.routeToken) return;
    if (!match) throw new Error("Maç kaydı bulunamadı.");

    document.title = `${text(match.homeTeam)} - ${text(match.awayTeam)} — Balkes`;
    const score = match.score || {};
    const played = score.played !== false && (score.display || score.home !== undefined);
    const scoreDisplay = played ? text(score.display, `${score.home}-${score.away}`) : "—";
    const sourceUrl = safeExternalUrl(match.source && match.source.url);

    const scoreboard = h("section", { className: "scoreboard" },
      h("div", { className: "team", text: text(match.homeTeam, "Ev sahibi") }),
      h("div", { className: "score" }, scoreDisplay,
        h("small", { text: played ? text(match.matchTypeLabel || match.competitionLabel, "Maç sonucu") : "Fikstür" })
      ),
      h("div", { className: "team", text: text(match.awayTeam, "Deplasman") })
    );

    const facts = h("section", { className: "section" },
      h("div", { className: "detail-grid" },
        detailCard("Tarih ve saat", [text(match.date), text(match.time)].filter(Boolean).join(" · ") || "Belirtilmedi"),
        detailCard("Stadyum", text(match.stadium || match.venue, "Belirtilmedi")),
        detailCard("Organizasyon", text(match.competition, "Belirtilmedi")),
        detailCard("Aşama", text(match.stageLabel || match.stage || match.matchTypeLabel, "Belirtilmedi"))
      )
    );

    const eventSection = buildEventSection(match);
    const lineupSection = buildLineupSection(match.lineups);
    const officialsSection = buildOfficialsSection(match.officials || match.referees);

    main.replaceChildren(pageShell(
      backLink(`${seasonId} sezonuna dön`, routeHref("score", seasonId)),
      h("div", { className: "page-intro" },
        h("div", {}, eyebrow("Maç ayrıntısı", "red"), h("h1", { text: `${text(match.homeTeam)} - ${text(match.awayTeam)}` }), h("p", { className: "lead", text: text(match.dateDisplay || `${match.date || ""} ${match.time || ""}`) }))
      ),
      scoreboard,
      facts,
      eventSection,
      lineupSection,
      officialsSection,
      sourceUrl !== "#" ? h("section", { className: "section source-note" }, "Kaynak: Türkiye Futbol Federasyonu · ", h("a", { href: sourceUrl, target: "_blank", rel: "noopener noreferrer" }, "Resmî maç sayfasını aç ↗")) : null
    ));
  }

  function detailCard(title, value) {
    return h("div", { className: "card" }, eyebrow(title), h("h3", { text: value }));
  }

  function buildEventSection(match) {
    let events = asArray(match.events).filter((event) => text(event.type) !== "substitution");
    if (!events.length) events = [...asArray(match.goals), ...asArray(match.cards)];
    const substitutions = asArray(match.substitutions);
    if (!events.length && !substitutions.length) return null;

    const section = h("section", { className: "section" }, sectionHead("Maç akışı", "Goller, kartlar ve değişiklikler", "TFF maç sayfasında yayımlanan olaylar.", "red"));
    const grid = h("div", { className: "detail-grid" });

    if (events.length) {
      const sorted = [...events].sort((a, b) => number(a.minute, 999) - number(b.minute, 999));
      grid.append(h("div", { className: "card" },
        h("h3", { text: "Olaylar" }),
        h("ul", { className: "timeline" }, ...sorted.map((event) => {
          const type = text(event.type);
          const icon = type.includes("goal") ? "⚽" : type.includes("red") ? "🟥" : type.includes("yellow") ? "🟨" : "•";
          const person = text(event.player || event.scorer, "Oyuncu");
          return h("li", {},
            h("span", { className: "minute", text: minuteLabel(event) }),
            h("span", {}, `${icon} ${person}`, h("small", { className: "muted", text: ` · ${text(event.team)}` }))
          );
        }))
      ));
    }

    if (substitutions.length) {
      const sorted = [...substitutions].sort((a, b) => number(a.minute, 999) - number(b.minute, 999));
      grid.append(h("div", { className: "card" },
        h("h3", { text: "Oyuncu değişiklikleri" }),
        h("ul", { className: "timeline" }, ...sorted.map((event) => h("li", {},
          h("span", { className: "minute", text: minuteLabel(event) }),
          h("span", {}, `↑ ${text(event.playerIn || event.player_in, "—")}  ·  ↓ ${text(event.playerOut || event.player_out, "—")}`, h("small", { className: "muted", text: ` · ${text(event.team)}` }))
        )))
      ));
    }
    section.append(grid);
    return section;
  }

  function minuteLabel(event) {
    const raw = text(event.minuteRaw);
    const match = raw.match(/\d+(?:\+\d+)?/);
    return match ? `${match[0]}'` : event.minute !== undefined ? `${number(event.minute)}'` : "—";
  }

  function buildLineupSection(lineups) {
    if (!lineups || (!lineups.home && !lineups.away)) return null;
    const section = h("section", { className: "section" }, sectionHead("Kadrolar", "İlk 11 ve yedekler", "Yayımlanan resmî maç kadroları."));
    const grid = h("div", { className: "lineup-grid" });
    [lineups.home, lineups.away].filter(Boolean).forEach((team) => {
      const starters = asArray(team.starting11);
      const substitutes = asArray(team.substitutes);
      grid.append(h("div", { className: "card" },
        h("h3", { className: "lineup-team", text: text(team.team, "Takım") }),
        h("p", { className: "eyebrow", text: "İlk 11" }),
        playerList(starters),
        substitutes.length ? h("details", {},
          h("summary", { text: `Yedekler · ${substitutes.length}` }),
          playerList(substitutes)
        ) : null,
        text(team.coach) ? h("p", { className: "source-note", text: `Teknik sorumlu: ${text(team.coach)}` }) : null
      ));
    });
    section.append(grid);
    return section;
  }

  function playerList(players) {
    return h("ul", { className: "people-list" }, ...players.map((player) => h("li", {},
      h("span", { className: "shirt", text: text(player.number || player.shirt_no, "—") }),
      h("span", { text: text(player.name, "Oyuncu") })
    )));
  }

  function buildOfficialsSection(officialsValue) {
    const officials = asArray(officialsValue);
    if (!officials.length) return null;
    return h("section", { className: "section" },
      sectionHead("Görevliler", "Hakemler", "Karşılaşmanın resmî görevlileri.", "green"),
      h("div", { className: "card" },
        h("ul", { className: "people-list" }, ...officials.map((official) => h("li", {},
          h("span", { className: "shirt", text: "•" }),
          h("span", {}, h("strong", { text: text(official.name, "—") }), h("small", { className: "muted", text: ` · ${text(official.role, "Görevli")}` }))
        )))
      )
    );
  }

  async function renderArchive(token) {
    const manifest = await archiveManifest();
    if (token !== state.routeToken) return;
    const items = asArray(manifest.items);
    const seasons = [...new Set(items.map((item) => text(item.season)).filter(Boolean))]
      .sort((a, b) => b.localeCompare(a, "tr", { numeric: true }));

    document.title = "Balkes Arşivi — Balkes";
    const grid = h("div", { className: "card-grid" });
    const countLabel = h("p", { className: "muted" });
    let query = "";
    let selectedSeason = "all";

    const paint = () => {
      const needle = normalize(query);
      const visible = items.filter((item) => {
        const seasonMatches = selectedSeason === "all" || text(item.season) === selectedSeason;
        const searchMatches = normalize(`${item.title} ${item.summary} ${item.content} ${item.season}`).includes(needle);
        return seasonMatches && searchMatches;
      });
      grid.replaceChildren(...visible.map(archiveCard));
      countLabel.textContent = `${visible.length} / ${items.length} kayıt gösteriliyor`;
      if (!visible.length) grid.append(notice("Arşiv kaydı bulunamadı", "Arama metnini veya sezon filtresini değiştirin."));
    };

    const seasonSelect = h("select", {
      className: "select",
      ariaLabel: "Arşivi sezona göre filtrele",
      onChange: (event) => { selectedSeason = event.currentTarget.value; paint(); }
    },
      h("option", { value: "all", text: "Tüm sezonlar" }),
      ...seasons.map((season) => h("option", { value: season, text: season }))
    );

    const intro = h("div", { className: "page-intro" },
      h("div", {},
        eyebrow("Kulübün hafızası"),
        h("h1", { text: "Balkes Arşivi" }),
        h("p", { className: "lead", text: "Tarihî sezon yazıları, anılar, tablolar ve fotoğraf koleksiyonları. Büyük medya dosyaları yalnızca açıldığında yüklenir." })
      ),
      h("button", { className: "button small", type: "button", text: "Veriyi yenile ↻", onClick: refreshCurrentRoute })
    );

    const toolbar = h("div", { className: "toolbar" },
      h("input", {
        className: "search",
        type: "search",
        placeholder: "Arşivde ara…",
        ariaLabel: "Arşivde ara",
        onInput: (event) => { query = event.currentTarget.value; paint(); }
      }),
      seasonSelect
    );

    paint();
    main.replaceChildren(pageShell(
      intro,
      h("div", { className: "stat-grid" },
        stat(items.length, "toplam arşiv kaydı"),
        stat(items.reduce((sum, item) => sum + number(item.imageCount), 0), "uzaktan fotoğraf"),
        stat(seasons.length, "sezon etiketi"),
        stat("Wayback", "korunan tarihî kaynak")
      ),
      h("section", { className: "section" }, sectionHead("Tüm içerikler", "71 kaydın tamamı", "Başlık, metin veya sezon adıyla arayın."), toolbar, countLabel, grid)
    ));
  }

  function archiveCard(item) {
    const image = archiveImage(item.imageAsset, item.imageCaption || item.title);
    if (image) image.classList.add("archive-cover");
    return h("article", { className: "card archive-card" },
      image,
      h("div", { className: "chip-row" },
        text(item.season) ? h("span", { className: "pill", text: item.season }) : null,
        h("span", { className: "pill red", text: `${number(item.imageCount)} fotoğraf` })
      ),
      h("h3", { text: text(item.title, "Arşiv kaydı") }),
      h("p", { className: "muted", text: truncate(item.summary || item.content, 155) }),
      h("a", { className: "card-link", href: routeHref("archive", item.id) }, "Arşivi aç →")
    );
  }

  async function renderArchiveDetail(itemId, token) {
    const manifest = await archiveManifest();
    if (token !== state.routeToken) return;
    const item = asArray(manifest.items).find((entry) => text(entry.id) === itemId);
    if (!item) throw new Error("Arşiv kaydı bulunamadı.");

    document.title = `${text(item.title, "Arşiv")} — Balkes`;
    const contentSection = h("section", { className: "section" },
      sectionHead("Arşiv metni", "Hikâye ve kayıtlar", text(item.sourceType)),
      h("article", { className: "card prose" }, ...contentParagraphs(item.content))
    );

    const photos = asArray(item.photos);
    const gallerySection = photos.length ? buildGallerySection(photos) : null;
    const tablesSection = text(item.tables) ? h("section", { className: "section" },
      sectionHead("Arşiv tabloları", `${number(item.tableCount)} tablo`, "Özgün kayıttaki tablo metinleri değiştirilmeden gösterilir.", "green"),
      h("details", { className: "card archive-tables" },
        h("summary", { text: "Tabloları göster" }),
        h("pre", { text: text(item.tables) })
      )
    ) : null;
    const source = safeExternalUrl(item.sourceUrl);

    main.replaceChildren(pageShell(
      backLink("Tüm arşiv", "#/archive"),
      h("div", { className: "page-intro" },
        h("div", {},
          eyebrow(text(item.season, "Balkes Arşivi")),
          h("h1", { text: text(item.title, "Arşiv kaydı") }),
          h("p", { className: "lead", text: text(item.summary) }),
          h("div", { className: "chip-row" },
            h("span", { className: "pill", text: `${photos.length} fotoğraf` }),
            h("span", { className: "pill red", text: `${number(item.tableCount)} tablo` })
          )
        )
      ),
      contentSection,
      tablesSection,
      gallerySection,
      source !== "#" ? h("section", { className: "section source-note" }, `Kaynak türü: ${text(item.sourceType, "Arşiv")} · `, h("a", { href: source, target: "_blank", rel: "noopener noreferrer" }, "Özgün kaydı aç ↗")) : null
    ));
  }

  function contentParagraphs(content) {
    const chunks = text(content)
      .split(/\n\s*\n/)
      .map((chunk) => chunk.trim())
      .filter(Boolean);
    if (!chunks.length) return [h("p", { text: "Bu kayıtta metin bulunmuyor." })];
    return chunks.map((chunk) => h("p", { text: chunk }));
  }

  function buildGallerySection(photos) {
    const section = h("section", { className: "section" }, sectionHead("Fotoğraf arşivi", `${photos.length} tarihî kare`, "Fotoğraflar sayfayı aşağı kaydırdıkça yüklenir.", "red"));
    const gallery = h("div", { className: "gallery" });
    let rendered = 0;
    const batchSize = 12;
    const more = h("button", { className: "button ghost", type: "button", text: "Daha fazla fotoğraf göster" });

    const appendBatch = () => {
      photos.slice(rendered, rendered + batchSize).forEach((photo) => {
        const image = archiveImage(photo.asset, photo.caption);
        if (!image) return;
        gallery.append(h("figure", {},
          image,
          text(photo.caption) ? h("figcaption", { text: truncate(photo.caption, 220) }) : null
        ));
      });
      rendered = Math.min(rendered + batchSize, photos.length);
      more.textContent = `Daha fazla fotoğraf göster · ${photos.length - rendered} kaldı`;
      more.classList.toggle("hidden", rendered >= photos.length);
    };
    more.addEventListener("click", appendBatch);
    appendBatch();
    section.append(gallery, h("div", { className: "actions" }, more));
    return section;
  }

  function renderAbout() {
    document.title = "Hakkında — Balkes";
    main.replaceChildren(pageShell(
      h("div", { className: "page-intro" },
        h("div", {},
          eyebrow("Şeffaflık"),
          h("h1", { text: "Hakkında" }),
          h("p", { className: "lead", text: "Balkes'in amacı, kaynakları ve iletişim kanalları." })
        )
      ),
      h("div", { className: "about-grid" },
        aboutCard("Sorumluluk reddi beyanı", "Bu site ve Android uygulaması taraftar yapımı bağımsız bir projedir; Balıkesirspor, TFF veya adı geçen kurumların resmî yayını değildir. Skor, puan durumu ve arşiv içerikleri bilgilendirme amaçlıdır; hata ya da gecikme olabilir. Kesin bilgi için resmî kaynakları kontrol edin.", "red"),
        aboutCard("Kaynaklar", "Maç, fikstür ve puan tabloları TFF'nin resmî sayfalarından; tarihî içerik ve fotoğraflar Balkes Arşivi, Özbalkesler ve kayıtlarda belirtilen özgün kaynaklardan alınır. Uygulama verileri GitHub deposundan sunulur."),
        aboutCard("Vibe Coding", "Projenin geliştirme sürecinde Vibe Coding ve yapay zekâ destekli araçlardan faydalanılmıştır. İçerik, doğrulama ve yayımlama kararları geliştirici tarafından kontrol edilmektedir.", "green"),
        h("article", { className: "card about-card" },
          h("h3", { text: "Geri bildirim ve iletişim" }),
          h("p", { className: "muted", text: "Hata bildirimi, öneri veya iletişim için Google Form'u kullanabilirsiniz." }),
          h("div", { className: "actions" },
            externalLink("Formu aç ↗", FEEDBACK_URL),
            externalLink("GitHub deposu ↗", REPOSITORY_URL, "button ghost")
          )
        )
      ),
      h("section", { className: "section card" },
        eyebrow("Android"),
        h("h2", { text: "Balkes'i telefona kur" }),
        h("p", { className: "lead", text: "Son kullanıcı APK'sını sade GitHub Release sayfasından indirebilirsiniz." }),
        h("div", { className: "actions" }, externalLink("Son Android sürümünü aç ↗", ANDROID_URL, "button red"))
      )
    ));
  }

  function aboutCard(title, body, tone = "") {
    return h("article", { className: `card about-card ${tone}`.trim() },
      h("h3", { text: title }),
      h("p", { className: "muted", text: body })
    );
  }

  async function loadVisitorCount() {
    const counter = document.querySelector("#visitor-counter");
    const value = document.querySelector("#goatcounter-value");
    const status = document.querySelector("#goatcounter-status");
    if (!counter || !value || !status) return;

    try {
      const response = await fetch(GOATCOUNTER_TOTAL_URL, {
        headers: { Accept: "application/json" },
        cache: "no-store"
      });
      if (!response.ok) throw new Error(`GoatCounter ${response.status}`);
      const data = await response.json();
      const count = text(data && data.count);
      if (!count) throw new Error("Sayaç değeri boş");
      value.textContent = count;
      status.textContent = "GoatCounter · toplam görüntülenme";
      counter.classList.add("is-ready");
    } catch (_error) {
      value.textContent = "—";
      status.textContent = "Sayaç görünürlüğü bekleniyor";
      counter.classList.add("is-unavailable");
    }
  }

  window.addEventListener("hashchange", route);
  window.addEventListener("DOMContentLoaded", () => {
    route();
    loadVisitorCount();
  }, { once: true });

  if ("serviceWorker" in navigator && location.protocol === "https:") {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("./sw.js").catch(() => {
        // The website remains fully usable when service workers are unavailable.
      });
    });
  }
})();
