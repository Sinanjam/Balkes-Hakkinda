package com.sinanjam.balkesskor;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
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

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        repository = new RemoteJsonRepository(this);
        repository.prefetch(DataEndpoints.scoreManifest());
        repository.prefetch(DataEndpoints.archiveManifest());
        showEntryChoice();
    }

    @Override
    protected void onDestroy() {
        repository.close();
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        if (!chooserVisible) {
            showEntryChoice();
            return;
        }
        super.onBackPressed();
    }

    private void showEntryChoice() {
        chooserVisible = true;
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

        TextView brand = Ui.eyebrow(this, "Balıkesirspor Dijital Merkezi", Ui.GOLD);
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
                Ui.GOLD,
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
        headerSubtitle = Ui.text(this, "Balıkesirspor dijital merkezi", 11, Color.rgb(242, 207, 215));
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

        tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);
        tabs.setGravity(Gravity.CENTER);
        tabs.setPadding(Ui.dp(this, 6), Ui.dp(this, 7), Ui.dp(this, 6), Ui.dp(this, 7));
        tabs.setBackgroundColor(Ui.SURFACE);
        tabs.setElevation(Ui.dp(this, 12));
        root.addView(tabs, new LinearLayout.LayoutParams(-1, Ui.dp(this, 68)));
        setContentView(root);
    }

    private void select(Tab tab) {
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
        Button button = new Button(this);
        boolean active = current == tab;
        button.setAllCaps(false);
        button.setText(label);
        button.setTextSize(11);
        button.setTypeface(active ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
        button.setTextColor(active ? Color.WHITE : Ui.MUTED);
        button.setPadding(0, 0, 0, 0);
        button.setBackground(Ui.navBackground(this, active));
        button.setOnClickListener(view -> select(tab));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1);
        params.setMargins(Ui.dp(this, 2), 0, Ui.dp(this, 2), 0);
        tabs.addView(button, params);
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
                        fromCache ? "Hızlı önbellek" : "GitHub güncel", fromCache ? Ui.GOLD : Ui.GREEN));
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
                    }
                }
                content.addView(hero);
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
                photosOnly ? Ui.GOLD : Ui.RED);
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
                        fromCache ? "Anında önbellek" : "Canlı arşiv", fromCache ? Ui.GOLD : Ui.GREEN));
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
                            photosOnly ? Ui.GOLD : Ui.RED));
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
                "Skor manifestindeki sezon dizini tek kaynak olarak kullanılır.", Ui.GOLD);
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
                    card.addView(Ui.eyebrow(MainActivity.this, "Sezon", Ui.GOLD));
                    TextView heading = strong(season.optString("name", season.optString("id")));
                    heading.setPadding(0, Ui.dp(MainActivity.this, 5), 0, 0);
                    card.addView(heading);
                    card.addView(Ui.text(MainActivity.this,
                            season.optInt("matchCount", 0) + " maç kaydı", 13, Ui.MUTED));
                    content.addView(card);
                }
            }
            @Override public void onError(String message) { showError(Tab.SEASONS, message); }
        });
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
