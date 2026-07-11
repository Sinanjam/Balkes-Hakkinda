package com.sinanjam.balkesskor.ui;

import android.app.Activity;
import android.graphics.Color;
import android.os.Build;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowManager;

public final class EdgeToEdge {
    private EdgeToEdge() {}

    public static void configure(Activity activity) {
        Window window = activity.getWindow();
        window.setStatusBarColor(Color.TRANSPARENT);
        window.setNavigationBarColor(Color.TRANSPARENT);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Api30.configure(window);
        } else {
            window.getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            Api28.allowDisplayCutout(window);
        }
    }

    public static void applyInsets(View view, int left, int top, int right, int bottom) {
        view.setOnApplyWindowInsetsListener((target, windowInsets) -> {
            int[] systemInsets = Build.VERSION.SDK_INT >= Build.VERSION_CODES.R
                    ? Api30.readInsets(windowInsets)
                    : readLegacyInsets(windowInsets);
            target.setPadding(
                    left + systemInsets[0],
                    top + systemInsets[1],
                    right + systemInsets[2],
                    bottom + systemInsets[3]);
            return windowInsets;
        });
        view.requestApplyInsets();
    }

    @SuppressWarnings("deprecation")
    private static int[] readLegacyInsets(WindowInsets insets) {
        return new int[]{
                insets.getSystemWindowInsetLeft(),
                insets.getSystemWindowInsetTop(),
                insets.getSystemWindowInsetRight(),
                insets.getSystemWindowInsetBottom()
        };
    }

    private static final class Api28 {
        private Api28() {}

        static void allowDisplayCutout(Window window) {
            WindowManager.LayoutParams attributes = window.getAttributes();
            attributes.layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            window.setAttributes(attributes);
        }
    }

    private static final class Api30 {
        private Api30() {}

        static void configure(Window window) {
            window.setDecorFitsSystemWindows(false);
            android.view.WindowInsetsController controller = window.getInsetsController();
            if (controller != null) {
                controller.setSystemBarsAppearance(0,
                        android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                                | android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
            }
        }

        static int[] readInsets(WindowInsets windowInsets) {
            android.graphics.Insets insets = windowInsets.getInsets(
                    WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            return new int[]{insets.left, insets.top, insets.right, insets.bottom};
        }
    }
}
