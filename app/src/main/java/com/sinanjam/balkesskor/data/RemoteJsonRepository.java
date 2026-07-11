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
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;

public final class RemoteJsonRepository {
    public interface Callback {
        void onSuccess(Object json, boolean fromCache);
        void onError(String message);
    }

    private static final class Pending {
        final Callback callback;
        final boolean hasCachedValue;

        Pending(Callback callback, boolean hasCachedValue) {
            this.callback = callback;
            this.hasCachedValue = hasCachedValue;
        }
    }

    private final File cacheDir;
    private final ExecutorService executor = Executors.newFixedThreadPool(4);
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Map<String, Object> memoryCache = new ConcurrentHashMap<>();
    private final Map<String, String> rawCache = new ConcurrentHashMap<>();
    private final Map<String, ArrayList<Pending>> inFlight = new HashMap<>();
    private volatile boolean closed;

    public RemoteJsonRepository(Context context) {
        cacheDir = new File(context.getFilesDir(), "json-cache");
        if (!cacheDir.exists()) cacheDir.mkdirs();
    }

    public void prefetch(String url) {
        get(url, new Callback() {
            @Override public void onSuccess(Object json, boolean fromCache) { }
            @Override public void onError(String message) { }
        });
    }

    public void get(String url, Callback callback) {
        if (closed) return;
        execute(() -> {
            if (closed) return;
            Object cached = memoryCache.get(url);
            if (cached == null) {
                try {
                    String cachedBody = read(cacheFile(url));
                    cached = parse(cachedBody);
                    memoryCache.put(url, cached);
                    rawCache.put(url, cachedBody);
                } catch (Exception ignored) { }
            }

            final Object immediate = cached;
            final boolean hasCachedValue = immediate != null;
            if (hasCachedValue) {
                post(() -> callback.onSuccess(immediate, true));
            }
            enqueueRefresh(url, callback, hasCachedValue);
        });
    }

    public void close() {
        closed = true;
        executor.shutdownNow();
        main.removeCallbacksAndMessages(null);
        synchronized (inFlight) {
            inFlight.clear();
        }
    }

    private void enqueueRefresh(String url, Callback callback, boolean hasCachedValue) {
        if (closed) return;
        boolean startRequest = false;
        synchronized (inFlight) {
            ArrayList<Pending> listeners = inFlight.get(url);
            if (listeners == null) {
                listeners = new ArrayList<>();
                inFlight.put(url, listeners);
                startRequest = true;
            }
            listeners.add(new Pending(callback, hasCachedValue));
        }
        if (startRequest) execute(() -> refresh(url));
    }

    private void refresh(String url) {
        try {
            String body = fetch(url);
            Object parsed = parse(body);
            boolean unchanged = body.equals(rawCache.get(url));
            memoryCache.put(url, parsed);
            rawCache.put(url, body);
            if (!unchanged) write(cacheFile(url), body);
            finish(url, parsed, null, unchanged);
        } catch (Exception error) {
            finish(url, null,
                    "İçerik alınamadı. İnternet bağlantını kontrol edip tekrar dene.", false);
        }
    }

    private void finish(String url, Object value, String error, boolean unchanged) {
        ArrayList<Pending> listeners;
        synchronized (inFlight) {
            listeners = inFlight.remove(url);
        }
        if (listeners == null || closed) return;
        for (Pending pending : listeners) {
            if (value != null && (!unchanged || !pending.hasCachedValue)) {
                post(() -> pending.callback.onSuccess(value, false));
            } else if (!pending.hasCachedValue) {
                post(() -> pending.callback.onError(error));
            }
        }
    }

    private void execute(Runnable action) {
        if (closed) return;
        try {
            executor.execute(action);
        } catch (RejectedExecutionException ignored) { }
    }

    private void post(Runnable action) {
        if (!closed) main.post(() -> {
            if (!closed) action.run();
        });
    }

    private String fetch(String address) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection();
        try {
            connection.setConnectTimeout(7_000);
            connection.setReadTimeout(15_000);
            connection.setUseCaches(true);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("Connection", "keep-alive");
            connection.setRequestProperty("User-Agent", "Balkes-Android/1.5");
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

    private File cacheFile(String url) {
        return new File(cacheDir, key(url) + ".json");
    }

    private String read(File file) throws Exception {
        if (!file.isFile()) throw new IllegalStateException("Önbellek yok");
        try (InputStream input = new FileInputStream(file)) {
            return read(input);
        }
    }

    private String read(InputStream input) throws Exception {
        try (InputStream in = input; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[32_768];
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
