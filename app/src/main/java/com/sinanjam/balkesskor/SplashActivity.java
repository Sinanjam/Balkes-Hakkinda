package com.sinanjam.balkesskor;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.sinanjam.balkesskor.ui.EdgeToEdge;
import com.sinanjam.balkesskor.ui.Ui;

public final class SplashActivity extends Activity {
    private static final long SPLASH_TIME_MS = 900L;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable openApp = () -> {
        startActivity(new Intent(SplashActivity.this, MainActivity.class));
        overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out);
        finish();
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        EdgeToEdge.configure(this);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackground(Ui.appBackground());

        TextView badge = Ui.text(this, "B", 50, Color.WHITE);
        badge.setTypeface(Typeface.DEFAULT_BOLD);
        badge.setGravity(Gravity.CENTER);
        badge.setBackground(Ui.badgeBackground(this));
        badge.setElevation(Ui.dp(this, 14));
        root.addView(badge, new LinearLayout.LayoutParams(Ui.dp(this, 96), Ui.dp(this, 96)));

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

        TextView loading = Ui.text(this, "BALIKESİRSPOR DİJİTAL MERKEZİ", 10, Ui.MUTED);
        loading.setLetterSpacing(0.11f);
        loading.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams loadingParams = new LinearLayout.LayoutParams(-1, -2);
        loadingParams.setMargins(0, Ui.dp(this, 18), 0, 0);
        root.addView(loading, loadingParams);

        setContentView(root);
        EdgeToEdge.applyInsets(root, Ui.dp(this, 24), Ui.dp(this, 28),
                Ui.dp(this, 24), Ui.dp(this, 28));
        handler.postDelayed(openApp, SPLASH_TIME_MS);
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(openApp);
        super.onDestroy();
    }
}
