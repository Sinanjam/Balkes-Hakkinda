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

import java.util.Locale;

public final class Ui {
    private static final Locale TURKISH = new Locale("tr", "TR");
    public static final int BACKGROUND = Color.rgb(2, 4, 8);
    public static final int SURFACE = Color.rgb(4, 7, 12);
    public static final int CARD = Color.rgb(8, 12, 19);
    public static final int TEXT = Color.rgb(250, 250, 252);
    public static final int MUTED = Color.rgb(174, 180, 195);
    public static final int RED = Color.rgb(255, 18, 76);
    public static final int RED_DARK = Color.rgb(105, 0, 34);
    public static final int CYAN = Color.rgb(0, 238, 255);
    public static final int GREEN = Color.rgb(99, 211, 145);
    public static final int AMBER = Color.rgb(255, 196, 87);

    private Ui() {}

    public static TextView title(Context context, String value) {
        TextView view = text(context, value, 28, TEXT);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setLetterSpacing(-0.015f);
        return view;
    }

    public static TextView eyebrow(Context context, String value, int color) {
        TextView view = text(context, value.toUpperCase(TURKISH), 11, color);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setLetterSpacing(0.12f);
        return view;
    }

    public static TextView text(Context context, String value, int sp, int color) {
        TextView view = new TextView(context);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color);
        view.setLineSpacing(0, 1.1f);
        return view;
    }

    public static LinearLayout card(Context context) {
        LinearLayout card = new LinearLayout(context);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(context, 18), dp(context, 16), dp(context, 18), dp(context, 16));
        card.setBackground(roundedGradient(context,
                new int[]{Color.rgb(12, 17, 26), Color.rgb(6, 9, 15)},
                Color.argb(58, 255, 255, 255), 18, 1));
        card.setElevation(dp(context, 3));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(0, dp(context, 11), 0, 0);
        card.setLayoutParams(params);
        return card;
    }

    public static LinearLayout sportsCard(Context context, int accent) {
        LinearLayout card = card(context);
        card.setBackground(roundedGradient(context,
                new int[]{Color.rgb(12, 17, 27), Color.rgb(6, 10, 16)},
                Color.argb(105, Color.red(accent), Color.green(accent), Color.blue(accent)),
                18, 1));
        card.setElevation(dp(context, 3));
        return card;
    }

    public static LinearLayout metric(Context context, String value, String label, int accent) {
        LinearLayout box = new LinearLayout(context);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setPadding(dp(context, 7), dp(context, 10), dp(context, 7), dp(context, 9));
        box.setBackground(rounded(context,
                Color.argb(22, Color.red(accent), Color.green(accent), Color.blue(accent)),
                Color.argb(68, Color.red(accent), Color.green(accent), Color.blue(accent)),
                12, 1));

        TextView number = text(context, value, 18, TEXT);
        number.setTypeface(Typeface.DEFAULT_BOLD);
        number.setGravity(Gravity.CENTER);
        box.addView(number);

        TextView caption = eyebrow(context, label, accent);
        caption.setTextSize(8);
        caption.setGravity(Gravity.CENTER);
        caption.setPadding(0, dp(context, 3), 0, 0);
        box.addView(caption);
        return box;
    }

    public static View divider(Context context) {
        View divider = new View(context);
        divider.setBackgroundColor(Color.argb(40, 255, 255, 255));
        divider.setLayoutParams(new LinearLayout.LayoutParams(-1, dp(context, 1)));
        return divider;
    }

    public static LinearLayout heroCard(Context context) {
        LinearLayout card = card(context);
        card.setPadding(dp(context, 20), dp(context, 20), dp(context, 20), dp(context, 20));
        card.setBackground(roundedGradient(context,
                new int[]{Color.rgb(70, 0, 25), Color.rgb(12, 11, 22), Color.rgb(4, 10, 16)},
                CYAN, 16, 1));
        card.setElevation(dp(context, 8));
        return card;
    }

    public static TextView chip(Context context, String value, int color) {
        TextView chip = eyebrow(context, value, color);
        chip.setGravity(Gravity.CENTER);
        chip.setPadding(dp(context, 11), dp(context, 6), dp(context, 11), dp(context, 6));
        chip.setBackground(rounded(context, Color.argb(38, Color.red(color), Color.green(color), Color.blue(color)),
                Color.argb(130, Color.red(color), Color.green(color), Color.blue(color)), 99, 1));
        return chip;
    }

    public static View loading(Context context) {
        LinearLayout box = card(context);
        box.setGravity(Gravity.CENTER);
        box.setPadding(dp(context, 18), dp(context, 24), dp(context, 18), dp(context, 24));
        ProgressBar progress = new ProgressBar(context);
        progress.getIndeterminateDrawable().setTint(RED);
        box.addView(progress, new LinearLayout.LayoutParams(dp(context, 38), dp(context, 38)));
        TextView label = text(context, "İçerikler hazırlanıyor…", 13, MUTED);
        label.setGravity(Gravity.CENTER);
        label.setPadding(0, dp(context, 10), 0, 0);
        box.addView(label);
        return box;
    }

    public static View message(Context context, String heading, String body) {
        LinearLayout card = card(context);
        TextView title = text(context, heading, 18, TEXT);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        card.addView(title);
        TextView detail = text(context, body, 14, MUTED);
        detail.setPadding(0, dp(context, 7), 0, 0);
        card.addView(detail);
        return card;
    }

    public static GradientDrawable appBackground() {
        return roundedGradient(null, new int[]{
                Color.rgb(26, 0, 12),
                Color.rgb(3, 11, 17),
                BACKGROUND
        }, Color.TRANSPARENT, 0, 0);
    }

    public static GradientDrawable headerBackground() {
        return roundedGradient(null, new int[]{
                Color.rgb(8, 12, 20),
                Color.rgb(88, 0, 30),
                Color.rgb(2, 17, 23)
        }, Color.TRANSPARENT, 0, 0);
    }

    public static GradientDrawable choiceBackground(Context context, int accent) {
        return roundedGradient(context, new int[]{
                Color.rgb(9, 14, 22),
                Color.rgb(3, 7, 12)
        }, Color.argb(175, Color.red(accent), Color.green(accent), Color.blue(accent)), 22, 1);
    }

    public static GradientDrawable badgeBackground(Context context) {
        return roundedGradient(context, new int[]{RED, RED_DARK, Color.rgb(0, 80, 90)}, CYAN, 18, 1);
    }

    public static GradientDrawable inputBackground(Context context) {
        return roundedGradient(context,
                new int[]{Color.rgb(6, 11, 18), Color.rgb(3, 7, 12)},
                Color.argb(190, 0, 238, 255), 12, 1);
    }

    public static GradientDrawable neonLine() {
        return new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT,
                new int[]{Color.TRANSPARENT, RED, CYAN, Color.TRANSPARENT});
    }

    public static GradientDrawable rounded(Context context, int fill, int stroke, int radiusDp, int strokeDp) {
        GradientDrawable result = new GradientDrawable();
        result.setColor(fill);
        result.setCornerRadius(context == null ? radiusDp : dp(context, radiusDp));
        if (strokeDp > 0) result.setStroke(context == null ? strokeDp : dp(context, strokeDp), stroke);
        return result;
    }

    private static GradientDrawable roundedGradient(Context context, int[] colors, int stroke, int radiusDp, int strokeDp) {
        GradientDrawable result = new GradientDrawable(GradientDrawable.Orientation.TL_BR, colors);
        result.setCornerRadius(context == null ? radiusDp : dp(context, radiusDp));
        if (strokeDp > 0) result.setStroke(context == null ? strokeDp : dp(context, strokeDp), stroke);
        return result;
    }

    public static int dp(Context context, int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }
}
