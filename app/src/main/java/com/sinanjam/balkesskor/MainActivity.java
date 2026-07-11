package com.sinanjam.balkesskor;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.sinanjam.balkesskor.data.DataEndpoints;
import com.sinanjam.balkesskor.data.RemoteJsonRepository;
import com.sinanjam.balkesskor.ui.Ui;

import org.json.JSONArray;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    private enum Tab { SCORE, ARCHIVE, PHOTOS, NEWS, SEASONS }

    private RemoteJsonRepository repository;
    private LinearLayout content;
    private LinearLayout tabs;
    private TextView headerTitle;
    private TextView headerSubtitle;
    private Tab current = Tab.SCORE;
    private boolean chooserVisible = true;
    private Runnable detailBackAction;
    private String detailRequestKey = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        repository = new RemoteJsonRepository(this);
        warmScoreData();
        repository.prefetch(DataEndpoints.archiveManifest());
        showEntryChoice();
    }

    private void warmScoreData() {
        repository.get(DataEndpoints.scoreManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (!(json instanceof JSONObject)) return;
                JSONArray seasons = ((JSONObject) json).optJSONArray("availableSeasons");
                if (seasons == null || seasons.length() == 0) return;
                JSONObject first = seasons.optJSONObject(0);
                if (first == null) return;
                String id = first.optString("id", "");
                if (id.length() == 0) return;
                repository.prefetch(DataEndpoints.scoreFile("seasons/" + id + "/season.json"));
                repository.prefetch(DataEndpoints.scoreFile("seasons/" + id + "/matches_index.json"));
            }

            @Override public void onError(String message) { }
        });
    }

    @Override
    protected void onDestroy() {
        repository.close();
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
        chooserVisible = true;
        detailBackAction = null;
        detailRequestKey = "";
        content = null;
        tabs = null;
        getWindow().setStatusBarColor(Color.rgb(40, 2, 14));
        getWindow().setNavigationBarColor(Ui.BACKGROUND);

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackground(Ui.appBackground());

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(Ui.dp(this, 22), Ui.dp(this, 34), Ui.dp(this, 22), Ui.dp(this, 30));
        scroll.addView(root, new ScrollView.LayoutParams(-1, -1));

        TextView badge = Ui.text(this, "B", 42, Color.WHITE);
        badge.setTypeface(Typeface.DEFAULT_BOLD);
        badge.setGravity(Gravity.CENTER);
        badge.setBackground(Ui.badgeBackground(this));
        badge.setElevation(Ui.dp(this, 12));
        root.addView(badge, new LinearLayout.LayoutParams(Ui.dp(this, 82), Ui.dp(this, 82)));

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

        TextView footer = Ui.text(this, "Veriler GitHub üzerinden güvenli biçimde güncellenir", 11, Ui.MUTED);
        footer.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams footerParams = new LinearLayout.LayoutParams(-1, -2);
        footerParams.setMargins(0, Ui.dp(this, 27), 0, 0);
        root.addView(footer, footerParams);

        setContentView(scroll);
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
        getWindow().setStatusBarColor(Color.rgb(44, 3, 17));
        getWindow().setNavigationBarColor(Ui.BACKGROUND);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Ui.BACKGROUND);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(Ui.dp(this, 15), Ui.dp(this, 13), Ui.dp(this, 14), Ui.dp(this, 13));
        header.setBackground(Ui.headerBackground());
        header.setElevation(Ui.dp(this, 8));

        TextView badge = Ui.text(this, "B", 23, Color.WHITE);
        badge.setTypeface(Typeface.DEFAULT_BOLD);
        badge.setGravity(Gravity.CENTER);
        badge.setBackground(Ui.badgeBackground(this));
        header.addView(badge, new LinearLayout.LayoutParams(Ui.dp(this, 52), Ui.dp(this, 52)));

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

        TextView change = Ui.chip(this, "Değiştir", Color.WHITE);
        change.setOnClickListener(view -> showEntryChoice());
        header.addView(change, new LinearLayout.LayoutParams(-2, -2));
        root.addView(header, new LinearLayout.LayoutParams(-1, -2));

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(Ui.dp(this, 15), Ui.dp(this, 17), Ui.dp(this, 15), Ui.dp(this, 30));
        scroll.addView(content);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout bottom = new LinearLayout(this);
        bottom.setOrientation(LinearLayout.VERTICAL);
        bottom.setBackgroundColor(Ui.SURFACE);

        View neonLine = new View(this);
        neonLine.setBackground(Ui.neonLine());
        bottom.addView(neonLine, new LinearLayout.LayoutParams(-1, Ui.dp(this, 1)));

        tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);
        tabs.setGravity(Gravity.CENTER);
        tabs.setPadding(Ui.dp(this, 5), Ui.dp(this, 5), Ui.dp(this, 5), Ui.dp(this, 3));
        bottom.addView(tabs, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(bottom, new LinearLayout.LayoutParams(-1, Ui.dp(this, 62)));
        setContentView(root);
    }

    private void select(Tab tab) {
        detailBackAction = null;
        detailRequestKey = "";
        current = tab;
        updateHeader(tab);
        renderTabs();
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

    private void renderTabs() {
        tabs.removeAllViews();
        addTab("Skor", Tab.SCORE);
        addTab("Arşiv", Tab.ARCHIVE);
        addTab("Foto", Tab.PHOTOS);
        addTab("Haber", Tab.NEWS);
        addTab("Sezon", Tab.SEASONS);
    }

    private void addTab(String label, Tab tab) {
        boolean active = current == tab;
        LinearLayout item = new LinearLayout(this);
        item.setOrientation(LinearLayout.VERTICAL);
        item.setGravity(Gravity.CENTER);
        item.setBackgroundColor(Color.TRANSPARENT);
        item.setClickable(true);
        item.setFocusable(true);
        item.setOnClickListener(view -> select(tab));

        TextView text = Ui.text(this, label, 11, active ? Ui.CYAN : Ui.MUTED);
        text.setTypeface(active ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
        text.setGravity(Gravity.CENTER);
        item.addView(text, new LinearLayout.LayoutParams(-1, 0, 1));

        View line = new View(this);
        line.setBackgroundColor(active ? Ui.CYAN : Color.TRANSPARENT);
        LinearLayout.LayoutParams lineParams = new LinearLayout.LayoutParams(Ui.dp(this, 24), Ui.dp(this, 2));
        lineParams.setMargins(0, 0, 0, Ui.dp(this, 2));
        item.addView(line, lineParams);

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1);
        tabs.addView(item, params);
    }

    private void start(String eyebrow, String title, String subtitle, int accent) {
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
        start("Canlı veri", "Balkes Skor", "Güncel sezon özeti GitHub veri deposundan gelir.", Ui.RED);
        repository.get(DataEndpoints.scoreManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (chooserVisible || current != Tab.SCORE || !(json instanceof JSONObject)) return;
                JSONObject root = (JSONObject) json;
                JSONArray seasons = root.optJSONArray("availableSeasons");
                clearResults();

                LinearLayout hero = Ui.heroCard(MainActivity.this);
                hero.addView(Ui.chip(MainActivity.this,
                        fromCache ? "Hızlı önbellek" : "GitHub güncel", fromCache ? Ui.CYAN : Ui.GREEN));
                TextView big = Ui.text(MainActivity.this,
                        seasons == null ? "—" : String.valueOf(seasons.length()), 46, Ui.TEXT);
                big.setTypeface(Typeface.DEFAULT_BOLD);
                big.setPadding(0, Ui.dp(MainActivity.this, 15), 0, 0);
                hero.addView(big);
                hero.addView(Ui.text(MainActivity.this, "erişilebilir sezon", 14, Ui.MUTED));
                if (seasons != null && seasons.length() > 0) {
                    JSONObject season = seasons.optJSONObject(0);
                    if (season != null) {
                        TextView active = strong("Aktif sezon  " + season.optString("name", season.optString("id")));
                        active.setPadding(0, Ui.dp(MainActivity.this, 13), 0, 0);
                        hero.addView(active);
                        final String id = season.optString("id", "");
                        final String name = season.optString("name", id);
                        makeClickable(hero, "SEZONU VE MAÇLARI AÇ", Ui.CYAN,
                                view -> renderSeasonDetail(id, name, Tab.SCORE));
                    }
                }
                content.addView(hero);

                if (seasons != null) {
                    int limit = Math.min(seasons.length(), 6);
                    for (int i = 0; i < limit; i++) {
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
                                season.optInt("matchCount", 0) + " maç kaydı", 13, Ui.MUTED));
                        makeClickable(card, "SKORLARI AÇ", Ui.RED,
                                view -> renderSeasonDetail(id, name, Tab.SCORE));
                        content.addView(card);
                    }
                }
            }
            @Override public void onError(String message) { showError(Tab.SCORE, message); }
        });
    }

    private void renderArchive(final boolean photosOnly) {
        final Tab expected = photosOnly ? Tab.PHOTOS : Tab.ARCHIVE;
        start(photosOnly ? "Tarihi kareler" : "Kulübün hafızası",
                photosOnly ? "Fotoğraf Koleksiyonu" : "Balkes Arşivi",
                photosOnly ? "Görseller APK içinde değil; ihtiyaç oldukça GitHub'dan gelir."
                        : "Sezon hikâyeleri ve tarihi yazılar uzaktaki manifestten gelir.",
                photosOnly ? Ui.CYAN : Ui.RED);
        repository.get(DataEndpoints.archiveManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (chooserVisible || current != expected || !(json instanceof JSONObject)) return;
                JSONArray items = ((JSONObject) json).optJSONArray("items");
                clearResults();
                if (items == null) {
                    content.addView(Ui.message(MainActivity.this, "Boş manifest", "items dizisi bulunamadı."));
                    return;
                }

                LinearLayout summary = Ui.heroCard(MainActivity.this);
                summary.addView(Ui.chip(MainActivity.this,
                        fromCache ? "Anında önbellek" : "Canlı arşiv", fromCache ? Ui.CYAN : Ui.GREEN));
                TextView count = Ui.text(MainActivity.this, String.valueOf(items.length()), 42, Ui.TEXT);
                count.setTypeface(Typeface.DEFAULT_BOLD);
                count.setPadding(0, Ui.dp(MainActivity.this, 12), 0, 0);
                summary.addView(count);
                summary.addView(Ui.text(MainActivity.this, photosOnly ? "arşiv kaynağı tarandı" : "arşiv kaydı bulundu", 14, Ui.MUTED));
                content.addView(summary);

                int shown = 0;
                for (int i = 0; i < items.length() && shown < 10; i++) {
                    JSONObject item = items.optJSONObject(i);
                    if (item == null) continue;
                    JSONArray photos = item.optJSONArray("photos");
                    if (photosOnly && (photos == null || photos.length() == 0)) continue;
                    LinearLayout card = Ui.card(MainActivity.this);
                    card.addView(Ui.eyebrow(MainActivity.this,
                            photosOnly ? photos.length() + " fotoğraf" : item.optString("season", "Arşiv"),
                            photosOnly ? Ui.CYAN : Ui.RED));
                    TextView heading = strong(item.optString("title", "İsimsiz kayıt"));
                    heading.setPadding(0, Ui.dp(MainActivity.this, 5), 0, 0);
                    card.addView(heading);
                    if (photosOnly) {
                        JSONObject first = photos.optJSONObject(0);
                        if (first != null) card.addView(Ui.text(MainActivity.this,
                                first.optString("caption", "Tarihi arşiv fotoğrafı"), 13, Ui.MUTED));
                    } else {
                        card.addView(Ui.text(MainActivity.this, item.optString("summary", ""), 13, Ui.MUTED));
                    }
                    final JSONObject selectedItem = item;
                    makeClickable(card, photosOnly ? "FOTOĞRAF KAYDINI AÇ" : "ARŞİVİ OKU",
                            photosOnly ? Ui.CYAN : Ui.RED,
                            view -> renderArchiveDetail(selectedItem, photosOnly));
                    content.addView(card);
                    shown++;
                }
            }
            @Override public void onError(String message) { showError(expected, message); }
        });
    }

    private void renderNews() {
        start("Son gelişmeler", "Haber ve Duyurular",
                "Yeni veri deposundaki news/index.json sözleşmesini kullanır.", Ui.RED);
        repository.get(DataEndpoints.newsManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (chooserVisible || current != Tab.NEWS) return;
                JSONArray items = json instanceof JSONArray
                        ? (JSONArray) json : ((JSONObject) json).optJSONArray("items");
                clearResults();
                if (items == null || items.length() == 0) {
                    content.addView(Ui.message(MainActivity.this, "Henüz duyuru yok", "Manifest geçerli fakat içerik boş."));
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
                if (chooserVisible || current != Tab.NEWS) return;
                clearResults();
                content.addView(Ui.message(MainActivity.this, "Veri deposu bekleniyor",
                        "news/index.json henüz yayımlanmadı. URL, CONTENT_BASE_URL ile değiştirilebilir."));
            }
        });
    }

    private void renderSeasons() {
        start("Kulüp tarihi", "Geçmiş Sezonlar",
                "Skor manifestindeki sezon dizini tek kaynak olarak kullanılır.", Ui.CYAN);
        repository.get(DataEndpoints.scoreManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (chooserVisible || current != Tab.SEASONS || !(json instanceof JSONObject)) return;
                JSONArray seasons = ((JSONObject) json).optJSONArray("availableSeasons");
                clearResults();
                if (seasons == null) {
                    content.addView(Ui.message(MainActivity.this, "Sezon yok", "availableSeasons bulunamadı."));
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
                            season.optInt("matchCount", 0) + " maç kaydı", 13, Ui.MUTED));
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
            int limit = Math.min(photos.length(), 6);
            for (int i = 0; i < limit; i++) {
                JSONObject photo = photos.optJSONObject(i);
                if (photo == null) continue;
                TextView caption = Ui.text(this,
                        "• " + photo.optString("caption", "Tarihi arşiv fotoğrafı"), 13, Ui.MUTED);
                caption.setPadding(0, Ui.dp(this, 8), 0, 0);
                photoCard.addView(caption);
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

        repository.get(DataEndpoints.scoreFile("seasons/" + seasonId + "/matches_index.json"),
                new RemoteJsonRepository.Callback() {
                    @Override public void onSuccess(Object json, boolean fromCache) {
                        if (chooserVisible || !key.equals(detailRequestKey) || !(json instanceof JSONArray)) return;
                        JSONArray matches = (JSONArray) json;
                        body.removeAllViews();

                        LinearLayout summary = Ui.heroCard(MainActivity.this);
                        summary.addView(Ui.chip(MainActivity.this,
                                fromCache ? "Hızlı önbellek" : "GitHub güncel",
                                fromCache ? Ui.CYAN : Ui.GREEN));
                        TextView count = Ui.text(MainActivity.this, String.valueOf(matches.length()), 42, Ui.TEXT);
                        count.setTypeface(Typeface.DEFAULT_BOLD);
                        count.setPadding(0, Ui.dp(MainActivity.this, 12), 0, 0);
                        summary.addView(count);
                        summary.addView(Ui.text(MainActivity.this, "maç kaydı", 14, Ui.MUTED));
                        body.addView(summary);

                        for (int i = 0; i < matches.length(); i++) {
                            JSONObject match = matches.optJSONObject(i);
                            if (match == null) continue;
                            final JSONObject selectedMatch = match;
                            LinearLayout card = Ui.card(MainActivity.this);
                            card.addView(Ui.eyebrow(MainActivity.this,
                                    match.optString("stage", "Maç"), resultColor(match)));
                            TextView teams = strong(match.optString("homeTeam", "Ev sahibi")
                                    + "\n" + scoreDisplay(match) + "\n"
                                    + match.optString("awayTeam", "Deplasman"));
                            teams.setGravity(Gravity.CENTER);
                            teams.setPadding(0, Ui.dp(MainActivity.this, 8), 0, 0);
                            card.addView(teams);
                            TextView date = Ui.text(MainActivity.this,
                                    match.optString("dateDisplay", ""), 12, Ui.MUTED);
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
                        body.addView(Ui.message(MainActivity.this, "Skorlar açılamadı", message));
                    }
                });
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

        repository.get(DataEndpoints.scoreFile(detailUrl), new RemoteJsonRepository.Callback() {
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
                extra.addView(Ui.message(MainActivity.this, "Detay alınamadı", message));
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
        content.addView(Ui.message(this, "Bağlantı kurulamadı", message));
    }
}
