# TFF veri çıktısı denetimi — 2026-07-11

## İncelenen paket

- Dosya: `tff-data.zip`
- SHA-256: `022e081b0d7053b14296d5438e19bfdf0d28ecf2386ab9b89ccea9d71889e13b`
- ZIP girdisi: 575
- Açılmış dosya: 551
- Açılmış boyut: yaklaşık 20 MB
- Yol taşması/bozuk ZIP: yok

## İlk çıktının özeti

- Keşif istenen sezon: 37
- Hatasız dönen sezon: 6
- Kulüp sayfasından bulunan maç: 0
- Sayfalama hatası veren sezon: 31
- Manifestte kalan sezon: 9
- Manifestte görünen maç: 440
- Haftalık puan tablosu: 236
- Eski validator sonucu: `ok_with_warnings`

Eski validator sonucu güvenilir değildi. Yapısal keşif hatalarını, altyapı
karışmasını, ertelenmiş kopyayı ve resmi tablo/maç sayısı farkını ölçmüyordu.

## Bulunan veri kusurları

### 2018-2019

- Toplam 207 kayıt vardı.
- 166 kayıt U14-U21, elit akademi veya PAF takımıydı.
- Profesyonel havuzda 35 lig ve 6 kupa kaydı vardı.
- `194862`, oynanmamış eski Balıkesirspor-Ümraniyespor fikstürüydü.
- Aynı eşleşme `205802` ile 28 Kasım 2018'de oynanmıştı.
- Doğru temiz sonuç: 34 lig + 6 kupa = 40 maç.

### 2019-2020

- Yalnız 30 lig maçı vardı.
- Resmi son puan tablosu Balıkesirspor için 34 maç gösteriyordu.
- 2, 6, 11 ve 19 Temmuz 2020 maçları, sezon sınırı 30 Haziran olduğu için
  yanlışlıkla reddedilmişti.
- Doğru sonuç: 34 lig + 1 kupa = 35 maç.

### 2023-2024

- Lig 15 takımlıydı.
- Takım başına 28 maç olmasına rağmen takvim 30 hafta sürdü.
- Eski `maxWeek=28` son iki takvim haftasını çekmedi; `maxWeek=30` yapıldı.

### 1996-1997

- İlk çıktıda yalnız 2 maç vardı.
- Canlı kulüp fikstürü iki sayfadan 33 profesyonel maç verdi.
- Doğru dağılım: 32 lig + 1 Türkiye Kupası.
- Resmi puan tablosu iki aşamalıdır:
  - Kademe 02: `pageID=805`, `grupID=210`, 18 maç
  - Klasman K2: `pageID=805`, `grupID=216`, 14 maç

## Uygulanan düzeltmeler

- Telerik RadGrid'in gerçek numaralı ASP.NET LinkButton postback'i okunuyor.
- Sayfalama tamamlanamazsa ilk sayfa korunuyor ve sonuç `partial` işaretleniyor.
- Profesyonel A takım filtresi eklendi.
- Ham HTML'deki ±700 karakter komşuluk seçimi kaldırıldı; maç kimlikleri satır
  bazında seçiliyor.
- Oynanan yeni tarih varken eski oynanmamış lig fikstürü çıkarılıyor.
- Birden çok lig aşaması aynı sezon içinde ayrı `stageId/stageWeek` ile tutuluyor.
- Puan tablosu URL'leri yinelenmeden ve haftalar paralel indiriliyor.
- Mevcut çıktıyı yerel temizleyen `sanitize_export.py` eklendi.
- Validator; keşif hatası, kapsama, altyapı karışması, artık dosya, kopya,
  manifest özeti ve resmi son tablo/maç sayısı tutarlılığını denetliyor.

## Canlı TFF doğrulaması

| Sezon | Fikstür sayfası | Keşfedilen | Yayımlanan |
|---|---:|---:|---:|
| 2025-2026 | 2/2 | 33 | — |
| 2019-2020 | 2/2 | 35 | 35 |
| 2018-2019 | 3/3 | 41 | 40 |
| 1996-1997 | 2/2 | 33 | 33 |

Üç eski sezonun 109 aday detayından 108 kayıt yayımlandı; tek düşen kayıt
2018-2019'daki oynanmamış/sonradan başka tarihte oynanmış fikstürdü. Yayımlanan
108 detayın tamamı kalite sınıfı A olarak doğrulandı. 2018-2019 ve 2019-2020
için 34'er resmi haftalık tablo üretildi.

## Sonuç

Yüklenen `tff-data.zip` doğrudan yayımlanmamalıdır. Yeni hatla aynı veri önce
temizlenmeli, sonra eksik sezonlar önbellekli tam senkronla tamamlanmalıdır.
Yapısal hata kaldığı sürece `validate_export.py` sıfır olmayan çıkış kodu verir.
