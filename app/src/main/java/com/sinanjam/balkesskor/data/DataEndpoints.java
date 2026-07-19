package com.sinanjam.balkesskor.data;

import com.sinanjam.balkesskor.BuildConfig;

import org.json.JSONObject;

import java.net.URI;

public final class DataEndpoints {
    private static volatile String scoreDataBase = slash(BuildConfig.SCORE_BASE_URL);
    private static volatile String scoreDataVersion = "";
    private static volatile String scoreSourceLabel = "GitHub Raw";

    private DataEndpoints() {}

    public static String scoreManifest() {
        return slash(BuildConfig.SCORE_BASE_URL) + "manifest.json";
    }

    public static String scoreMirrorManifest() {
        return slash(BuildConfig.SCORE_MIRROR_BASE_URL) + "manifest.json";
    }

    public static synchronized void configureScoreManifest(JSONObject manifest, String manifestUrl) {
        String manifestBase = directory(manifestUrl);
        String advertisedBase = manifest == null ? "" : manifest.optString("dataBaseUrl", "");
        boolean mirrorSource = manifestUrl != null && manifestUrl.contains("cdn.jsdelivr.net");
        if (mirrorSource && isSafeHttpsBase(manifestBase)) scoreDataBase = slash(manifestBase);
        else if (isSafeHttpsBase(advertisedBase)) scoreDataBase = slash(advertisedBase);
        else if (isSafeHttpsBase(manifestBase)) scoreDataBase = slash(manifestBase);
        else scoreDataBase = slash(BuildConfig.SCORE_BASE_URL);

        scoreSourceLabel = mirrorSource
                ? "GitHub CDN" : "GitHub Raw";

        Object version = manifest == null ? null : manifest.opt("appDataVersion");
        if (version == null || version == JSONObject.NULL) {
            version = manifest == null ? null : manifest.opt("dataVersion");
        }
        scoreDataVersion = safeVersion(version);
    }

    public static String scoreFile(String relativePath) {
        String clean = dataRelativePath(relativePath);
        String address = isSafeHttpsUrl(clean) ? clean : slash(scoreDataBase) + clean;
        return versioned(address);
    }

    public static String scoreMirrorFile(String relativePath) {
        String clean = dataRelativePath(relativePath);
        String alternateBase = scoreDataBase.contains("cdn.jsdelivr.net")
                ? BuildConfig.SCORE_BASE_URL : BuildConfig.SCORE_MIRROR_BASE_URL;
        String address = isSafeHttpsUrl(clean)
                ? clean : slash(alternateBase) + clean;
        return versioned(address);
    }

    public static String scoreDataVersion() {
        return scoreDataVersion;
    }

    public static String scoreSourceLabel() {
        return scoreSourceLabel;
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

    private static String dataRelativePath(String value) {
        String clean = trim(value);
        if (!isSafeHttpsUrl(clean)) return clean;
        try {
            String path = new URI(clean).getPath();
            int data = path.indexOf("/data/");
            if (data >= 0) return path.substring(data + 6);
        } catch (Exception ignored) { }
        return clean;
    }

    private static String versioned(String address) {
        String version = scoreDataVersion;
        if (version.length() == 0) return address;
        return address + (address.contains("?") ? "&" : "?") + "v=" + version;
    }

    private static String directory(String address) {
        if (address == null) return "";
        int query = address.indexOf('?');
        String clean = query >= 0 ? address.substring(0, query) : address;
        int slash = clean.lastIndexOf('/');
        return slash >= 0 ? clean.substring(0, slash + 1) : "";
    }

    private static boolean isSafeHttpsBase(String value) {
        return isSafeHttpsUrl(value) && value.indexOf('?') < 0 && value.indexOf('#') < 0;
    }

    private static boolean isSafeHttpsUrl(String value) {
        if (value == null || value.length() == 0) return false;
        try {
            URI uri = new URI(value);
            return "https".equalsIgnoreCase(uri.getScheme())
                    && uri.getHost() != null
                    && uri.getHost().length() > 0;
        } catch (Exception ignored) {
            return false;
        }
    }

    private static String safeVersion(Object value) {
        if (value == null) return "";
        return String.valueOf(value).replaceAll("[^A-Za-z0-9._-]", "");
    }
}
