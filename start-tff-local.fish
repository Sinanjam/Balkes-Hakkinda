#!/usr/bin/env fish
# Uzun TFF görevini terminal kapansa da yerel kullanıcı servisi olarak çalıştırır.
set -l root (realpath (dirname (status --current-filename)))
set -l unit balkes-tff-sync
set -l workers 10
set -l output generated/tff-data

if test -n "$argv[1]"
    set workers $argv[1]
end
if test -n "$argv[2]"
    set output $argv[2]
end

if not command -q systemd-run
    echo "systemd-run bulunamadı. Ön planda çalıştır:" >&2
    echo "fish sync-tff-until-clean.fish $workers $output" >&2
    exit 1
end
if systemctl --user is-active --quiet $unit
    echo "Görev zaten çalışıyor. Durum: fish status-tff-local.fish"
    exit 0
end

set -l fish_bin (command -s fish)
if test -z "$fish_bin"
    echo "fish bulunamadı." >&2
    exit 1
end
set -l joined_path (string join : $PATH)

systemd-run --user \
    --unit=$unit \
    --collect \
    --property=Type=exec \
    --property=Restart=no \
    --working-directory=$root \
    --setenv=PATH=$joined_path \
    $fish_bin $root/sync-tff-until-clean.fish $workers $output
or exit $status

echo "Yerel görev başladı. Terminali kapatabilirsin."
echo "Durum: fish status-tff-local.fish"
echo "Durdur: fish stop-tff-local.fish"

set -l linger (loginctl show-user $USER --property=Linger --value 2>/dev/null)
if test "$linger" != "yes"
    echo "Not: Bilgisayardan tamamen çıkış yapacaksan bir kez çalıştır:"
    echo "sudo loginctl enable-linger $USER"
end
