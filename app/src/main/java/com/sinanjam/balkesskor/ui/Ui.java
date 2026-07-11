package com.sinanjam.balkesskor.ui;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

public final class Ui {
    public static final int BACKGROUND = Color.rgb(14, 15, 19);
    public static final int CARD = Color.rgb(29, 31, 38);
    public static final int TEXT = Color.WHITE;
    public static final int MUTED = Color.rgb(185, 188, 198);
    public static final int RED = Color.rgb(178, 11, 36);

    private Ui() {}

    public static TextView title(Context context, String value) {
        TextView view = text(context, value, 25, TEXT);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        return view;
    }

    public static TextView text(Context context, String value, int sp, int color) {
        TextView view = new TextView(context);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color);
        view.setLineSpacing(0, 1.08f);
        return view;
    }

    public static LinearLayout card(Context context) {
        LinearLayout card = new LinearLayout(context);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(context, 16), dp(context, 14), dp(context, 16), dp(context, 14));
        GradientDrawable background = new GradientDrawable();
        background.setColor(CARD);
        background.setCornerRadius(dp(context, 14));
        background.setStroke(dp(context, 1), Color.rgb(58, 61, 72));
        card.setBackground(background);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(0, dp(context, 10), 0, 0);
        card.setLayoutParams(params);
        return card;
    }

    public static View loading(Context context) {
        LinearLayout box = card(context);
        box.setGravity(Gravity.CENTER);
        ProgressBar progress = new ProgressBar(context);
        box.addView(progress, new LinearLayout.LayoutParams(dp(context, 42), dp(context, 42)));
        TextView label = text(context, "Veri yükleniyor…", 14, MUTED);
        label.setGravity(Gravity.CENTER);
        box.addView(label);
        return box;
    }

    public static View message(Context context, String heading, String body) {
        LinearLayout card = card(context);
        TextView title = text(context, heading, 18, TEXT);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        card.addView(title);
        TextView detail = text(context, body, 14, MUTED);
        detail.setPadding(0, dp(context, 6), 0, 0);
        card.addView(detail);
        return card;
    }

    public static int dp(Context context, int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }
}
