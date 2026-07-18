# İki proje incelemesi ve taşıma planı

## Kısa sonuç

Ana taban olarak Balkes Skor'un `com.sinanjam.balkesskor` kimliği korunmalıdır. Arşiv uygulamasının veri zenginliği alınmalı; 3.552 satırlık `MainActivity`, 156 MB asset ve 13 MB resource doğrudan taşınmamalıdır. Birleşik uygulamada GitHub veri deposu tek doğruluk kaynağı, telefonun özel dizini ise yalnızca önbellek olmalıdır.

## Mevcut projeler

| Konu | Balkes Skor | Balkes Arşivi | Birleşik karar |
| --- | --- | --- | --- |
| Paket | `com.sinanjam.balkesskor` | `com.sinanjam.arsiv` | Skor paketi korunur |
| Java yapı | 1 adet, 1.277 satırlık Activity | 3 Activity/receiver; ana dosya 3.552 satır | Veri, ekran ve ağ kodu ayrılır |
| Veri | GitHub raw `data/` | APK asset + kısmi GitHub indirme | Tamamen uzaktaki sürümlü manifest |
| APK girdisi | 4,1 MB asset, 1,1 MB logo | 156 MB asset, 13 MB resource | Küçük vector/ikon dışında medya yok |
| Çevrimdışı | İnternet yoksa uygulama kapanır | Yerel asset'e döner | Son başarılı JSON/medya önbelleği |
| Sayaç | Firebase SDK | Elle yazılmış Firestore REST | İlk sürümden çıkar; gerekirse ayrı modül |
| Güncelleme | GitHub release kontrolü | Splash + receiver ile mükerrer | Tek güncelleme servisi, sonraki aşama |
| Build | Nix dosyası + Gradle | Nix dosyası + Gradle | Tek `flake.nix`, fish build komutu |

## Yinelenen ve çakışan parçalar

1. Her iki projede de `HttpURLConnection`, JSON ayrıştırma, splash/release kontrolü, koyu tema kartları ve aktif kullanıcı sayacı ayrı ayrı yazılmış.
2. Her iki projede de uygulama durumu ile ekran çizimi aynı Activity içinde. Bu durum yeni bölüm eklemeyi ve hata ayıklamayı zorlaştırıyor.
3. Skor kaynak kodu yalnızca uzaktaki veriyi okuduğu halde `app/src/main/assets/data` kopyası APK'ya giriyor.
4. Arşiv güncelleme kodu uzak JSON'u indiriyor fakat yeni veriyi kaydetmeden uzak önbellek anahtarlarını siliyor; ardından tekrar yerel asset'i okuyor. Gerçek uzaktan güncelleme akışı bu nedenle etkisiz.
5. Skor manifestindeki `dataBaseUrl` alanı varken uygulama sabit `BASE_DATA_URL` kullanıyor. Manifest tabanlı yönlendirme devreye alınmalı.
6. Arşivde aynı içerik hem `VERI_KAYNAGI_YENI_CEKIM`, hem `assets/archive_data`, hem de `wayback_media` altında tekrar bulunuyor.
7. Eski projelerde keystore/parola ve Firebase yapılandırması kaynak ağacında. Yeni projeye taşınmamalı; release imzası kullanıcıya özel ve Git dışı tutulmalı.
8. ZIP'lerde `build/`, `.gradle/` ve hazır APK gibi üretilebilir çıktılar var. Yeni depo bunları izlememeli.

## Hedef veri deposu

```text
balkes-data/
  manifest.json
  score/manifest.json
  score/seasons/<id>/...
  archive/index.json
  archive/items/<id>.json
  photos/index.json
  news/index.json
  media/archive/...
  media/news/...
```

Liste dosyaları küçük olmalı. Uzun arşiv metni, ayrıntılı maç ve büyük fotoğraf listesi ilgili detay dosyasına bölünmelidir. Her manifest `schemaVersion`, `dataVersion` ve `generatedAt` taşımalıdır. Medyada mümkünse WebP/AVIF küçük önizleme ve ayrı tam boy adres kullanılmalıdır.

## Uygulanabilir taşıma sırası

### 1. Temiz taban

- Skor application ID'sini koru.
- Firebase, `google-services.json`, keystore, build çıktısı ve yerel veri assetlerini çıkar.
- Tek Nix shell ve fish build giriş noktası kullan.
- Debug sürümünü `.dev` ekiyle ayrı kur.

### 2. Ortak ağ ve önbellek

- Bütün JSON isteklerini tek repository üzerinden geçir.
- Bağlantı zaman aşımı, HTTP durum kontrolü ve disk önbelleğini tek yerde yönet.
- Son başarılı JSON'u çevrimdışı göster.
- Sonraki adımda ETag/If-None-Match ve önbellek yaş politikası ekle.

### 3. Skor taşıması

- Mevcut sezon, maç, puan ve oyuncu ayrıştırıcılarını küçük model sınıflarına böl.
- `dataBaseUrl` alanına saygı göster; sabit URL yalnızca başlangıç manifesti için kalsın.
- Eski `MainActivity` ekranlarını birer ekran sınıfına taşı.

### 4. Arşiv taşıması

- Mevcut 71 öğelik JSON'u `archive/index.json` ve öğe detaylarına böl.
- Arama, favori yazı, favori fotoğraf, tablo gösterimi ve okuma boyutu özelliklerini sırayla taşı.
- `asset` yollarını doğrudan `mediaBaseUrl` ile çözülen uzak medya yollarına dönüştür.

### 5. Fotoğraf katmanı

- Küçük önizleme/tam boy çiftini manifestte tanımla.
- Diskte LRU sınırı uygula; APK içine medya koyma.
- Kaydet/paylaş işlevini Android sürümlerine uygun tek servis içinde taşı.

### 6. Haber ve duyuru

- `news/index.json` sözleşmesini yayımla.
- Kategori, yayımlanma tarihi, özet, detay URL'si ve isteğe bağlı görsel alanlarını kullan.
- Bildirim ancak veri akışı kararlı olduktan sonra WorkManager benzeri zamanlanmış katmana alınmalı.

### 7. Sürüm ve güvenlik

- GitHub release kontrolünü veri kontrolünden ayır; ağ hatası uygulamayı engellemesin.
- Release imzasını ortam değişkeni veya Git dışı `secrets.properties` ile bağla.
- Firebase sayaç istenirse uygulamanın temel çalışmasını etkilemeyen ayrı, isteğe bağlı modül yap.

### 8. Test ve yayın kapıları

- JSON şemalarını CI'da doğrula.
- Bozuk/eksik manifest, HTTP 404, çevrimdışı önbellek ve eski şema testleri ekle.
- Debug APK boyutunu ve APK içindeki en büyük dosyaları her build'de raporla.
- Veri deposu ve uygulama sürümünü birbirinden bağımsız yayımla.

## Bu iskelette tamamlanan ilk dilim

- Skor paket kimliği korundu.
- Beş bölümlü birleşik gezinme oluşturuldu.
- Skor ve arşiv mevcut GitHub adreslerinden okunuyor.
- Ortak JSON repository ve disk önbelleği eklendi.
- Haber bölümü gelecekteki `news/index.json` için hazırlandı.
- Medya, Firebase ve gizli imza dosyaları APK/kaynak ağacına alınmadı.
