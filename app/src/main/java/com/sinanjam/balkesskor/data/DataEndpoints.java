package com.sinanjam.balkesskor.data;

import com.sinanjam.balkesskor.BuildConfig;

public final class DataEndpoints {
    private DataEndpoints() {}

    public static String scoreManifest() {
        return slash(BuildConfig.SCORE_BASE_URL) + "manifest.json";
    }

    public static String archiveManifest() {
        return BuildConfig.ARCHIVE_MANIFEST_URL;
    }

    public static String newsManifest() {
        return slash(BuildConfig.CONTENT_BASE_URL) + "news/index.json";
    }

    public static String archiveMedia(String relativePath) {
        return slash(BuildConfig.ARCHIVE_MEDIA_BASE_URL) + trim(relativePath);
    }

    private static String slash(String value) {
        return value.endsWith("/") ? value : value + "/";
    }

    private static String trim(String value) {
        if (value == null) return "";
        while (value.startsWith("/")) value = value.substring(1);
        return value;
    }
}
