#!/usr/bin/env fish
# Yalnız kalite kapısı geçmiş ve artık değişmeyen TFF çıktısını paketler.
set -l root (realpath (dirname (status --current-filename)))
cd $root
or exit 1

set -l unit balkes-tff-sync
set -l data_dir generated/tff-data
set -l report $data_dir/reports/completion.json
set -l release_dir local-releases/tff-data

if type -q systemctl; and systemctl --user is-active --quiet $unit
    echo "Paketleme durduruldu: TFF görevi hâlâ çalışıyor." >&2
    echo "Önce: fish status-tff-local.fish" >&2
    exit 2
end
if not test -f $report
    echo "Paketleme durduruldu: completion.json bulunamadı." >&2
    exit 2
end

nix develop . --command python3 tools/tff/package_release.py \
    --data-root $data_dir \
    --output-dir $release_dir
or exit $status

echo
echo "Hazır: $root/$release_dir"
echo "ZIP + SHA-256 + kalite özeti birlikte üretildi."
