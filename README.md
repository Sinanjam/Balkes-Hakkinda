# Balkes birleşik Android uygulaması

Bu iskelet, **Balkes Skor** paket kimliğini ve ağ tabanlı veri yaklaşımını korur; **Balkes Arşivi** içeriğini uzaktaki manifest üzerinden ekler. Büyük arşiv medyası APK'ya gömülmez.

## İlk iskelette çalışanlar

- Tek Activity üzerinde çökme riskini azaltan neon splash ve her açılışta premium
  **Skor Merkezi / Balkes Arşivi** seçim ekranı.
- Beş ana bölüm: Skor, Arşiv, Fotoğraf, Haber, Geçmiş Sezonlar.
- Mevcut Balkes Skor `manifest.json` verisini okuma.
- Mevcut Balkes Arşivi `archive_items.json` verisini okuma.
- Skor ve arşiv manifestlerini seçim ekranındayken arka planda ön yükleme.
- Bellek ve disk önbelleğini anında gösterip GitHub verisini arkada yenileme.
- Aynı adrese giden eşzamanlı istekleri tek ağ isteğinde birleştirme.
- İnternet kesildiğinde son başarılı JSON'u gecikmeden gösterme.
- Premium koyu-kırmızı arayüz, belirgin bölüm kartları ve durum rozetleri.
- Siyah zeminli kırmızı/camgöbeği neon şema.
- Alt bölüm menüsü tamamen kaldırıldı; Skor/Arşiv seçimi açılış ekranından yapılıyor.
- Android 6–15, ekran çentiği ve sistem çubukları için edge-to-edge tam ekran uyumu.
- Samsung Android sürümlerinde pencere oluşmadan sistem çubuğu denetleyicisine
  erişmeyen güvenli açılış sırası.
- Android 12 sistem splash'iyle uyumlu özel neon açılış ekranı.
- Arşiv indeksindeki 71 kaydın tamamını kademeli ve akıcı biçimde gösterme.
- Başlık, sezon ve açıklama içinde çalışan hızlı arşiv araması.
- Detay açıldığında uzaktan indirilen, küçültülerek gösterilen ve diskte önbelleğe
  alınan gerçek arşiv fotoğrafları.
- Bağlantı hatalarında açıklayıcı mesaj ve tek dokunuşla **Tekrar Dene**.
- Arşiv kartından tam yazı, fotoğraf bilgisi ve tablo detayını açma.
- Sezon kartından maç listesine, maç kartından olay ve hakem detayına geçme.
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

## Telefona kurup aç

Telefonunda **Geliştirici seçenekleri > USB hata ayıklama** açıkken kabloyu bağla:

```fish
nix develop --command adb install -r app/build/outputs/apk/debug/app-debug.apk
nix develop --command adb shell am force-stop com.sinanjam.balkesskor.dev
nix develop --command adb shell am start -n com.sinanjam.balkesskor.dev/com.sinanjam.balkesskor.MainActivity
```

Uygulama yine kapanırsa hata kaydını tek dosyaya al:

```fish
nix develop --command adb logcat -d '*:E' > balkes-hata.txt
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

## TFF arşiv verisini çek

Balıkesirspor'un TFF'deki profesyonel sezonlarını, ayrıntılı maçlarını ve hafta
hafta puan tablolarını önbellekli/paralel biçimde üretmek için:

```fish
fish sync-tff.fish
```

Yarım kalırsa aynı komutu yeniden çalıştır; biten dosyalar tekrar indirilmez.
Detaylar: [TFF hızlı veri çekme](docs/TFF_HIZLI_VERI_CEKME.md)

Uzun çekimi yalnız bu bilgisayarda, terminal kapansa da kalite kapısını geçene
kadar çalıştırmak için:

```fish
fish start-tff-local.fish
```

```fish
fish status-tff-local.fish
fish stop-tff-local.fish
```

Görev bittikten ve `readyToPublish: true` görüldükten sonra doğrulanmış ZIP
oluşturmak için:

```fish
fish pack-tff-data.fish
```

Paketleyici görev çalışırken veya kalite kapısı geçilmemişken dosya üretmez;
oluşturduğu `tff-data-final-*.zip` arşivini de otomatik test eder.

Bu görev GitHub'a veya APK'ya veri yüklemez. Sonuç ve ham önbellek sırasıyla
`generated/tff-data/` ve `.cache/tff/` altında yerelde kalır. Yapısal eksik,
yarım TFF sayfalaması veya eksik puan tablosu varken görev tamamlanmış sayılmaz.

Son 1083 maçlık çıktının puan tablosu denetimi ve giderilen tarihsel hedef
hataları: [docs/TFF_DATA_AUDIT_2026-07-12.md](docs/TFF_DATA_AUDIT_2026-07-12.md)

Detaylı inceleme ve taşıma sırası: [docs/INCELEME_VE_TASIMA_PLANI.md](docs/INCELEME_VE_TASIMA_PLANI.md)
