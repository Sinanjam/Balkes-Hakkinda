# TFF çıktı onarımı ve kalite kapısı

`sync-tff.fish`, puan tablolarını ürettikten sonra otomatik olarak
`tools/tff/repair_export.py` aracını çalıştırır.

Araç yalnızca doğrulanmış TFF maç JSON'larını işler:

- lig maçlarını kulüp fikstüründeki gerçek hafta numarasıyla eşleştirir;
- Kademe/Klasman/Yükselme gibi aşamalarda `week` ve `stageWeek` alanlarını ayrı tutar;
- kupa ve play-off maçlarına lig haftası yazmaz;
- kişi adlarına yapışmış `,90+`, `45+2`, `12. dk` benzeri parçaları temizler;
- maç oyuncu listesini ve global oyuncu/rakip indekslerini yeniden kurar;
- Android'in eski alanlarıyla yeni snake_case istatistik alanlarını birlikte üretir.

Çalışma başarısız sayılır ve senkron durursa iki rapora bakın:

```text
generated/tff-data/reports/repair_export.json
generated/tff-data/reports/repair_validation.json
```

`repair_validation.json` içindeki `status` değeri `ok` olmalıdır. Ayrıca
`fallbackWeeks`, `dirtyPersonNames` ve `incompatiblePlayers` değerleri sıfır
olmadan çıktı yayınlanmamalıdır.

## Yerel kontrol

Fish/NixOS ortamında:

```fish
nix develop
python tools/tff/tests/test_repair_export.py
fish sync-tff.fish 10 false
jq '.status, .leagueMatches, .players, .errors' generated/tff-data/reports/repair_validation.json
```

Önbelleği sıfırlayıp TFF sayfalarını yeniden indirmek gerekirse son argümanı
`true` yapın:

```fish
fish sync-tff.fish 10 true
```
