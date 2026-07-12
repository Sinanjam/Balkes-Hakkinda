#!/usr/bin/env fish
# Yerel TFF senkronunu kalite kapısı geçene kadar önbellekli biçimde tekrarlar.
set -l root (dirname (status --current-filename))
cd $root
or exit 1

set -l workers 10
set -l output generated/tff-data
set -l retry_seconds 120
set -l max_attempts 0

if test -n "$argv[1]"
    set workers $argv[1]
end
if test -n "$argv[2]"
    set output $argv[2]
end
if test -n "$argv[3]"
    set retry_seconds $argv[3]
end
if test -n "$argv[4]"
    set max_attempts $argv[4]
end

for value in $workers $retry_seconds $max_attempts
    if not string match -qr '^[0-9]+$' -- $value
        echo "Hata: workers, retry_seconds ve max_attempts tam sayı olmalı." >&2
        exit 2
    end
end
if test $workers -lt 1 -o $workers -gt 12
    echo "Hata: paralel iş sayısı 1-12 arasında olmalı." >&2
    exit 2
end

set -l state_dir .cache/tff/overnight
set -l log_file $state_dir/latest.log
set -l state_file $state_dir/state.env
mkdir -p $state_dir
or exit 1
touch $log_file

function write_state --argument-names phase attempt exit_code
    printf 'PHASE=%s\nATTEMPT=%s\nEXIT_CODE=%s\nUPDATED_AT=%s\nOUTPUT=%s\nLOG=%s\n' \
        $phase $attempt $exit_code (date -Is) $output $log_file >$state_file
end

echo "Yerel TFF görevi başladı: "(date -Is) | tee -a $log_file
echo "Çıktı=$output | paralellik=$workers | bekleme=$retry_seconds sn | azamiDeneme=$max_attempts" | tee -a $log_file
echo "max_attempts=0 ise kalite kapısı geçene kadar durmaz." | tee -a $log_file

set -l attempt 0
while true
    set attempt (math $attempt + 1)
    set -l force false
    # İlk üç tur önbelleği kullanır. Hata kalırsa dördüncü turda eski/bozuk
    # HTML olasılığını elemek için yalnız bir kez tam yenileme yapılır.
    if test $attempt -eq 4
        set force true
    end

    write_state running $attempt -1
    echo "" | tee -a $log_file
    echo "=== DENEME $attempt | "(date -Is)" | force=$force ===" | tee -a $log_file

    fish ./sync-tff.fish $workers $force $output 2>&1 | tee -a $log_file
    set -l sync_status $pipestatus[1]

    if test $sync_status -eq 0
        write_state completed $attempt 0
        echo "TAMAMLANDI: sıkı kalite kapısı geçildi — "(date -Is) | tee -a $log_file
        exit 0
    end

    write_state retrying $attempt $sync_status
    echo "Deneme $attempt tamamlanamadı (kod=$sync_status). Önbellek korunuyor." | tee -a $log_file
    if test $max_attempts -gt 0 -a $attempt -ge $max_attempts
        write_state failed $attempt $sync_status
        echo "Azami deneme sayısına ulaşıldı." | tee -a $log_file
        exit $sync_status
    end
    echo "$retry_seconds saniye sonra yeniden denenecek." | tee -a $log_file
    sleep $retry_seconds
end
