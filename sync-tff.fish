#!/usr/bin/env fish
set -l root (dirname (status --current-filename))
cd $root

set -l workers 10
set -l force false
set -l output generated/tff-data

if test -n "$argv[1]"
    set workers $argv[1]
end
if test -n "$argv[2]"
    set force $argv[2]
end
if test -n "$argv[3]"
    set output $argv[3]
end

set -l extra
if test "$force" = "true"
    set extra --force
end

echo "TFF tam arşiv çekimi başlıyor"
echo "Paralel iş sayısı: $workers"
echo "Çıktı: $output"
echo "Önbelleği yenile: $force"

nix develop . --command python3 tools/tff/sync_all.py \
    --workers $workers \
    --output $output \
    $extra
or exit $status

echo "Bitti: $root/$output"
