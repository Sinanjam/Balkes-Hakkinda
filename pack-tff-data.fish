#!/usr/bin/env fish
# Yalnız kalite kapısı geçmiş ve artık değişmeyen TFF çıktısını paketler.
set -l root (realpath (dirname (status --current-filename)))
cd $root
or exit 1

set -l unit balkes-tff-sync
set -l data_dir generated/tff-data
set -l report $data_dir/reports/completion.json

if systemctl --user is-active --quiet $unit
    echo "Paketleme durduruldu: TFF görevi hâlâ çalışıyor." >&2
    echo "Önce: fish status-tff-local.fish" >&2
    exit 2
end
if not test -f $report
    echo "Paketleme durduruldu: completion.json bulunamadı." >&2
    exit 2
end

set -l ready (nix develop . --command jq -r '.readyToPublish // false' $report | tail -n 1)
if test "$ready" != "true"
    echo "Paketleme durduruldu: kalite kapısı henüz geçilmedi." >&2
    nix develop . --command jq '{status, readyToPublish, summary, errors}' $report
    exit 2
end

set -l archive tff-data-final-(date +%Y%m%d-%H%M%S).zip
nix develop . --command sh -c \
    'cd generated && zip -q -r ../"$1" tff-data' sh $archive
or exit $status

nix develop . --command unzip -tq $archive
or begin
    echo "ZIP doğrulaması başarısız: $archive" >&2
    exit 3
end

echo "Hazır ve doğrulandı: $root/$archive"
