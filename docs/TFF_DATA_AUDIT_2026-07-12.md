# TFF veri çıktısı denetimi — 2026-07-12

## İncelenen paket

- Dosya: `tff-data(1).zip`
- SHA-256: `b9b35717fcb5449a30ef04cd47b44c2a4b127735f3d2218b0c94d479fd5d9bfd`
- ZIP girdisi: 1329
- Açılmış dosya: 1261
- Bozuk ZIP/yol taşması: yok

## Çıktının durumu

- Keşif: 37/37 sezon tamamlandı
- Profesyonel maç bulunan sezon: 31
- Yayımlanan maç: 1083
- Kalite: 1080 A, 3 B
- Altyapı/PAF sızıntısı: 0
- Artık detay dosyası: 0
- Haftalık puan tablosu: 788

Maç keşfi ve temizleme başarılıdır. Paket yine de doğrudan yayımlanamaz; eski
puan tablosu hedeflerinde iki yapısal kusur bulunmuştur.

## Bulunan yapısal kusurlar

1. 1990-1991 ile 2009-2010 arasındaki on tarihsel sezon yanlışlıkla aynı güncel
   `pageID=971&grupID=2605` hedefine bağlanmıştır. Maç detayındaki açılır kutu
   güncel ligi de içerdiği için yalnız "Balıkesirspor metni var" kontrolü yanlış
   pozitif üretmiştir.
2. 1995-1996 TFF sayfasında Kademe ve Klasman/Yükselme modülleri aynı HTML
   içindedir. Sayfa genelindeki ilk Balıkesirspor tablosu altı ayrı grup sanılmış,
   36 yerine 108 puan haftası üretilmiştir.
3. 2008-2009 Klasman K2 tablosu ilk aşamadaki 18 maçı devralır. Resmi son satır
   32 maç gösterse de ikinci aşamanın eklediği maç sayısı 14'tür.
4. 1995-1996 `47516` ile 1999-2000 `32333` ve `32335` kayıtları TFF detayında
   genel lig etiketi taşır; bunlar sezon sonu yükselme play-off maçlarıdır ve lig
   puan tablosu toplamına katılmamalıdır.

## Uygulanan güçlendirmeler

- Puan hedefi artık istenen sezon metnini ve kullanılabilir Balıkesirspor
  tablosunu birlikte doğrular.
- Yanlış eski `target.json` kayıtları keşif sürümü 2 ile otomatik geçersiz olur;
  maç HTML önbelleği korunur.
- Arşiv tablosu `grupID`'nin ait olduğu Kademe/Klasman modülü içinde parse edilir.
- Grup kimliği olmayan ayrı Yükselme/Final modülleri bağımsız aşama olarak bulunur.
- Resmi aşamalar kulüp fikstüründeki gerçek lig maçı sayısıyla uzlaştırılır.
- Devreden toplam taşıyan Klasman tablolarında yalnız yeni maçlar aşama toplamına
  eklenir; ham resmi toplam ayrıca korunur.
- Aynı puan hedefinin birden fazla sezonda kullanılması kalite kapısında yapısal
  hata sayılır.
- Kaynakla doğrulanan üç play-off sınıflandırması dar kapsamlı registry düzeltmesi
  olarak uygulanır; maçlar silinmez.

## Canlı TFF duman testi

| Sezon | Doğrulanan resmi hedef/aşama |
|---|---|
| 2009-2010 | 01 Kademe: 20 maç; Yükselme: 18 maç |
| 2008-2009 | 02 Kademe: 18 maç; K2: 14 yeni maç (18 maç devralır) |
| 2007-2008 | Grup 03: 32 maç |
| 2006-2007 | Grup 03: 30 maç |
| 2000-2001 | Grup 06: 32 maç |
| 1999-2000 | Grup 06: 32 lig maçı; ayrıca 2 play-off |
| 1998-1999 | Grup 07: 32 maç |
| 1997-1998 | Grup 06: 32 maç |
| 1991-1992 | Grup 7: 34 maç |
| 1990-1991 | Grup 7: 34 maç |
| 1995-1996 | Kademe 02: 18; Yükselme F: 18; ayrıca 1 play-off |

1995-1996 için 36/36 resmi haftalık tablo canlı olarak indirildi. Lig özeti 36
maç, 55-41 gol ve 61 puan; play-off maçı ayrıca korunur. Kaynak kodu birim testleri
16/16 geçmektedir.

## Sonraki koşu

Normal önbellekli komut yeterlidir:

```fish
fish sync-tff.fish 10 false
```

`--force` gerekmez. Yeni hedef sürümü yalnız hatalı puan hedeflerini yeniden
keşfeder; indirilmiş maç ayrıntıları kullanılmaya devam eder. İşlem sonunda
`reports/validation.json` içindeki `status` alanının `error` olmadığı
doğrulanmadan veri yayımlanmamalıdır.
