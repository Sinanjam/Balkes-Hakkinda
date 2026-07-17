#!/usr/bin/env fish
# Yalnız kalan iki puan tablosu sorununu onarır; maç arşivini baştan üretmez.
set -l root (realpath (dirname (status --current-filename)))
cd $root
or exit 1

set -l workers 5
if test -n "$argv[1]"
    set workers $argv[1]
end
if not string match -qr '^[1-8]$' -- $workers
    echo "Hata: paralel iş sayısı 1-8 arasında olmalı." >&2
    exit 2
end

set -l unit balkes-tff-sync
set -l output generated/tff-data
set -l cache .cache/tff
set -l registry $cache/runtime_registry.json
set -l reports $output/reports
set -l state_file $cache/overnight/state.env
set -l completion_report $reports/completion.json

function write_repair_state --argument-names phase code state_file output
    mkdir -p (dirname $state_file)
    printf 'PHASE=%s\nATTEMPT=targeted\nEXIT_CODE=%s\nUPDATED_AT=%s\nOUTPUT=%s\nLOG=foreground\n' \
        $phase $code (date -Is) $output >$state_file
end

function run_nix
    nix develop . --command env \
        PYTHONUNBUFFERED=1 \
        TFF_BASE_URL=http://www.tff.org/Default.aspx \
        TFF_FETCH_TIMEOUT=30 \
        $argv
end

if type -q systemctl
    if systemctl --user is-active --quiet $unit
        echo "Eski sonsuz deneme servisi durduruluyor..."
        systemctl --user stop $unit
        or begin
            echo "Hata: $unit durdurulamadı." >&2
            exit 1
        end
    end
end

if not test -f $registry
    echo "Hata: $registry yok. Önce tam senkronun en az bir kez çalışmış olması gerekiyor." >&2
    exit 2
end
if not test -f $output/manifest.json
    echo "Hata: $output/manifest.json yok; hedefli onarım güvenle çalıştırılamaz." >&2
    exit 2
end

mkdir -p $reports $cache/overnight
or exit 1
command cp -f $registry $cache/runtime_registry.before-standings-repair.json
or exit 1
for report in club_fixture_discovery.json repair_validation.json validation.json completion.json
    if test -f $reports/$report
        command cp -f $reports/$report $reports/$report.before-standings-repair
    end
end

write_repair_state repairing -1 $state_file $output
echo ""
echo "1/6 — İki sezonun TFF fikstür hedefleri güncelleniyor..."
run_nix python3 tools/tff/discover_club_fixtures.py \
    --registry tools/tff/balkes_tff_seed_registry.json \
    --output $registry \
    --report $reports/club_fixture_discovery.json \
    --cache-dir $cache/club_fixtures \
    --raw-dir $cache/raw \
    --target-cache-dir $cache/standings_targets \
    --workers $workers \
    --timeout 30 \
    --attempts 3 \
    --delay 0.08 \
    --allow-empty \
    --season 2025-2026 \
    --season 2006-2007
set -l discovery_status $status
if test $discovery_status -ne 0
    write_repair_state failed $discovery_status $state_file $output
    echo "Hata: hedef keşfi tamamlanamadı." >&2
    exit $discovery_status
end

# Hedefli işlem hiçbir koşulda diğer sezonların runtime kayıtlarını düşürmemeli.
run_nix jq -e '(.seasons | length) >= 32 and (.runOrder | length) >= 32' $registry >/dev/null
set -l registry_status $status
if test $registry_status -ne 0
    command cp -f $cache/runtime_registry.before-standings-repair.json $registry
    write_repair_state failed 3 $state_file $output
    echo "Güvenlik durdurması: diğer sezon kayıtları korunamadı; runtime yedeği geri yüklendi." >&2
    exit 3
end

echo ""
echo "2/6 — Yarım kalan tam senkronun boşalttığı tablolar önbellekten kuruluyor..."
run_nix python3 tools/tff/tff_standings_builder.py \
    --seed $registry \
    --data-root $output \
    --raw-root $cache/standings \
    --reports-root $reports/standings \
    --penalties tools/tff/standings_penalties.json \
    --repair-incomplete-only \
    --mode official-only \
    --probe-limit 5000 \
    --workers $workers \
    --week-workers $workers \
    --season-workers 2 \
    --detail-fetch-mode none \
    --week-param-mode smart \
    --sleep 0.08
set -l recovery_status $status
if test $recovery_status -ne 0
    write_repair_state failed $recovery_status $state_file $output
    echo "Hata: önbellekten puan tablosu kurtarma tamamlanamadı." >&2
    exit $recovery_status
end

echo ""
echo "3/6 — 2025-2026 ve 2006-2007 resmi haftaları taze çekiliyor..."
run_nix python3 tools/tff/tff_standings_builder.py \
    --seed $registry \
    --data-root $output \
    --raw-root $cache/standings \
    --reports-root $reports/standings \
    --penalties tools/tff/standings_penalties.json \
    --season 2025-2026 \
    --season 2006-2007 \
    --mode official-only \
    --probe-limit 5000 \
    --workers $workers \
    --week-workers $workers \
    --season-workers 1 \
    --detail-fetch-mode missing \
    --week-param-mode smart \
    --sleep 0.08 \
    --force
set -l standings_status $status
if test $standings_status -ne 0
    write_repair_state failed $standings_status $state_file $output
    echo "Hata: resmi puan tabloları üretilemedi." >&2
    exit $standings_status
end

echo ""
echo "4/6 — Maç haftaları ve indeksler yeniden bağlanıyor..."
run_nix python3 tools/tff/repair_export.py \
    --data-root $output \
    --registry $registry \
    --report $reports/repair_export.json \
    --validation-report $reports/repair_validation.json
set -l repair_status $status
if test $repair_status -ne 0
    write_repair_state failed $repair_status $state_file $output
    echo "Hata: çıktı onarımı tamamlanamadı." >&2
    exit $repair_status
end

echo ""
echo "5/6 — Bütün 32 sezon sıkı kurallarla doğrulanıyor..."
run_nix python3 tools/tff/validate_export.py \
    --data-root $output \
    --report $reports/validation.json \
    --registry $registry \
    --discovery-report $reports/club_fixture_discovery.json \
    --strict
set -l validation_status $status

echo ""
echo "6/6 — Son kalite kapısı çalışıyor..."
run_nix python3 tools/tff/completion_gate.py \
    --data-root $output \
    --report $completion_report
set -l completion_status $status

echo ""
if test -f $completion_report
    run_nix jq '{status, readyToPublish, summary, errors, warnings}' $completion_report
end

if test $validation_status -eq 0 -a $completion_status -eq 0
    write_repair_state completed 0 $state_file $output
    echo ""
    echo "TAMAMLANDI: 32 sezon korundu ve sıkı kalite kapısı geçildi."
    exit 0
end

write_repair_state failed 1 $state_file $output
echo ""
echo "Onarım bitti fakat kalite kapısında hâlâ gerçek bir eksik var. Yukarıdaki JSON yeterli; sonsuz servisi yeniden başlatma." >&2
exit 1
