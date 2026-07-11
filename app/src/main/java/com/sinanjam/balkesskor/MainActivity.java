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
    private Tab current = Tab.SCORE;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        repository = new RemoteJsonRepository(this);
        buildShell();
        select(Tab.SCORE);
    }

    @Override
    protected void onDestroy() {
        repository.close();
        super.onDestroy();
    }

    private void buildShell() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Ui.BACKGROUND);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setPadding(Ui.dp(this, 18), Ui.dp(this, 15), Ui.dp(this, 18), Ui.dp(this, 13));
        header.setBackgroundColor(Color.rgb(124, 5, 26));
        TextView name = Ui.text(this, "BALKES", 27, Color.WHITE);
        name.setTypeface(Typeface.DEFAULT_BOLD);
        header.addView(name);
        header.addView(Ui.text(this, "Skor • Arşiv • Fotoğraf • Haber", 12, Color.rgb(242, 215, 220)));
        root.addView(header, new LinearLayout.LayoutParams(-1, -2));

        ScrollView scroll = new ScrollView(this);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(Ui.dp(this, 14), Ui.dp(this, 14), Ui.dp(this, 14), Ui.dp(this, 28));
        scroll.addView(content);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);
        tabs.setPadding(Ui.dp(this, 4), Ui.dp(this, 5), Ui.dp(this, 4), Ui.dp(this, 5));
        tabs.setBackgroundColor(Color.rgb(20, 21, 27));
        root.addView(tabs, new LinearLayout.LayoutParams(-1, Ui.dp(this, 64)));
        setContentView(root);
    }

    private void select(Tab tab) {
        current = tab;
        renderTabs();
        if (tab == Tab.SCORE) renderScore();
        else if (tab == Tab.ARCHIVE) renderArchive(false);
        else if (tab == Tab.PHOTOS) renderArchive(true);
        else if (tab == Tab.NEWS) renderNews();
        else renderSeasons();
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
        button.setAllCaps(false);
        button.setText(label);
        button.setTextSize(11);
        button.setTextColor(current == tab ? Color.WHITE : Ui.MUTED);
        button.setBackgroundColor(current == tab ? Ui.RED : Color.TRANSPARENT);
        button.setOnClickListener(view -> select(tab));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1);
        params.setMargins(Ui.dp(this, 2), 0, Ui.dp(this, 2), 0);
        tabs.addView(button, params);
    }

    private void start(String title, String subtitle) {
        content.removeAllViews();
        content.addView(Ui.title(this, title));
        TextView sub = Ui.text(this, subtitle, 13, Ui.MUTED);
        sub.setPadding(0, Ui.dp(this, 4), 0, Ui.dp(this, 4));
        content.addView(sub);
        content.addView(Ui.loading(this));
    }

    private void renderScore() {
        start("Balkes Skor", "Güncel sezon özeti GitHub veri deposundan gelir.");
        repository.get(DataEndpoints.scoreManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (current != Tab.SCORE || !(json instanceof JSONObject)) return;
                JSONObject root = (JSONObject) json;
                JSONArray seasons = root.optJSONArray("availableSeasons");
                content.removeViews(2, content.getChildCount() - 2);
                LinearLayout card = Ui.card(MainActivity.this);
                card.addView(strong("Balıkesirspor maç merkezi"));
                card.addView(Ui.text(MainActivity.this,
                        seasons == null ? "Sezon bilgisi bulunamadı" : seasons.length() + " sezon erişilebilir",
                        17, Ui.TEXT));
                card.addView(Ui.text(MainActivity.this,
                        fromCache ? "Önbellekteki son veri gösteriliyor" : "GitHub verisi güncel",
                        12, fromCache ? Color.rgb(235, 181, 80) : Color.rgb(111, 210, 144)));
                if (seasons != null && seasons.length() > 0) {
                    JSONObject season = seasons.optJSONObject(0);
                    if (season != null) card.addView(Ui.text(MainActivity.this,
                            "Aktif sezon: " + season.optString("name", season.optString("id")), 15, Ui.MUTED));
                }
                content.addView(card);
            }
            @Override public void onError(String message) { showError(Tab.SCORE, message); }
        });
    }

    private void renderArchive(final boolean photosOnly) {
        final Tab expected = photosOnly ? Tab.PHOTOS : Tab.ARCHIVE;
        start(photosOnly ? "Fotoğraflar" : "Balkes Arşivi",
                photosOnly ? "Görseller APK içinde değil; manifestteki adreslerden yüklenir."
                        : "Arşiv yazıları ve sezon hikâyeleri uzaktaki JSON manifestinden gelir.");
        repository.get(DataEndpoints.archiveManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (current != expected || !(json instanceof JSONObject)) return;
                JSONArray items = ((JSONObject) json).optJSONArray("items");
                content.removeViews(2, content.getChildCount() - 2);
                if (items == null) { content.addView(Ui.message(MainActivity.this, "Boş manifest", "items dizisi bulunamadı.")); return; }
                int shown = 0;
                for (int i = 0; i < items.length() && shown < 12; i++) {
                    JSONObject item = items.optJSONObject(i);
                    if (item == null) continue;
                    JSONArray photos = item.optJSONArray("photos");
                    if (photosOnly && (photos == null || photos.length() == 0)) continue;
                    LinearLayout card = Ui.card(MainActivity.this);
                    card.addView(strong(item.optString("title", "İsimsiz kayıt")));
                    if (photosOnly) {
                        JSONObject first = photos.optJSONObject(0);
                        card.addView(Ui.text(MainActivity.this,
                                photos.length() + " fotoğraf" + (first == null ? "" : " • " + first.optString("caption", "")),
                                13, Ui.MUTED));
                    } else {
                        card.addView(Ui.text(MainActivity.this, item.optString("summary", ""), 13, Ui.MUTED));
                    }
                    content.addView(card);
                    shown++;
                }
                content.addView(Ui.message(MainActivity.this, fromCache ? "Önbellek" : "Canlı veri",
                        items.length() + " kayıt bulundu; ilk " + shown + " kayıt gösteriliyor."));
            }
            @Override public void onError(String message) { showError(expected, message); }
        });
    }

    private void renderNews() {
        start("Haber ve duyurular", "Yeni veri deposundaki news/index.json sözleşmesini kullanır.");
        repository.get(DataEndpoints.newsManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (current != Tab.NEWS) return;
                JSONArray items = json instanceof JSONArray ? (JSONArray) json : ((JSONObject) json).optJSONArray("items");
                content.removeViews(2, content.getChildCount() - 2);
                if (items == null || items.length() == 0) {
                    content.addView(Ui.message(MainActivity.this, "Henüz duyuru yok", "Manifest geçerli fakat içerik boş."));
                    return;
                }
                for (int i = 0; i < items.length() && i < 15; i++) {
                    JSONObject item = items.optJSONObject(i);
                    if (item == null) continue;
                    LinearLayout card = Ui.card(MainActivity.this);
                    card.addView(strong(item.optString("title", "Duyuru")));
                    card.addView(Ui.text(MainActivity.this, item.optString("summary", ""), 13, Ui.MUTED));
                    content.addView(card);
                }
            }
            @Override public void onError(String message) {
                if (current != Tab.NEWS) return;
                content.removeViews(2, content.getChildCount() - 2);
                content.addView(Ui.message(MainActivity.this, "Veri deposu bekleniyor",
                        "news/index.json henüz yayımlanmadı. URL, CONTENT_BASE_URL ile değiştirilebilir."));
            }
        });
    }

    private void renderSeasons() {
        start("Geçmiş sezonlar", "Skor manifestindeki sezon dizini tek kaynak olarak kullanılır.");
        repository.get(DataEndpoints.scoreManifest(), new RemoteJsonRepository.Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) {
                if (current != Tab.SEASONS || !(json instanceof JSONObject)) return;
                JSONArray seasons = ((JSONObject) json).optJSONArray("availableSeasons");
                content.removeViews(2, content.getChildCount() - 2);
                if (seasons == null) { content.addView(Ui.message(MainActivity.this, "Sezon yok", "availableSeasons bulunamadı.")); return; }
                for (int i = 0; i < seasons.length(); i++) {
                    JSONObject season = seasons.optJSONObject(i);
                    if (season == null) continue;
                    LinearLayout card = Ui.card(MainActivity.this);
                    card.addView(strong(season.optString("name", season.optString("id"))));
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
        if (current != expected) return;
        content.removeViews(2, content.getChildCount() - 2);
        content.addView(Ui.message(this, "Bağlantı kurulamadı", message));
    }
}
