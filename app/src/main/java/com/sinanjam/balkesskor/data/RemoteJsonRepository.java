package com.sinanjam.balkesskor.data;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class RemoteJsonRepository {
    public interface Callback {
        void onSuccess(Object json, boolean fromCache);
        void onError(String message);
    }

    private final File cacheDir;
    private final ExecutorService executor = Executors.newFixedThreadPool(3);
    private final Handler main = new Handler(Looper.getMainLooper());

    public RemoteJsonRepository(Context context) {
        cacheDir = new File(context.getFilesDir(), "json-cache");
        if (!cacheDir.exists()) cacheDir.mkdirs();
    }

    public void get(String url, Callback callback) {
        executor.execute(() -> {
            File cache = new File(cacheDir, key(url) + ".json");
            try {
                String body = fetch(url);
                Object parsed = parse(body);
                write(cache, body);
                main.post(() -> callback.onSuccess(parsed, false));
            } catch (Exception networkError) {
                try {
                    Object parsed = parse(read(cache));
                    main.post(() -> callback.onSuccess(parsed, true));
                } catch (Exception cacheError) {
                    main.post(() -> callback.onError("Veri alınamadı. İnternet bağlantısını kontrol edin."));
                }
            }
        });
    }

    public void close() {
        executor.shutdownNow();
    }

    private String fetch(String address) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection();
        try {
            connection.setConnectTimeout(10_000);
            connection.setReadTimeout(20_000);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("User-Agent", "Balkes-Android/1.1");
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new IllegalStateException("HTTP " + status);
            return read(connection.getInputStream());
        } finally {
            connection.disconnect();
        }
    }

    private Object parse(String body) throws Exception {
        String value = body == null ? "" : body.trim();
        if (value.startsWith("[")) return new JSONArray(value);
        if (value.startsWith("{")) return new JSONObject(value);
        throw new IllegalArgumentException("JSON bekleniyordu");
    }

    private String read(File file) throws Exception {
        if (!file.isFile()) throw new IllegalStateException("Önbellek yok");
        try (InputStream input = new FileInputStream(file)) {
            return read(input);
        }
    }

    private String read(InputStream input) throws Exception {
        try (InputStream in = input; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) >= 0) out.write(buffer, 0, count);
            return out.toString(StandardCharsets.UTF_8.name());
        }
    }

    private void write(File file, String body) throws Exception {
        File temporary = new File(file.getParentFile(), file.getName() + ".tmp");
        try (FileOutputStream output = new FileOutputStream(temporary)) {
            output.write(body.getBytes(StandardCharsets.UTF_8));
        }
        if (!temporary.renameTo(file)) {
            try (FileOutputStream output = new FileOutputStream(file)) {
                output.write(body.getBytes(StandardCharsets.UTF_8));
            }
            temporary.delete();
        }
    }

    private String key(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder();
            for (byte item : digest) result.append(String.format("%02x", item));
            return result.toString();
        } catch (Exception ignored) {
            return String.valueOf(value.hashCode());
        }
    }
}
