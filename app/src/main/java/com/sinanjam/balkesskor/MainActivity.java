package com.sinanjam.balkesskor;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.sinanjam.balkesskor.data.DataEndpoints;
import com.sinanjam.balkesskor.data.RemoteImageLoader;
import com.sinanjam.balkesskor.data.RemoteJsonRepository;
import com.sinanjam.balkesskor.ui.EdgeToEdge;
import com.sinanjam.balkesskor.ui.Ui;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

public final class MainActivity extends Activity {
    private enum Tab { SCORE, ARCHIVE, PHOTOS, NEWS, SEASONS }
    private static final Locale TURKISH = new Locale("tr", "TR");

    private RemoteJsonRepository repository;
    private RemoteImageLoader imageLoader;
    private final Handler uiHandler = new Handler(Looper.getMainLooper());
    private final Runnable openChooser = () -> {
        if (!isFinishing() && !isDestroyed()) showEntryChoice();
    };
    private LinearLayout content;
    private ScrollView screenScroll;
    private TextView headerTitle;
    private TextView headerSubtitle;
    private Tab current = Tab.SCORE;
    private boolean chooserVisible = true;
    private Runnable detailBackAction;
    private String detailRequestKey = "";
    private int archiveRenderGeneration = 0;
    private int scoreRenderGeneration = 0;
    private final Map<String, String> seasonMatchUrls = new HashMap<>();
    private final Map<String, String> seasonStandingsUrls = new HashMap<>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        EdgeToEdge.configure(this);
        if (savedInstanceState == null) {
            showSplashScreen();
        } else {
            showEntryChoice();
        }

        repository = new RemoteJsonRepository(this);
        imageLoader = new RemoteImageLoader(this);
        warmScoreData();
        repository.prefetch(DataEndpoints.archiveManifest());
        if (savedInstanceState == null) uiHandler.postDelayed(openChooser, 700L);
    }

    private void showSplashScreen() {
        chooserVisible = true;
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackground(Ui.appBackground());

        ImageView badge = brandLogo();
        badge.setElevation(Ui.dp(this, 14));
        root.addView(badge, new LinearLayout.LayoutParams(Ui.dp(this, 150), Ui.dp(this, 150)));

        TextView title = Ui.text(this, "BALKES", 34, Ui.TEXT);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setLetterSpacing(0.13f);
        title.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(-1, -2);
        titleParams.setMargins(0, Ui.dp(this, 25), 0, 0);
        root.addView(title, titleParams);

        TextView subtitle = Ui.eyebrow(this, "Skor • Arşiv • Kulübün Hafızası", Ui.CYAN);
        subtitle.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(-1, -2);
        subtitleParams.setMargins(0, Ui.dp(this, 9), 0, Ui.dp(this, 25));
        root.addView(subtitle, subtitleParams);

        View line = new View(this);
        line.setBackground(Ui.neonLine());
        root.addView(line, new LinearLayout.LayoutParams(Ui.dp(this, 210), Ui.dp(this, 2)));

        setContentView(root);
        EdgeToEdge.applyInsets(root, Ui.dp(this, 24), Ui.dp(this, 28),
                Ui.dp(this, 24), Ui.dp(this, 28));
    }

    private void warmScoreData() {
        getScoreManifest(new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (isFinishing() || isDestroyed()) return;
                if (!(json instanceof JSONObject)) return;
                JSONArray seasons = ((JSONObject) json).optJSONArray("availableSeasons");
                if (seasons == null || seasons.length() == 0) return;
                JSONObject first = featuredSeason(seasons);
                if (first == null) return;
                String id = first.optString("id", "");
                if (id.length() == 0) return;
                prefetchScoreFile(first.optString(
                        "seasonUrl", "seasons/" + id + "/season.json"));
                prefetchScoreFile(first.optString(
                        "matchesIndexUrl", "seasons/" + id + "/matches_index.json"));
                String standings = first.optString("standingsByWeekUrl", "");
                if (standings.length() > 0) prefetchScoreFile(standings);
            }

            @Override public void onError(String message) { }
        });
    }

    private void getScoreManifest(RemoteJsonRepository.Callback callback) {
        String[] candidates = new String[]{
                DataEndpoints.scoreManifest(),
                DataEndpoints.scoreMirrorManifest()
        };
        getScoreManifest(candidates, 0, callback);
    }

    private void getScoreManifest(String[] candidates, int index,
                                  RemoteJsonRepository.Callback callback) {
        if (index >= candidates.length) {
            callback.onError("32 sezonluk birleşik skor verisi alınamadı. "
                    + "GitHub veri deposunun herkese açık olduğundan emin olup yeniden dene.");
            return;
        }
        final String address = candidates[index];
        if (index > 0 && address.equals(candidates[index - 1])) {
            getScoreManifest(candidates, index + 1, callback);
            return;
        }
        repository.get(address, new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (!(json instanceof JSONObject)
                        || !isUnifiedScoreManifest((JSONObject) json)) {
                    getScoreManifest(candidates, index + 1, callback);
                    return;
                }
                configureScoreManifest((JSONObject) json, address);
                callback.onSuccess(json, fromCache);
            }

            @Override public void onError(String message) {
                getScoreManifest(candidates, index + 1, callback);
            }
        });
    }

    private boolean isUnifiedScoreManifest(JSONObject manifest) {
        JSONArray seasons = manifest.optJSONArray("availableSeasons");
        if (seasons == null || seasons.length() < 32) return false;
        int matchIndexes = 0;
        int standingsIndexes = 0;
        int totalMatches = 0;
        for (int index = 0; index < seasons.length(); index++) {
            JSONObject season = seasons.optJSONObject(index);
            if (season == null) continue;
            if (season.optString("matchesIndexUrl", "").length() > 0) matchIndexes++;
            if (season.optString("standingsByWeekUrl", "").length() > 0) standingsIndexes++;
            totalMatches += season.optInt("matchCount", 0);
        }
        return matchIndexes == seasons.length()
                && standingsIndexes >= 31
                && totalMatches >= 1_100;
    }

    private void prefetchScoreFile(String relativePath) {
        repository.prefetch(DataEndpoints.scoreFile(relativePath));
        String mirror = DataEndpoints.scoreMirrorFile(relativePath);
        if (!mirror.equals(DataEndpoints.scoreFile(relativePath))) repository.prefetch(mirror);
    }

    private void getScoreJson(String relativePath, RemoteJsonRepository.Callback callback) {
        final String primary = DataEndpoints.scoreFile(relativePath);
        final String mirror = DataEndpoints.scoreMirrorFile(relativePath);
        repository.get(primary, new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                callback.onSuccess(json, fromCache);
            }

            @Override public void onError(String message) {
                if (mirror.equals(primary)) {
                    callback.onError(message);
                    return;
                }
                repository.get(mirror, callback);
            }
        });
    }

    private void configureScoreManifest(JSONObject manifest, String manifestUrl) {
        DataEndpoints.configureScoreManifest(manifest, manifestUrl);
        seasonMatchUrls.clear();
        seasonStandingsUrls.clear();
        JSONArray seasons = manifest.optJSONArray("availableSeasons");
        if (seasons == null) return;
        for (int index = 0; index < seasons.length(); index++) {
            JSONObject season = seasons.optJSONObject(index);
            if (season == null) continue;
            String id = season.optString("id", "");
            if (id.length() == 0) continue;
            seasonMatchUrls.put(id, season.optString(
                    "matchesIndexUrl", "seasons/" + id + "/matches_index.json"));
            String standings = season.optString("standingsByWeekUrl", "");
            if (standings.length() > 0) seasonStandingsUrls.put(id, standings);
        }
    }

    private JSONObject featuredSeason(JSONArray seasons) {
        if (seasons == null) return null;
        for (int index = 0; index < seasons.length(); index++) {
            JSONObject season = seasons.optJSONObject(index);
            if (season != null && season.optString("standingsByWeekUrl", "").length() > 0) {
                return season;
            }
        }
        return seasons.optJSONObject(0);
    }

    @Override
    protected void onDestroy() {
        chooserVisible = true;
        archiveRenderGeneration++;
        detailRequestKey = "";
        uiHandler.removeCallbacksAndMessages(null);
        if (repository != null) repository.close();
        if (imageLoader != null) imageLoader.close();
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        if (detailBackAction != null) {
            Runnable action = detailBackAction;
            detailBackAction = null;
            action.run();
            return;
        }
        if (!chooserVisible) {
            showEntryChoice();
            return;
        }
        super.onBackPressed();
    }

    private void showEntryChoice() {
        uiHandler.removeCallbacks(openChooser);
        archiveRenderGeneration++;
        chooserVisible = true;
        detailBackAction = null;
        detailRequestKey = "";
        content = null;

        ScrollView scroll = new ScrollView(this);
        screenScroll = scroll;
        scroll.setFillViewport(true);
        scroll.setBackground(Ui.appBackground());

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(Ui.dp(this, 22), Ui.dp(this, 34), Ui.dp(this, 22), Ui.dp(this, 30));
        scroll.addView(root, new ScrollView.LayoutParams(-1, -1));

        ImageView badge = brandLogo();
        badge.setElevation(Ui.dp(this, 12));
        root.addView(badge, new LinearLayout.LayoutParams(Ui.dp(this, 112), Ui.dp(this, 112)));

        TextView brand = Ui.eyebrow(this, "Balıkesirspor Dijital Merkezi", Ui.CYAN);
        brand.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams brandParams = new LinearLayout.LayoutParams(-1, -2);
        brandParams.setMargins(0, Ui.dp(this, 24), 0, 0);
        root.addView(brand, brandParams);

        TextView title = Ui.text(this, "Nereden başlamak\nistersin?", 31, Ui.TEXT);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setGravity(Gravity.CENTER);
        title.setLetterSpacing(-0.015f);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(-1, -2);
        titleParams.setMargins(0, Ui.dp(this, 9), 0, Ui.dp(this, 8));
        root.addView(title, titleParams);

        TextView subtitle = Ui.text(this,
                "Maç merkezine ya da kulübün hafızasına tek dokunuşla geç.", 14, Ui.MUTED);
        subtitle.setGravity(Gravity.CENTER);
        root.addView(subtitle, new LinearLayout.LayoutParams(-1, -2));

        View scoreChoice = choiceCard(
                "CANLI VE GÜNCEL",
                "Skor Merkezi",
                "Maçlar, sezonlar, puan durumu ve takım istatistikleri",
                Ui.RED,
                view -> enterApp(Tab.SCORE));
        LinearLayout.LayoutParams scoreParams = new LinearLayout.LayoutParams(-1, -2);
        scoreParams.setMargins(0, Ui.dp(this, 30), 0, 0);
        root.addView(scoreChoice, scoreParams);

        View archiveChoice = choiceCard(
                "KULÜBÜN HAFIZASI",
                "Balkes Arşivi",
                "Sezon hikâyeleri, tarihi yazılar ve fotoğraf koleksiyonu",
                Ui.CYAN,
                view -> enterApp(Tab.ARCHIVE));
        LinearLayout.LayoutParams archiveParams = new LinearLayout.LayoutParams(-1, -2);
        archiveParams.setMargins(0, Ui.dp(this, 14), 0, 0);
        root.addView(archiveChoice, archiveParams);

        TextView footer = Ui.text(this,
                "İçerikler otomatik güncellenir ve çevrimdışı da açılır", 11, Ui.MUTED);
        footer.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams footerParams = new LinearLayout.LayoutParams(-1, -2);
        footerParams.setMargins(0, Ui.dp(this, 27), 0, 0);
        root.addView(footer, footerParams);

        setContentView(scroll);
        EdgeToEdge.applyInsets(scroll, 0, 0, 0, 0);
    }

    private View choiceCard(String eyebrow, String title, String body, int accent,
                            View.OnClickListener listener) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.HORIZONTAL);
        card.setGravity(Gravity.CENTER_VERTICAL);
        card.setPadding(Ui.dp(this, 5), Ui.dp(this, 5), Ui.dp(this, 17), Ui.dp(this, 5));
        card.setBackground(Ui.choiceBackground(this, accent));
        card.setElevation(Ui.dp(this, 8));
        card.setClickable(true);
        card.setFocusable(true);
        card.setOnClickListener(listener);

        View rail = new View(this);
        rail.setBackgroundColor(accent);
        LinearLayout.LayoutParams railParams = new LinearLayout.LayoutParams(Ui.dp(this, 4), -1);
        railParams.setMargins(0, Ui.dp(this, 9), Ui.dp(this, 15), Ui.dp(this, 9));
        card.addView(rail, railParams);

        LinearLayout copy = new LinearLayout(this);
        copy.setOrientation(LinearLayout.VERTICAL);
        copy.setPadding(0, Ui.dp(this, 13), 0, Ui.dp(this, 13));
        card.addView(copy, new LinearLayout.LayoutParams(0, -2, 1));
        copy.addView(Ui.eyebrow(this, eyebrow, accent));

        TextView heading = Ui.text(this, title, 22, Ui.TEXT);
        heading.setTypeface(Typeface.DEFAULT_BOLD);
        heading.setPadding(0, Ui.dp(this, 4), 0, Ui.dp(this, 5));
        copy.addView(heading);
        copy.addView(Ui.text(this, body, 13, Ui.MUTED));

        TextView arrow = Ui.text(this, "›", 34, accent);
        arrow.setTypeface(Typeface.DEFAULT_BOLD);
        arrow.setGravity(Gravity.CENTER);
        card.addView(arrow, new LinearLayout.LayoutParams(Ui.dp(this, 34), -1));
        return card;
    }

    private void enterApp(Tab firstTab) {
        chooserVisible = false;
        buildShell();
        select(firstTab);
    }

    private void buildShell() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Ui.BACKGROUND);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(Ui.dp(this, 15), Ui.dp(this, 13), Ui.dp(this, 14), Ui.dp(this, 13));
        header.setBackground(Ui.headerBackground());
        header.setElevation(Ui.dp(this, 8));

        ImageView badge = brandLogo();
        header.addView(badge, new LinearLayout.LayoutParams(Ui.dp(this, 62), Ui.dp(this, 62)));

        LinearLayout titles = new LinearLayout(this);
        titles.setOrientation(LinearLayout.VERTICAL);
        titles.setPadding(Ui.dp(this, 12), 0, Ui.dp(this, 8), 0);
        header.addView(titles, new LinearLayout.LayoutParams(0, -2, 1));
        headerTitle = Ui.text(this, "BALKES", 23, Color.WHITE);
        headerTitle.setTypeface(Typeface.DEFAULT_BOLD);
        headerTitle.setLetterSpacing(0.035f);
        titles.addView(headerTitle);
        headerSubtitle = Ui.text(this, "Balıkesirspor dijital merkezi", 11, Ui.CYAN);
        titles.addView(headerSubtitle);

        TextView change = Ui.chip(this, "Ana Menü", Color.WHITE);
        change.setFocusable(true);
        change.setOnClickListener(view -> showEntryChoice());
        header.addView(change, new LinearLayout.LayoutParams(-2, -2));
        root.addView(header, new LinearLayout.LayoutParams(-1, -2));

        ScrollView scroll = new ScrollView(this);
        screenScroll = scroll;
        scroll.setFillViewport(true);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(Ui.dp(this, 15), Ui.dp(this, 17), Ui.dp(this, 15), Ui.dp(this, 30));
        scroll.addView(content);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        setContentView(root);
        EdgeToEdge.applyInsets(root, 0, 0, 0, 0);
    }

    private void select(Tab tab) {
        archiveRenderGeneration++;
        detailBackAction = null;
        detailRequestKey = "";
        current = tab;
        updateHeader(tab);
        if (tab == Tab.SCORE) renderScore();
        else if (tab == Tab.ARCHIVE) renderArchive(false);
        else if (tab == Tab.PHOTOS) renderArchive(true);
        else if (tab == Tab.NEWS) renderNews();
        else renderSeasons();
    }

    private void updateHeader(Tab tab) {
        if (headerSubtitle == null) return;
        if (tab == Tab.SCORE) headerSubtitle.setText("Skor merkezi • güncel veri");
        else if (tab == Tab.ARCHIVE) headerSubtitle.setText("Kulübün hafızası • arşiv");
        else if (tab == Tab.PHOTOS) headerSubtitle.setText("Tarihi kareler • fotoğraf");
        else if (tab == Tab.NEWS) headerSubtitle.setText("Haberler • duyurular");
        else headerSubtitle.setText("Geçmiş sezonlar • istatistik");
    }

    private void start(String eyebrow, String title, String subtitle, int accent) {
        scrollToTop();
        content.removeAllViews();
        content.addView(Ui.eyebrow(this, eyebrow, accent));
        TextView heading = Ui.title(this, title);
        heading.setPadding(0, Ui.dp(this, 4), 0, 0);
        content.addView(heading);
        TextView sub = Ui.text(this, subtitle, 13, Ui.MUTED);
        sub.setPadding(0, Ui.dp(this, 5), 0, Ui.dp(this, 4));
        content.addView(sub);
        content.addView(Ui.loading(this));
    }

    private void clearResults() {
        while (content.getChildCount() > 3) content.removeViewAt(3);
    }

    private void renderScore() {
        final int generation = ++scoreRenderGeneration;
        start("Canlı veri", "Balkes Skor",
                "Güncel sezonlar ve maç kayıtları otomatik yenilenir.", Ui.RED);
        getScoreManifest(new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (chooserVisible || current != Tab.SCORE || generation != scoreRenderGeneration
                        || !(json instanceof JSONObject)) return;
                JSONObject root = (JSONObject) json;
                JSONArray seasons = root.optJSONArray("availableSeasons");
                clearResults();

                if (seasons == null || seasons.length() == 0) {
                    content.addView(retryCard("Sezon verisi bulunamadı",
                            "GitHub veri listesi boş döndü. Yenileyip yeniden dene.", Ui.RED,
                            view -> refreshScoreData()));
                    return;
                }

                LinearLayout hero = Ui.heroCard(MainActivity.this);
                hero.addView(Ui.chip(MainActivity.this,
                        fromCache ? "Hemen hazır" : "Veriler güncel",
                        fromCache ? Ui.CYAN : Ui.GREEN));
                TextView big = Ui.text(MainActivity.this,
                        seasons == null ? "—" : String.valueOf(seasons.length()), 46, Ui.TEXT);
                big.setTypeface(Typeface.DEFAULT_BOLD);
                big.setPadding(0, Ui.dp(MainActivity.this, 15), 0, 0);
                hero.addView(big);
                int totalMatches = 0;
                for (int index = 0; index < seasons.length(); index++) {
                    JSONObject item = seasons.optJSONObject(index);
                    if (item != null) totalMatches += item.optInt("matchCount", 0);
                }
                hero.addView(Ui.text(MainActivity.this,
                        "erişilebilir sezon  •  " + totalMatches + " toplam maç", 14, Ui.MUTED));
                String dataVersion = DataEndpoints.scoreDataVersion();
                TextView source = Ui.text(MainActivity.this,
                        "Uygulama " + BuildConfig.VERSION_NAME
                                + "  •  Veri " + (dataVersion.length() == 0 ? "canlı" : dataVersion)
                                + "  •  GitHub + CDN yedekli",
                        11, Ui.MUTED);
                source.setPadding(0, Ui.dp(MainActivity.this, 8), 0, 0);
                hero.addView(source);
                if (seasons.length() > 0) {
                    JSONObject season = featuredSeason(seasons);
                    if (season != null) {
                        TextView active = strong("Son puan tablosu  "
                                + season.optString("name", season.optString("id")));
                        active.setPadding(0, Ui.dp(MainActivity.this, 13), 0, 0);
                        hero.addView(active);
                        final String id = season.optString("id", "");
                        final String name = season.optString("name", id);
                        makeClickable(hero, "SEZONU VE MAÇLARI AÇ", Ui.CYAN,
                                view -> renderSeasonDetail(id, name, Tab.SCORE));
                    }
                }
                TextView refresh = Ui.eyebrow(MainActivity.this, "VERİLERİ ŞİMDİ YENİLE  ↻", Ui.GREEN);
                refresh.setPadding(0, Ui.dp(MainActivity.this, 14), 0, 0);
                refresh.setClickable(true);
                refresh.setFocusable(true);
                refresh.setOnClickListener(view -> refreshScoreData());
                hero.addView(refresh);
                content.addView(hero);

                if (seasons != null) {
                    TextView allSeasons = Ui.eyebrow(MainActivity.this,
                            "TÜM SEZONLAR  •  " + seasons.length(), Ui.CYAN);
                    allSeasons.setPadding(0, Ui.dp(MainActivity.this, 18), 0,
                            Ui.dp(MainActivity.this, 2));
                    content.addView(allSeasons);
                    for (int i = 0; i < seasons.length(); i++) {
                        JSONObject season = seasons.optJSONObject(i);
                        if (season == null) continue;
                        final String id = season.optString("id", "");
                        final String name = season.optString("name", id);
                        LinearLayout card = Ui.card(MainActivity.this);
                        card.addView(Ui.eyebrow(MainActivity.this, "Sezon", Ui.CYAN));
                        TextView seasonTitle = strong(name);
                        seasonTitle.setPadding(0, Ui.dp(MainActivity.this, 5), 0, 0);
                        card.addView(seasonTitle);
                        card.addView(Ui.text(MainActivity.this,
                                season.optInt("matchCount", 0) + " maç  •  "
                                        + (season.optString("standingsByWeekUrl", "").length() > 0
                                        ? "hafta hafta puan durumu" : "fikstür hazır"),
                                13, Ui.MUTED));
                        makeClickable(card, "SKORLARI AÇ", Ui.RED,
                                view -> renderSeasonDetail(id, name, Tab.SCORE));
                        content.addView(card);
                    }
                }
            }
            @Override public void onError(String message) {
                if (generation == scoreRenderGeneration) showError(Tab.SCORE, message);
            }
        });
    }

    private void refreshScoreData() {
        if (chooserVisible || current != Tab.SCORE || repository == null) return;
        scoreRenderGeneration++;
        start("Canlı veri", "Veriler Yenileniyor",
                "Önbellek temizlendi; maçlar ve puan tabloları yeniden alınıyor.", Ui.GREEN);
        seasonMatchUrls.clear();
        seasonStandingsUrls.clear();
        repository.clearCache(() -> {
            if (!chooserVisible && current == Tab.SCORE) renderScore();
        });
    }

    private void renderArchive(final boolean photosOnly) {
        final Tab expected = photosOnly ? Tab.PHOTOS : Tab.ARCHIVE;
        start(photosOnly ? "Tarihi kareler" : "Kulübün hafızası",
                photosOnly ? "Fotoğraf Koleksiyonu" : "Balkes Arşivi",
                photosOnly ? "Görseller ihtiyaç oldukça indirilir; uygulama hafif kalır."
                        : "Sezon hikâyeleri ve tarihi yazılar otomatik güncellenir.",
                photosOnly ? Ui.CYAN : Ui.RED);
        repository.get(DataEndpoints.archiveManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (chooserVisible || current != expected || !(json instanceof JSONObject)) return;
                JSONArray items = ((JSONObject) json).optJSONArray("items");
                clearResults();
                if (items == null) {
                    content.addView(retryCard("Arşiv hazırlanamadı",
                            "Arşiv listesi şu anda okunamıyor.", Ui.RED,
                            view -> select(expected)));
                    return;
                }

                LinearLayout summary = Ui.heroCard(MainActivity.this);
                summary.addView(Ui.chip(MainActivity.this,
                        fromCache ? "Anında önbellek" : "Canlı arşiv", fromCache ? Ui.CYAN : Ui.GREEN));
                TextView count = Ui.text(MainActivity.this, String.valueOf(items.length()), 42, Ui.TEXT);
                count.setTypeface(Typeface.DEFAULT_BOLD);
                count.setPadding(0, Ui.dp(MainActivity.this, 12), 0, 0);
                summary.addView(count);
                summary.addView(Ui.text(MainActivity.this,
                        photosOnly ? "fotoğraflı arşiv kaynaklarının tamamı" : "arşiv kaydının tamamı gösteriliyor",
                        14, Ui.MUTED));
                content.addView(summary);

                EditText search = new EditText(MainActivity.this);
                search.setSingleLine(true);
                search.setTextColor(Ui.TEXT);
                search.setHintTextColor(Ui.MUTED);
                search.setTextSize(14);
                search.setHint("Arşivlerde ara…");
                search.setInputType(InputType.TYPE_CLASS_TEXT
                        | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
                search.setImeOptions(EditorInfo.IME_ACTION_DONE);
                search.setPadding(Ui.dp(MainActivity.this, 15), Ui.dp(MainActivity.this, 12),
                        Ui.dp(MainActivity.this, 15), Ui.dp(MainActivity.this, 12));
                search.setBackground(Ui.inputBackground(MainActivity.this));
                LinearLayout.LayoutParams searchParams = new LinearLayout.LayoutParams(-1, -2);
                searchParams.setMargins(0, Ui.dp(MainActivity.this, 13), 0, Ui.dp(MainActivity.this, 2));
                content.addView(search, searchParams);

                LinearLayout results = new LinearLayout(MainActivity.this);
                results.setOrientation(LinearLayout.VERTICAL);
                content.addView(results, new LinearLayout.LayoutParams(-1, -2));
                renderArchiveResults(items, photosOnly, "", results, expected);

                search.addTextChangedListener(new TextWatcher() {
                    @Override public void beforeTextChanged(CharSequence value, int start, int count, int after) { }
                    @Override public void onTextChanged(CharSequence value, int start, int before, int count) {
                        renderArchiveResults(items, photosOnly, value.toString(), results, expected);
                    }
                    @Override public void afterTextChanged(Editable value) { }
                });
            }
            @Override public void onError(String message) { showError(expected, message); }
        });
    }

    private void renderArchiveResults(JSONArray source, boolean photosOnly, String query,
                                      LinearLayout results, Tab expected) {
        final int generation = ++archiveRenderGeneration;
        results.removeAllViews();
        String normalized = query == null ? ""
                : query.trim().toLowerCase(TURKISH);
        ArrayList<JSONObject> filtered = new ArrayList<>();

        for (int i = 0; i < source.length(); i++) {
            JSONObject item = source.optJSONObject(i);
            if (item == null) continue;
            JSONArray photos = item.optJSONArray("photos");
            if (photosOnly && (photos == null || photos.length() == 0)) continue;
            String searchable = (item.optString("title", "") + " "
                    + item.optString("season", "") + " "
                    + item.optString("summary", ""))
                    .toLowerCase(TURKISH);
            if (normalized.length() == 0 || searchable.contains(normalized)) filtered.add(item);
        }

        TextView status = Ui.eyebrow(this,
                filtered.size() + (normalized.length() == 0 ? " arşivin tamamı" : " eşleşen arşiv"),
                Ui.CYAN);
        status.setPadding(0, Ui.dp(this, 12), 0, 0);
        results.addView(status);

        if (filtered.isEmpty()) {
            results.addView(Ui.message(this, "Sonuç bulunamadı",
                    "Başka bir sezon, takım veya anahtar kelime deneyebilirsin."));
            return;
        }
        appendArchiveBatch(filtered, 0, photosOnly, results, expected, generation);
    }

    private void appendArchiveBatch(ArrayList<JSONObject> items, int start, boolean photosOnly,
                                    LinearLayout results, Tab expected, int generation) {
        if (chooserVisible || current != expected || generation != archiveRenderGeneration) return;
        int end = Math.min(start + 12, items.size());
        for (int i = start; i < end; i++) {
            results.addView(archiveListCard(items.get(i), photosOnly));
        }
        if (end < items.size()) {
            uiHandler.post(() -> appendArchiveBatch(
                    items, end, photosOnly, results, expected, generation));
        }
    }

    private LinearLayout archiveListCard(JSONObject item, boolean photosOnly) {
        JSONArray photos = item.optJSONArray("photos");
        LinearLayout card = Ui.card(this);
        card.addView(Ui.eyebrow(this,
                photosOnly && photos != null
                        ? photos.length() + " fotoğraf" : item.optString("season", "Arşiv"),
                photosOnly ? Ui.CYAN : Ui.RED));
        TextView heading = strong(item.optString("title", "İsimsiz kayıt"));
        heading.setPadding(0, Ui.dp(this, 5), 0, 0);
        card.addView(heading);
        if (photosOnly && photos != null) {
            JSONObject first = photos.optJSONObject(0);
            if (first != null) card.addView(Ui.text(this,
                    first.optString("caption", "Tarihi arşiv fotoğrafı"), 13, Ui.MUTED));
        } else {
            card.addView(Ui.text(this, item.optString("summary", ""), 13, Ui.MUTED));
        }
        makeClickable(card, photosOnly ? "FOTOĞRAF KAYDINI AÇ" : "ARŞİVİ OKU",
                photosOnly ? Ui.CYAN : Ui.RED,
                view -> renderArchiveDetail(item, photosOnly));
        return card;
    }

    private void renderNews() {
        start("Son gelişmeler", "Haber ve Duyurular",
                "Kulüple ilgili haber ve duyurular burada güncellenir.", Ui.RED);
        repository.get(DataEndpoints.newsManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (chooserVisible || current != Tab.NEWS) return;
                JSONArray items = json instanceof JSONArray
                        ? (JSONArray) json : ((JSONObject) json).optJSONArray("items");
                clearResults();
                if (items == null || items.length() == 0) {
                    content.addView(Ui.message(MainActivity.this, "Henüz duyuru yok",
                            "Yeni bir duyuru yayımlandığında burada görünecek."));
                    return;
                }
                for (int i = 0; i < items.length() && i < 12; i++) {
                    JSONObject item = items.optJSONObject(i);
                    if (item == null) continue;
                    LinearLayout card = Ui.card(MainActivity.this);
                    card.addView(Ui.eyebrow(MainActivity.this, "Duyuru", Ui.RED));
                    TextView heading = strong(item.optString("title", "Duyuru"));
                    heading.setPadding(0, Ui.dp(MainActivity.this, 5), 0, 0);
                    card.addView(heading);
                    card.addView(Ui.text(MainActivity.this, item.optString("summary", ""), 13, Ui.MUTED));
                    content.addView(card);
                }
            }
            @Override public void onError(String message) {
                showError(Tab.NEWS, message);
            }
        });
    }

    private void renderSeasons() {
        start("Kulüp tarihi", "Geçmiş Sezonlar",
                "Geçmiş sezonların maç ve sonuç kayıtlarını incele.", Ui.CYAN);
        getScoreManifest(new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (chooserVisible || current != Tab.SEASONS || !(json instanceof JSONObject)) return;
                JSONArray seasons = ((JSONObject) json).optJSONArray("availableSeasons");
                clearResults();
                if (seasons == null) {
                    content.addView(retryCard("Sezonlar hazırlanamadı",
                            "Sezon listesi şu anda okunamıyor.", Ui.CYAN,
                            view -> select(Tab.SEASONS)));
                    return;
                }
                for (int i = 0; i < seasons.length(); i++) {
                    JSONObject season = seasons.optJSONObject(i);
                    if (season == null) continue;
                    LinearLayout card = Ui.card(MainActivity.this);
                    card.addView(Ui.eyebrow(MainActivity.this, "Sezon", Ui.CYAN));
                    TextView heading = strong(season.optString("name", season.optString("id")));
                    heading.setPadding(0, Ui.dp(MainActivity.this, 5), 0, 0);
                    card.addView(heading);
                    card.addView(Ui.text(MainActivity.this,
                            season.optInt("matchCount", 0) + " maç  •  "
                                    + (season.optString("standingsByWeekUrl", "").length() > 0
                                    ? "hafta hafta puan durumu" : "fikstür hazır"),
                            13, Ui.MUTED));
                    final String id = season.optString("id", "");
                    final String name = season.optString("name", id);
                    makeClickable(card, "SEZONU AÇ", Ui.CYAN,
                            view -> renderSeasonDetail(id, name, Tab.SEASONS));
                    content.addView(card);
                }
            }
            @Override public void onError(String message) { showError(Tab.SEASONS, message); }
        });
    }

    private void makeClickable(LinearLayout card, String actionText, int accent,
                               View.OnClickListener listener) {
        card.setClickable(true);
        card.setFocusable(true);
        card.setOnClickListener(listener);
        TextView action = Ui.eyebrow(this, actionText + "  →", accent);
        action.setPadding(0, Ui.dp(this, 13), 0, 0);
        card.addView(action);
    }

    private LinearLayout beginDetail(String eyebrow, String title, String subtitle,
                                     int accent, Runnable backAction) {
        scrollToTop();
        detailBackAction = backAction;
        content.removeAllViews();

        TextView back = Ui.eyebrow(this, "←  Geri", Ui.CYAN);
        back.setPadding(0, Ui.dp(this, 5), 0, Ui.dp(this, 17));
        back.setClickable(true);
        back.setFocusable(true);
        back.setOnClickListener(view -> {
            Runnable action = detailBackAction;
            detailBackAction = null;
            if (action != null) action.run();
        });
        content.addView(back);
        content.addView(Ui.eyebrow(this, eyebrow, accent));

        TextView heading = Ui.title(this, title);
        heading.setPadding(0, Ui.dp(this, 4), 0, 0);
        content.addView(heading);

        TextView sub = Ui.text(this, subtitle, 13, Ui.MUTED);
        sub.setPadding(0, Ui.dp(this, 5), 0, Ui.dp(this, 7));
        content.addView(sub);

        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        content.addView(body, new LinearLayout.LayoutParams(-1, -2));
        return body;
    }

    private void scrollToTop() {
        if (screenScroll != null) screenScroll.post(() -> screenScroll.scrollTo(0, 0));
    }

    private void renderArchiveDetail(JSONObject item, boolean photosOnly) {
        final Tab origin = current;
        detailRequestKey = "archive:" + item.optString("id", String.valueOf(System.nanoTime()));
        LinearLayout body = beginDetail(
                photosOnly ? "Fotoğraf arşivi" : "Arşiv yazısı",
                item.optString("title", "Balkes Arşivi"),
                item.optString("season", "Balıkesirspor kulüp arşivi"),
                photosOnly ? Ui.CYAN : Ui.RED,
                () -> select(origin));

        LinearLayout hero = Ui.heroCard(this);
        hero.addView(Ui.chip(this, item.optString("season", "Arşiv"),
                photosOnly ? Ui.CYAN : Ui.RED));
        String summary = item.optString("summary", "");
        if (summary.length() > 0) {
            TextView summaryView = Ui.text(this, summary, 15, Ui.TEXT);
            summaryView.setPadding(0, Ui.dp(this, 13), 0, 0);
            hero.addView(summaryView);
        }
        body.addView(hero);

        String article = item.optString("content", "");
        if (article.length() > 0) {
            LinearLayout articleCard = Ui.card(this);
            articleCard.addView(Ui.eyebrow(this, "Tam metin", Ui.CYAN));
            TextView articleView = Ui.text(this, article, 15, Ui.TEXT);
            articleView.setPadding(0, Ui.dp(this, 10), 0, 0);
            articleView.setTextIsSelectable(true);
            articleCard.addView(articleView);
            body.addView(articleCard);
        }

        JSONArray photos = item.optJSONArray("photos");
        if (photos != null && photos.length() > 0) {
            LinearLayout photoCard = Ui.card(this);
            photoCard.addView(Ui.eyebrow(this, photos.length() + " fotoğraf kaydı", Ui.CYAN));
            int limit = Math.min(photos.length(), 4);
            for (int i = 0; i < limit; i++) {
                JSONObject photo = photos.optJSONObject(i);
                if (photo == null) continue;
                String captionText = photo.optString("caption", "Tarihi arşiv fotoğrafı");
                String asset = photo.optString("asset", "");
                String imageUrl = asset.length() > 0
                        ? DataEndpoints.archiveMedia(asset) : photo.optString("sourceUrl", "");

                ImageView image = new ImageView(this);
                image.setScaleType(ImageView.ScaleType.CENTER_CROP);
                image.setContentDescription(captionText);
                image.setBackgroundColor(Ui.SURFACE);
                LinearLayout.LayoutParams imageParams = new LinearLayout.LayoutParams(
                        -1, Ui.dp(this, 210));
                imageParams.setMargins(0, Ui.dp(this, 13), 0, 0);
                photoCard.addView(image, imageParams);
                imageLoader.load(imageUrl, image);

                TextView caption = Ui.text(this, captionText, 12, Ui.MUTED);
                caption.setPadding(0, Ui.dp(this, 7), 0, Ui.dp(this, 4));
                photoCard.addView(caption);
            }
            if (photos.length() > limit) {
                TextView remaining = Ui.eyebrow(this,
                        "+" + (photos.length() - limit) + " ek fotoğraf kaydı", Ui.RED);
                remaining.setPadding(0, Ui.dp(this, 10), 0, 0);
                photoCard.addView(remaining);
            }
            body.addView(photoCard);
        }

        String tables = item.optString("tables", "");
        if (tables.length() > 0) {
            LinearLayout tableCard = Ui.card(this);
            tableCard.addView(Ui.eyebrow(this, "Tablolar ve sonuçlar", Ui.RED));
            TextView tableText = Ui.text(this, clip(tables, 8_000), 12, Ui.MUTED);
            tableText.setTypeface(Typeface.MONOSPACE);
            tableText.setPadding(0, Ui.dp(this, 10), 0, 0);
            tableText.setTextIsSelectable(true);
            tableCard.addView(tableText);
            body.addView(tableCard);
        }
    }

    private void renderSeasonDetail(String seasonId, String seasonName, Tab origin) {
        if (seasonId == null || seasonId.length() == 0) {
            showError(origin, "Sezon kimliği bulunamadı.");
            return;
        }
        final String key = "season:" + seasonId + ":" + System.nanoTime();
        detailRequestKey = key;
        LinearLayout body = beginDetail(
                "Skor merkezi",
                seasonName + " Sezonu",
                "Maç skorları ve ayrıntılı karşılaşma kayıtları",
                Ui.CYAN,
                () -> select(origin));
        body.addView(Ui.loading(this));

        String matchesUrl = seasonMatchUrls.get(seasonId);
        if (matchesUrl == null || matchesUrl.length() == 0) {
            matchesUrl = "seasons/" + seasonId + "/matches_index.json";
        }
        getScoreJson(matchesUrl,
                new RemoteJsonRepository.Callback() {
                    @Override public void onSuccess(Object json, boolean fromCache) {
                        if (chooserVisible || !key.equals(detailRequestKey) || !(json instanceof JSONArray)) return;
                        JSONArray matches = (JSONArray) json;
                        body.removeAllViews();

                        LinearLayout summary = Ui.heroCard(MainActivity.this);
                        summary.addView(Ui.chip(MainActivity.this,
                                fromCache ? "Hemen hazır" : "Veriler güncel",
                                fromCache ? Ui.CYAN : Ui.GREEN));
                        TextView count = Ui.text(MainActivity.this, String.valueOf(matches.length()), 42, Ui.TEXT);
                        count.setTypeface(Typeface.DEFAULT_BOLD);
                        count.setPadding(0, Ui.dp(MainActivity.this, 12), 0, 0);
                        summary.addView(count);
                        summary.addView(Ui.text(MainActivity.this,
                                "maç kaydının tamamı bu sayfada", 14, Ui.MUTED));
                        TextView dataSource = Ui.text(MainActivity.this,
                                "GitHub veri sürümü " + DataEndpoints.scoreDataVersion()
                                        + "  •  CDN yedeği etkin",
                                11, Ui.MUTED);
                        dataSource.setPadding(0, Ui.dp(MainActivity.this, 7), 0, 0);
                        summary.addView(dataSource);
                        body.addView(summary);

                        TextView standingsHeading = Ui.eyebrow(MainActivity.this,
                                "PUAN DURUMU  •  HAFTA HAFTA", Ui.CYAN);
                        standingsHeading.setPadding(0, Ui.dp(MainActivity.this, 20), 0, 0);
                        body.addView(standingsHeading);
                        LinearLayout standingsSlot = new LinearLayout(MainActivity.this);
                        standingsSlot.setOrientation(LinearLayout.VERTICAL);
                        body.addView(standingsSlot, new LinearLayout.LayoutParams(-1, -2));
                        loadSeasonStandings(seasonId, key, standingsSlot);

                        TextView matchesHeading = Ui.eyebrow(MainActivity.this,
                                "TÜM MAÇLAR  •  " + matches.length(), Ui.RED);
                        matchesHeading.setPadding(0, Ui.dp(MainActivity.this, 21), 0,
                                Ui.dp(MainActivity.this, 2));
                        body.addView(matchesHeading);

                        if (matches.length() == 0) {
                            body.addView(Ui.message(MainActivity.this, "Maç kaydı yok",
                                    "Bu sezonun fikstürü henüz yayımlanmadı."));
                        }

                        for (int i = 0; i < matches.length(); i++) {
                            JSONObject match = matches.optJSONObject(i);
                            if (match == null) continue;
                            final JSONObject selectedMatch = match;
                            LinearLayout card = Ui.card(MainActivity.this);
                            card.addView(Ui.eyebrow(MainActivity.this,
                                    match.optString("roundLabel",
                                            match.optString("stage", "Maç")), resultColor(match)));
                            TextView teams = strong(match.optString("homeTeam", "Ev sahibi")
                                    + "\n" + scoreDisplay(match) + "\n"
                                    + match.optString("awayTeam", "Deplasman"));
                            teams.setGravity(Gravity.CENTER);
                            teams.setPadding(0, Ui.dp(MainActivity.this, 8), 0, 0);
                            card.addView(teams);
                            TextView date = Ui.text(MainActivity.this,
                                    match.optString("dateDisplay", "") + "  •  "
                                            + match.optString("competitionLabel",
                                                    match.optString("competitionType", "Maç")),
                                    12, Ui.MUTED);
                            date.setGravity(Gravity.CENTER);
                            date.setPadding(0, Ui.dp(MainActivity.this, 5), 0, 0);
                            card.addView(date);
                            makeClickable(card, "MAÇ DETAYINI AÇ", Ui.CYAN,
                                    view -> renderMatchDetail(selectedMatch, seasonId, seasonName, origin));
                            body.addView(card);
                        }
                    }

                    @Override public void onError(String message) {
                        if (chooserVisible || !key.equals(detailRequestKey)) return;
                        body.removeAllViews();
                        body.addView(retryCard("Skorlar açılamadı", friendlyError(message), Ui.RED,
                                view -> renderSeasonDetail(seasonId, seasonName, origin)));
                    }
                });
    }

    private void loadSeasonStandings(String seasonId, String requestKey, LinearLayout slot) {
        String standingsUrl = seasonStandingsUrls.get(seasonId);
        if (standingsUrl == null || standingsUrl.length() == 0) {
            slot.removeAllViews();
            slot.addView(Ui.message(this, "Puan durumu henüz oluşmadı",
                    "Bu sezonda oynanmış lig maçı veya yayımlanmış resmi tablo bulunmuyor."));
            return;
        }
        slot.removeAllViews();
        slot.addView(Ui.loading(this));
        getScoreJson(standingsUrl,
                new RemoteJsonRepository.Callback() {
                    @Override public void onSuccess(Object json, boolean fromCache) {
                        if (chooserVisible || !requestKey.equals(detailRequestKey)
                                || !(json instanceof JSONArray)) return;
                        JSONArray snapshots = (JSONArray) json;
                        int latest = latestStandingSnapshot(snapshots);
                        if (latest < 0) {
                            slot.removeAllViews();
                            slot.addView(retryCard("Puan durumu boş",
                                    "Resmi haftalık tablo dosyasında gösterilecek satır bulunamadı.",
                                    Ui.CYAN,
                                    view -> loadSeasonStandings(seasonId, requestKey, slot)));
                            return;
                        }
                        renderStandingSnapshot(slot, snapshots, latest);
                    }

                    @Override public void onError(String message) {
                        if (chooserVisible || !requestKey.equals(detailRequestKey)) return;
                        slot.removeAllViews();
                        slot.addView(retryCard("Puan durumu açılamadı",
                                friendlyError(message) + " GitHub CDN yedeği de denendi.", Ui.CYAN,
                                view -> loadSeasonStandings(seasonId, requestKey, slot)));
                    }
                });
    }

    private int latestStandingSnapshot(JSONArray snapshots) {
        for (int index = snapshots.length() - 1; index >= 0; index--) {
            JSONObject snapshot = snapshots.optJSONObject(index);
            JSONArray rows = snapshot == null ? null : snapshot.optJSONArray("standings");
            if (rows != null && rows.length() > 0) return index;
        }
        return -1;
    }

    private void renderStandingSnapshot(LinearLayout slot, JSONArray snapshots, int index) {
        if (index < 0 || index >= snapshots.length()) return;
        JSONObject snapshot = snapshots.optJSONObject(index);
        JSONArray rows = snapshot == null ? null : snapshot.optJSONArray("standings");
        if (snapshot == null || rows == null || rows.length() == 0) return;

        slot.removeAllViews();
        LinearLayout card = Ui.card(this);
        String source = snapshot.optString("source", "");
        card.addView(Ui.eyebrow(this,
                source.startsWith("official_tff") ? "Resmi TFF puan durumu" : "Puan durumu",
                Ui.CYAN));
        TextView week = strong(snapshot.optInt("week", index + 1) + ". Hafta");
        week.setPadding(0, Ui.dp(this, 5), 0, Ui.dp(this, 9));
        card.addView(week);

        LinearLayout navigation = new LinearLayout(this);
        navigation.setOrientation(LinearLayout.HORIZONTAL);
        navigation.setGravity(Gravity.CENTER_VERTICAL);
        TextView previous = Ui.eyebrow(this, "← ÖNCEKİ", Ui.CYAN);
        previous.setGravity(Gravity.START);
        previous.setAlpha(index > 0 ? 1f : 0.28f);
        if (index > 0) {
            previous.setClickable(true);
            previous.setFocusable(true);
            previous.setOnClickListener(view -> renderStandingSnapshot(slot, snapshots, index - 1));
        }
        navigation.addView(previous, new LinearLayout.LayoutParams(0, -2, 1f));

        TextView position = Ui.text(this, (index + 1) + " / " + snapshots.length(), 11, Ui.MUTED);
        position.setGravity(Gravity.CENTER);
        navigation.addView(position, new LinearLayout.LayoutParams(0, -2, 1f));

        TextView next = Ui.eyebrow(this, "SONRAKİ →", Ui.CYAN);
        next.setGravity(Gravity.END);
        next.setAlpha(index + 1 < snapshots.length() ? 1f : 0.28f);
        if (index + 1 < snapshots.length()) {
            next.setClickable(true);
            next.setFocusable(true);
            next.setOnClickListener(view -> renderStandingSnapshot(slot, snapshots, index + 1));
        }
        navigation.addView(next, new LinearLayout.LayoutParams(0, -2, 1f));
        card.addView(navigation);

        TextView labels = Ui.eyebrow(this,
                "O: OYNANAN  •  G: GALİBİYET  •  B: BERABERLİK  •  M: MAĞLUBİYET",
                Ui.MUTED);
        labels.setTextSize(9);
        labels.setPadding(0, Ui.dp(this, 13), 0, Ui.dp(this, 5));
        card.addView(labels);
        for (int rowIndex = 0; rowIndex < rows.length(); rowIndex++) {
            JSONObject row = rows.optJSONObject(rowIndex);
            if (row == null) continue;
            card.addView(standingRow(row, rowIndex));
        }
        TextView legend = Ui.text(this,
                "A: Atılan  •  Y: Yenilen  •  AV: Averaj  •  P: Puan", 10, Ui.MUTED);
        legend.setPadding(0, Ui.dp(this, 9), 0, 0);
        card.addView(legend);
        slot.addView(card);
    }

    private LinearLayout standingRow(JSONObject item, int rowIndex) {
        String team = item.optString("team", "—");
        boolean isBalkes = item.optBoolean("isBalkes", false)
                || team.toLowerCase(TURKISH).contains("balıkesirspor")
                || team.toLowerCase(Locale.ROOT).contains("balikesirspor");
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(Ui.dp(this, 7), Ui.dp(this, 7), Ui.dp(this, 7), Ui.dp(this, 7));
        if (isBalkes) {
            row.setBackground(Ui.rounded(this, Color.argb(42, 255, 18, 76),
                    Color.argb(175, 255, 18, 76), 10, 1));
        }

        TextView rankView = Ui.text(this,
                String.valueOf(item.optInt("rank", rowIndex + 1)), 12,
                isBalkes ? Ui.RED : Ui.MUTED);
        rankView.setTypeface(Typeface.MONOSPACE, isBalkes ? Typeface.BOLD : Typeface.NORMAL);
        row.addView(rankView, new LinearLayout.LayoutParams(Ui.dp(this, 30), -2));

        LinearLayout teamBox = new LinearLayout(this);
        teamBox.setOrientation(LinearLayout.VERTICAL);
        TextView teamView = Ui.text(this, team, 12, isBalkes ? Ui.TEXT : Ui.MUTED);
        if (isBalkes) teamView.setTypeface(Typeface.DEFAULT_BOLD);
        teamBox.addView(teamView);
        String stats = "O " + item.optInt("played", 0)
                + "  G " + item.optInt("won", 0)
                + "  B " + item.optInt("drawn", 0)
                + "  M " + item.optInt("lost", 0)
                + "\nA " + item.optInt("goalsFor", 0)
                + "  Y " + item.optInt("goalsAgainst", 0)
                + "  AV " + signed(item.optInt("goalDifference", 0));
        TextView statsView = Ui.text(this, stats, 10, isBalkes ? Ui.CYAN : Ui.MUTED);
        statsView.setTypeface(Typeface.MONOSPACE, isBalkes ? Typeface.BOLD : Typeface.NORMAL);
        statsView.setPadding(0, Ui.dp(this, 3), 0, 0);
        teamBox.addView(statsView);
        row.addView(teamBox, new LinearLayout.LayoutParams(0, -2, 1f));

        TextView pointsView = Ui.text(this, item.optInt("points", 0) + "\nP", 13,
                isBalkes ? Ui.CYAN : Ui.TEXT);
        pointsView.setTypeface(Typeface.DEFAULT_BOLD);
        pointsView.setGravity(Gravity.CENTER);
        row.addView(pointsView, new LinearLayout.LayoutParams(Ui.dp(this, 45), -2));
        return row;
    }

    private String signed(int value) {
        return value > 0 ? "+" + value : String.valueOf(value);
    }

    private void renderMatchDetail(JSONObject match, String seasonId, String seasonName, Tab origin) {
        final String key = "match:" + match.optString("id", "") + ":" + System.nanoTime();
        detailRequestKey = key;
        String home = match.optString("homeTeam", "Ev sahibi");
        String away = match.optString("awayTeam", "Deplasman");
        LinearLayout body = beginDetail(
                match.optString("stage", "Maç detayı"),
                home + "  " + scoreDisplay(match) + "  " + away,
                match.optString("dateDisplay", seasonName),
                resultColor(match),
                () -> renderSeasonDetail(seasonId, seasonName, origin));

        LinearLayout scoreboard = Ui.heroCard(this);
        TextView homeView = Ui.text(this, home, 17, Ui.TEXT);
        homeView.setTypeface(Typeface.DEFAULT_BOLD);
        homeView.setGravity(Gravity.CENTER);
        scoreboard.addView(homeView);
        TextView scoreView = Ui.text(this, scoreDisplay(match), 44, resultColor(match));
        scoreView.setTypeface(Typeface.DEFAULT_BOLD);
        scoreView.setGravity(Gravity.CENTER);
        scoreView.setPadding(0, Ui.dp(this, 9), 0, Ui.dp(this, 9));
        scoreboard.addView(scoreView);
        TextView awayView = Ui.text(this, away, 17, Ui.TEXT);
        awayView.setTypeface(Typeface.DEFAULT_BOLD);
        awayView.setGravity(Gravity.CENTER);
        scoreboard.addView(awayView);
        body.addView(scoreboard);

        LinearLayout extra = new LinearLayout(this);
        extra.setOrientation(LinearLayout.VERTICAL);
        extra.addView(Ui.loading(this));
        body.addView(extra, new LinearLayout.LayoutParams(-1, -2));

        String detailUrl = match.optString("detailUrl", "");
        if (detailUrl.length() == 0) {
            extra.removeAllViews();
            extra.addView(Ui.message(this, "Özet kayıt", "Bu maç için ayrıntılı olay dosyası bulunmuyor."));
            return;
        }

        getScoreJson(detailUrl, new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (chooserVisible || !key.equals(detailRequestKey) || !(json instanceof JSONObject)) return;
                JSONObject detail = (JSONObject) json;
                extra.removeAllViews();

                JSONArray events = detail.optJSONArray("events");
                if (events != null && events.length() > 0) {
                    LinearLayout eventCard = Ui.card(MainActivity.this);
                    eventCard.addView(Ui.eyebrow(MainActivity.this, "Maç olayları", Ui.RED));
                    int limit = Math.min(events.length(), 35);
                    for (int i = 0; i < limit; i++) {
                        JSONObject event = events.optJSONObject(i);
                        if (event == null) continue;
                        TextView line = Ui.text(MainActivity.this, eventText(event), 13, Ui.TEXT);
                        line.setPadding(0, Ui.dp(MainActivity.this, 8), 0, 0);
                        eventCard.addView(line);
                    }
                    extra.addView(eventCard);
                }

                JSONArray referees = detail.optJSONArray("referees");
                if (referees != null && referees.length() > 0) {
                    LinearLayout refereeCard = Ui.card(MainActivity.this);
                    refereeCard.addView(Ui.eyebrow(MainActivity.this, "Hakemler", Ui.CYAN));
                    for (int i = 0; i < referees.length(); i++) {
                        JSONObject referee = referees.optJSONObject(i);
                        if (referee == null) continue;
                        TextView line = Ui.text(MainActivity.this,
                                referee.optString("role_tr", "Hakem") + " • "
                                        + referee.optString("name", ""), 13, Ui.MUTED);
                        line.setPadding(0, Ui.dp(MainActivity.this, 7), 0, 0);
                        refereeCard.addView(line);
                    }
                    extra.addView(refereeCard);
                }

                if (events == null || events.length() == 0) {
                    extra.addView(Ui.message(MainActivity.this, "Maç özeti",
                            "Skor kaydı açıldı; bu karşılaşmada olay verisi bulunmuyor."));
                }
            }

            @Override public void onError(String message) {
                if (chooserVisible || !key.equals(detailRequestKey)) return;
                extra.removeAllViews();
                extra.addView(retryCard("Maç detayı açılamadı", friendlyError(message), Ui.RED,
                        view -> renderMatchDetail(match, seasonId, seasonName, origin)));
            }
        });
    }

    private String scoreDisplay(JSONObject match) {
        JSONObject score = match.optJSONObject("score");
        if (score == null) return "-";
        return score.optString("display", score.optInt("home", 0) + "-" + score.optInt("away", 0));
    }

    private int resultColor(JSONObject match) {
        JSONObject balkes = match.optJSONObject("balkes");
        String result = balkes == null ? "" : balkes.optString("result", "");
        if ("W".equals(result)) return Ui.GREEN;
        if ("L".equals(result)) return Ui.RED;
        return Ui.CYAN;
    }

    private String eventText(JSONObject event) {
        String minute = event.optString("minute_text", "");
        String type = event.optString("type", "");
        String team = event.optString("team", "");
        if ("goal".equals(type)) {
            return minute + "  GOL • " + event.optString("player", "") + "  " + team;
        }
        if ("yellow_card".equals(type)) {
            return minute + "  SARI KART • " + event.optString("player", "") + "  " + team;
        }
        if ("red_card".equals(type)) {
            return minute + "  KIRMIZI KART • " + event.optString("player", "") + "  " + team;
        }
        if ("substitution".equals(type)) {
            return minute + "  DEĞİŞİKLİK • " + event.optString("player_out", "")
                    + " → " + event.optString("player_in", "") + "  " + team;
        }
        return minute + "  " + event.optString("raw", type) + "  " + team;
    }

    private String clip(String value, int max) {
        if (value == null) return "";
        if (value.length() <= max) return value;
        return value.substring(0, max) + "\n…";
    }

    private TextView strong(String value) {
        TextView view = Ui.text(this, value, 17, Ui.TEXT);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setGravity(Gravity.START);
        return view;
    }

    private void showError(Tab expected, String message) {
        if (chooserVisible || current != expected) return;
        clearResults();
        content.addView(retryCard("İçerik açılamadı", friendlyError(message),
                expected == Tab.ARCHIVE || expected == Tab.SCORE || expected == Tab.NEWS
                        ? Ui.RED : Ui.CYAN,
                view -> select(expected)));
    }

    private ImageView brandLogo() {
        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.balkes_logo);
        logo.setScaleType(ImageView.ScaleType.CENTER_CROP);
        logo.setContentDescription("Balkes logosu");
        logo.setBackgroundColor(Color.BLACK);
        return logo;
    }

    private LinearLayout retryCard(String title, String message, int accent,
                                   View.OnClickListener retry) {
        LinearLayout card = Ui.card(this);
        card.addView(Ui.eyebrow(this, "Bağlantı sorunu", accent));
        TextView heading = strong(title);
        heading.setPadding(0, Ui.dp(this, 6), 0, 0);
        card.addView(heading);
        TextView detail = Ui.text(this, message, 13, Ui.MUTED);
        detail.setPadding(0, Ui.dp(this, 7), 0, 0);
        card.addView(detail);
        makeClickable(card, "TEKRAR DENE", accent, retry);
        return card;
    }

    private String friendlyError(String message) {
        if (message == null || message.trim().length() == 0) {
            return "İnternet bağlantını kontrol edip yeniden deneyebilirsin.";
        }
        return message.trim();
    }
}
