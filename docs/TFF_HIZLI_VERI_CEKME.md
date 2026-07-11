# TFF hızlı veri çekme

## Tek komut

Proje klasöründe:

```fish
fish sync-tff.fish
```

Varsayılan ayar 10 paralel iş kullanır. Daha yavaş bağlantıda veya TFF hata
verirse 6 iş kullan:

```fish
fish sync-tff.fish 6
```

Önbelleği tamamen yenilemek için:

```fish
fish sync-tff.fish 10 true
```

Çıktı `generated/tff-data/` altında oluşur. Yarım kalırsa aynı komutu yeniden
çalıştırmak yeterlidir; tamamlanan HTML ve JSON dosyaları tekrar indirilmez.

## Yalnızca bir sezonu denemek

Önce tek sezonla hızlı kontrol:

```fish
nix develop . --command python3 tools/tff/sync_all.py \
  --season 2025-2026 \
  --workers 10
```

## Ne toplar?

- TFF kulüp sayfasındaki profesyonel Balıkesirspor fikstürleri
- Maç sayfasındaki resmi puan-cetveli seçicisinden doğru lig ve grup hedefi
- Maç kodu, tarih, saat, stat, organizasyon ve skor
- Hakemler ve diğer görevliler
- Ev/deplasman ilk 11, yedekler ve teknik ekip
- Goller, gol türü ve dakikası
- Sarı/kırmızı kartlar
- Oyuncu değişiklikleri
- TFF oyuncu ve maç kimlikleri
- Bulunabildiği yerde resmi hafta hafta puan cetveli
- Resmi haftalık tablo yoksa TFF maç sonuçlarından hesaplanan ve kaynak türü
  açıkça işaretlenen haftalık tablo

## Dosya düzeni

```text
generated/tff-data/
  manifest.json
  data_report.json
  seasons/<sezon>/season.json
  seasons/<sezon>/matches_index.json
  seasons/<sezon>/matches/<mac-id>.json
  seasons/<sezon>/standings_by_week.json
  reports/validation.json
```

Ham HTML ve kaldığı yer bilgisi `.cache/tff/` altında tutulur. Bu klasörler
Git'e eklenmez; uygulama APK'sına da girmez.

## Hız ve güvenlik

- Sezon keşfi, sezon işleme ve maç detayları sınırlı paralellikle çalışır.
- Varsayılan 10 iş TFF'yi gereksiz yere zorlamadan hızlı tamamlanacak şekilde
  seçilmiştir; 12'nin üzerine çıkılması önerilmez.
- Her istek iki kez denenir; 502/503/504 veren ölü arşiv dalları hızlı atlanır.
- Tarihi sezon dışındaki ve Balıkesirspor içermeyen maçlar yayımlanmaz.
- Her çalışmanın sonunda bütün maç kimlikleri, detay dosyaları ve puan tabloları
  `reports/validation.json` içine raporlanır.
- Bir sezonun lig/grup hedefi bulunamazsa yalnız Balıkesirspor maçlarından sahte
  bir "tam lig tablosu" hesaplanmaz; eksik durum kalite raporuna yazılır.
- TFF'de bulunmayan eski kayıtlar uydurulmaz; raporda eksik olarak bırakılır.

## GitHub verisine dönüştürme

Üretilen klasör APK'ya gömülmek için değil, GitHub veri dalına/repo'suna
yüklenmek içindir. Uygulamanın okuyacağı varsayılan kök:

```text
https://raw.githubusercontent.com/Sinanjam/Balkes-Hakkinda/main/data/
```

Başka bir veri reposu kullanırsan komuttan önce fish'te şunu ayarlayabilirsin:

```fish
set -x BALKES_DATA_BASE_URL https://raw.githubusercontent.com/KULLANICI/REPO/main/data/
fish sync-tff.fish
```
