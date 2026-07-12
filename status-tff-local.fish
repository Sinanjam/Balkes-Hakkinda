#!/usr/bin/env fish
set -l root (realpath (dirname (status --current-filename)))
set -l unit balkes-tff-sync
set -l state_file $root/.cache/tff/overnight/state.env
set -l report $root/generated/tff-data/reports/completion.json

if systemctl --user is-active --quiet $unit
    echo "Durum: ÇALIŞIYOR"
else
    echo "Durum: ÇALIŞMIYOR"
end

if test -f $state_file
    echo ""
    echo "Son görev durumu:"
    sed -n '1,20p' $state_file
end

if test -f $report
    echo ""
    echo "Son kalite raporu:"
    nix develop $root --command jq \
        '{status, readyToPublish, summary, errors, warnings}' $report
end

echo ""
echo "Son günlük:"
journalctl --user --unit=$unit --lines=25 --no-pager 2>/dev/null
or tail -n 25 $root/.cache/tff/overnight/latest.log 2>/dev/null
