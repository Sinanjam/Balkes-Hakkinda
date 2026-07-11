# Balkes birleşik Android uygulaması

Bu iskelet, **Balkes Skor** paket kimliğini ve ağ tabanlı veri yaklaşımını korur; **Balkes Arşivi** içeriğini uzaktaki manifest üzerinden ekler. Büyük arşiv medyası APK'ya gömülmez.

## İlk iskelette çalışanlar

- Beş ana bölüm: Skor, Arşiv, Fotoğraf, Haber, Geçmiş Sezonlar.
- Mevcut Balkes Skor `manifest.json` verisini okuma.
- Mevcut Balkes Arşivi `archive_items.json` verisini okuma.
- Başarılı yanıtları uygulamanın özel dizininde önbelleğe alma.
- İnternet kesildiğinde son başarılı JSON'u gösterme.
- Firebase, keystore, yerel medya kopyası ve `google-services.json` olmadan küçük uygulama yapısı.
- Debug uygulamasında `.dev` paket eki; mevcut kurulu sürümle çakışmaz.

## NixOS + fish build

```fish
cd balkes-birlesik
chmod +x build.fish
fish build.fish
```

APK:

```text
app/build/outputs/apk/debug/app-debug.apk
```

Nix store salt okunur olduğu için gereken Android SDK bileşenleri `flake.nix`
içinde önceden tanımlıdır. Gradle'ın SDK'ya sonradan paket kurmasına izin
verilmez.

Farklı veri deposuyla build:

```fish
nix develop --command gradle --no-daemon :app:assembleDebug \
  -PCONTENT_BASE_URL=https://raw.githubusercontent.com/KULLANICI/DEPO/main/
```

`SCORE_BASE_URL`, `ARCHIVE_MANIFEST_URL` ve `ARCHIVE_MEDIA_BASE_URL` da aynı şekilde Gradle özelliği olarak değiştirilebilir.

Detaylı inceleme ve taşıma sırası: [docs/INCELEME_VE_TASIMA_PLANI.md](docs/INCELEME_VE_TASIMA_PLANI.md)
