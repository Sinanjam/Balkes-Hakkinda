#!/usr/bin/env fish
set -l unit balkes-tff-sync
if systemctl --user is-active --quiet $unit
    systemctl --user stop $unit
    echo "Yerel TFF görevi durduruldu. Önbellek silinmedi."
else
    echo "Çalışan yerel TFF görevi yok."
end
