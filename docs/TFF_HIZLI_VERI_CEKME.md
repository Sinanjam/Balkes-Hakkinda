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

## Gece boyunca yerelde çalıştırma

Proje klasöründe yalnız şu komutu ver:

```fish
fish start-tff-local.fish
```

Bu komut `balkes-tff-sync` adlı yerel systemd kullanıcı görevini başlatır.
Terminal kapanabilir; bilgisayar açık ve kullanıcı oturumu etkin kaldığı sürece
iş sürer. Bilgisayardan tamamen çıkış yapacaksan görevi başlatmadan önce bir kez:

```fish
sudo loginctl enable-linger $USER
```

Durumu ve son kalite raporunu görmek için:

```fish
fish status-tff-local.fish
```

Durdurmak için:

```fish
fish stop-tff-local.fish
```

Durdurmak indirilenleri silmez. Aynı başlatma komutu kaldığı yerden, yerel
`.cache/tff/` önbelleğini kullanarak devam eder. Görev ilk üç denemede önbelleği
korur; hâlâ hata varsa dördüncü denemede eski/bozuk HTML olasılığını elemek için
bir kez tam yenileme yapar. Sonraki denemeler yine önbelleklidir.

Varsayılan görev kalite kapısı geçene kadar durmaz. Daha az paralellik istersen:

```fish
fish start-tff-local.fish 6
```

Ön planda çalıştırmak istersen:

```fish
fish sync-tff-until-clean.fish
```

Bu akış **yalnız yerelde çalışır**; GitHub'a veri göndermez. Üretilen veri
`generated/tff-data/`, günlük `.cache/tff/overnight/latest.log`, son makinece
okunabilir sonuç ise `generated/tff-data/reports/completion.json` içindedir.

`true` ile zorunlu yenilemeyi yalnız bozuk bir HTML önbelleği olduğunda kullan.
Normal devam komutu daha hızlıdır:

```fish
fish sync-tff.fish 10 false
```

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
- Eski liglerde Kademe/Klasman gibi aynı sezon içindeki birden çok resmi aşama

## Mevcut çıktıyı temizlemek

Eski bir `generated/tff-data` klasörünü yeniden indirmeden yalnız yerel olarak
temizlemek için:

```fish
nix develop . --command python3 tools/tff/sanitize_export.py \
  --data-root generated/tff-data
```

Bu işlem yalnız üretilmiş veri ağacında çalışır; U14-U21/PAF/BAL kayıtlarını,
ertelenip başka tarihte oynanmış eski fikstürü ve indekste olmayan artık detay
dosyalarını çıkarır. Tam senkron bunu zaten otomatik çalıştırır.

## Dosya düzeni

```text
generated/tff-data/
  manifest.json
  data_report.json
  seasons/<sezon>/season.json
  seasons/<sezon>/matches_index.json
  seasons/<sezon>/matches/<mac-id>.json
  seasons/<sezon>/standings_by_week.json
  reports/sanitization.json
  reports/club_fixture_discovery.json
  reports/repair_export.json
  reports/repair_validation.json
  reports/validation.json
  reports/completion.json
```

Ham HTML ve kaldığı yer bilgisi `.cache/tff/` altında tutulur. Bu klasörler
Git'e eklenmez; uygulama APK'sına da girmez.

## Hız ve güvenlik

- Sezon keşfi, sezon işleme ve maç detayları sınırlı paralellikle çalışır.
- TFF RadGrid sayfalaması HTML'deki gerçek numaralı ASP.NET LinkButton ile
  yapılır. Sayfa geçişi yine olmazsa ilk sayfa kaybedilmez; sonuç açıkça
  `paginationComplete=false` olarak raporlanır.
- Resmi puan tablolarının haftaları paralel çekilir; aynı exact URL registry'de
  iki kez geçse bile yalnız bir kez indirilir.
- Varsayılan 10 iş TFF'yi gereksiz yere zorlamadan hızlı tamamlanacak şekilde
  seçilmiştir; 12'nin üzerine çıkılması önerilmez.
- Her istek iki kez denenir; 502/503/504 veren ölü arşiv dalları hızlı atlanır.
- Tarihi sezon dışındaki ve Balıkesirspor içermeyen maçlar yayımlanmaz.
- Yalnız profesyonel A takım kabul edilir. U14-U21, PAF, akademi, kadın,
  futsal ve BAL takımı etiketli kayıtlar kalite hatasıdır.
- Her çalışmanın sonunda bütün maç kimlikleri, detay dosyaları ve puan tabloları
  `reports/validation.json` içine raporlanır.
- Senkron artık sıkı modda doğrulanır. Beklenen profesyonel sezon, fikstür
  sayfalaması, lig maçı haftası veya haftalık tablo eksikse sıfır olmayan kodla
  biter ve yerel gece görevi yeniden dener.
- `completion.json`, temel alanların tamamlığını ve maçların kadro/olay/hakem
  kapsamasını ayrıca sayar. TFF'nin kendi maç sayfasında hiç yayımlanmamış alanlar
  uydurulmaz; `sourceLimitedMatches` altında kaynak kısıtı olarak listelenir.
- Bir sezonun lig/grup hedefi bulunamazsa yalnız Balıkesirspor maçlarından sahte
  bir "tam lig tablosu" hesaplanmaz; eksik durum kalite raporuna yazılır.
- Puan hedefi, sayfada istenen sezon ve doğru grup modülü birlikte görülmeden
  kabul edilmez. Aynı hedef iki farklı sezonda kullanılırsa doğrulama hata verir.
- Kademe toplamını devralan Klasman tablolarında ham resmi toplam ile o aşamada
  eklenen maç sayısı ayrı tutulur.
- TFF'de bulunmayan eski kayıtlar uydurulmaz; raporda eksik olarak bırakılır.

## Yüklenen ilk çıktıda bulunan sorunlar

`tff-data.zip` taramasında 440 kayıt görünmesine rağmen 2018-2019 klasöründeki
207 kaydın 166'sı altyapı/PAF maçıydı. Kulüp fikstürü keşfi 37 sezonun 31'inde
ikinci sayfaya geçememiş, 1996-1997 sezonunda yalnız 2 maç kalmış ve 2019-2020
COVID sonrası Temmuz maçları sezon dışı sayılmıştı.

Güçlendirilmiş hat canlı TFF denemesinde şu sonuçları verdi:

| Sezon | Eski çıktı | Canlı doğrulanan profesyonel çıktı |
|---|---:|---:|
| 2019-2020 | 30 | 34 lig + 1 kupa |
| 2018-2019 | 207 | 34 lig + 6 kupa |
| 1996-1997 | 2 | 32 lig + 1 kupa |

1996-1997 puan tablosu TFF'deki iki resmi aşamadan üretilir: Kademe 02 için
18 hafta/maç ve Klasman K2 için 14 hafta/maç. JSON kayıtlarında hem kesintisiz
`week` hem de aşama içindeki `stageWeek`, `stageId` ve `stageLabel` bulunur.

İkinci tam çıktıdaki 1083 profesyonel maç ve tarihsel puan hedefleri için yapılan
son denetim: [TFF veri çıktısı denetimi — 2026-07-12](TFF_DATA_AUDIT_2026-07-12.md).

Kalite kapısını ayrıca çalıştırmak için:

```fish
nix develop . --command python3 tools/tff/validate_export.py \
  --data-root generated/tff-data \
  --registry .cache/tff/runtime_registry.json
```

Yapısal hata, altyapı karışması, oynanan/ertelenmiş kopya veya resmi son tablo
ile maç sayısı çelişkisi varsa komut sıfır olmayan kodla biter.

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
