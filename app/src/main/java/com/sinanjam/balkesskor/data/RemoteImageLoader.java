package com.sinanjam.balkesskor.data;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Handler;
import android.os.Looper;
import android.widget.ImageView;

import com.sinanjam.balkesskor.R;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Comparator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;

public final class RemoteImageLoader {
    private static final int MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024;
    private static final int MAX_DECODE_EDGE = 1_200;
    private static final long MAX_CACHE_BYTES = 80L * 1024L * 1024L;

    private final File cacheDir;
    private final ExecutorService executor = Executors.newFixedThreadPool(3);
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile boolean closed;

    public RemoteImageLoader(Context context) {
        cacheDir = new File(context.getFilesDir(), "image-cache");
        if (!cacheDir.exists()) cacheDir.mkdirs();
    }

    public void load(String address, ImageView target) {
        if (closed || address == null || address.length() == 0) return;
        target.setTag(address);
        target.setAlpha(0.35f);
        target.setImageResource(R.drawable.balkes_logo);

        execute(() -> {
            try {
                File file = new File(cacheDir, key(address) + ".img");
                if (!file.isFile() || file.length() == 0) download(address, file);
                Bitmap bitmap = decode(file);
                if (bitmap == null) {
                    file.delete();
                    throw new IllegalStateException("Görsel çözülemedi");
                }
                file.setLastModified(System.currentTimeMillis());
                post(() -> {
                    if (!address.equals(target.getTag())) return;
                    target.setImageBitmap(bitmap);
                    target.animate().alpha(1f).setDuration(180L).start();
                });
            } catch (Exception ignored) {
                post(() -> {
                    if (!address.equals(target.getTag())) return;
                    target.setAlpha(0.18f);
                    target.setImageResource(R.drawable.balkes_logo);
                });
            }
        });
    }

    public void close() {
        closed = true;
        executor.shutdownNow();
        main.removeCallbacksAndMessages(null);
    }

    private void download(String address, File destination) throws Exception {
        File temporary = new File(destination.getParentFile(),
                destination.getName() + "." + Thread.currentThread().getId() + ".tmp");
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection();
        try {
            connection.setConnectTimeout(7_000);
            connection.setReadTimeout(18_000);
            connection.setUseCaches(true);
            connection.setRequestProperty("Accept", "image/*");
            connection.setRequestProperty("User-Agent", "Balkes-Android/1.5");
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new IllegalStateException("HTTP " + status);

            int total = 0;
            try (InputStream input = connection.getInputStream();
                 FileOutputStream output = new FileOutputStream(temporary)) {
                byte[] buffer = new byte[32_768];
                int count;
                while ((count = input.read(buffer)) >= 0) {
                    total += count;
                    if (total > MAX_DOWNLOAD_BYTES) {
                        throw new IllegalStateException("Görsel çok büyük");
                    }
                    output.write(buffer, 0, count);
                }
            }
            if (destination.exists()) destination.delete();
            if (!temporary.renameTo(destination)) {
                throw new IllegalStateException("Görsel önbelleğe alınamadı");
            }
            trimCache();
        } finally {
            connection.disconnect();
            if (temporary.exists() && !destination.exists()) temporary.delete();
        }
    }

    private Bitmap decode(File file) {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeFile(file.getAbsolutePath(), bounds);

        int sample = 1;
        while (bounds.outWidth / sample > MAX_DECODE_EDGE
                || bounds.outHeight / sample > MAX_DECODE_EDGE) {
            sample *= 2;
        }

        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = Math.max(1, sample);
        options.inPreferredConfig = Bitmap.Config.ARGB_8888;
        return BitmapFactory.decodeFile(file.getAbsolutePath(), options);
    }

    private synchronized void trimCache() {
        File[] files = cacheDir.listFiles(file -> file.isFile() && file.getName().endsWith(".img"));
        if (files == null || files.length == 0) return;

        long total = 0L;
        for (File file : files) total += file.length();
        if (total <= MAX_CACHE_BYTES) return;

        Arrays.sort(files, Comparator.comparingLong(File::lastModified));
        for (File file : files) {
            if (total <= MAX_CACHE_BYTES) break;
            long length = file.length();
            if (file.delete()) total -= length;
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
