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
    public static final int BACKGROUND = Color.rgb(8, 10, 15);
    public static final int SURFACE = Color.rgb(19, 22, 30);
    public static final int CARD = Color.rgb(27, 31, 41);
    public static final int TEXT = Color.rgb(250, 250, 252);
    public static final int MUTED = Color.rgb(174, 180, 195);
    public static final int RED = Color.rgb(224, 0, 52);
    public static final int RED_DARK = Color.rgb(118, 5, 31);
    public static final int GOLD = Color.rgb(217, 174, 83);
    public static final int GREEN = Color.rgb(99, 211, 145);

    private Ui() {}

    public static TextView title(Context context, String value) {
        TextView view = text(context, value, 28, TEXT);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setLetterSpacing(-0.015f);
        return view;
    }

    public static TextView eyebrow(Context context, String value, int color) {
        TextView view = text(context, value.toUpperCase(), 11, color);
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
                new int[]{Color.rgb(31, 35, 46), Color.rgb(22, 25, 34)},
                Color.rgb(54, 60, 75), 18, 1));
        card.setElevation(dp(context, 4));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(0, dp(context, 11), 0, 0);
        card.setLayoutParams(params);
        return card;
    }

    public static LinearLayout heroCard(Context context) {
        LinearLayout card = card(context);
        card.setPadding(dp(context, 20), dp(context, 20), dp(context, 20), dp(context, 20));
        card.setBackground(roundedGradient(context,
                new int[]{Color.rgb(91, 4, 27), Color.rgb(35, 17, 29), Color.rgb(22, 25, 34)},
                Color.rgb(153, 20, 53), 20, 1));
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
        TextView label = text(context, "GitHub verisi hazırlanıyor…", 13, MUTED);
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
                Color.rgb(44, 2, 14),
                Color.rgb(17, 11, 19),
                BACKGROUND
        }, Color.TRANSPARENT, 0, 0);
    }

    public static GradientDrawable headerBackground() {
        return roundedGradient(null, new int[]{
                Color.rgb(46, 3, 16),
                Color.rgb(126, 5, 34),
                Color.rgb(50, 5, 20)
        }, Color.TRANSPARENT, 0, 0);
    }

    public static GradientDrawable choiceBackground(Context context, int accent) {
        return roundedGradient(context, new int[]{
                Color.rgb(31, 34, 45),
                Color.rgb(20, 23, 31)
        }, Color.argb(175, Color.red(accent), Color.green(accent), Color.blue(accent)), 22, 1);
    }

    public static GradientDrawable navBackground(Context context, boolean active) {
        if (active) {
            return roundedGradient(context, new int[]{RED_DARK, RED}, Color.rgb(242, 66, 104), 14, 1);
        }
        return rounded(context, Color.TRANSPARENT, Color.TRANSPARENT, 14, 0);
    }

    public static GradientDrawable badgeBackground(Context context) {
        return roundedGradient(context, new int[]{RED, RED_DARK}, Color.rgb(255, 91, 126), 22, 1);
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
