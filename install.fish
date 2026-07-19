#!/usr/bin/env fish
set -l root (dirname (status --current-filename))
cd $root

set -l apk app/build/outputs/apk/debug/app-debug.apk
fish build.fish
or exit $status

nix develop --command adb install -r $apk
or exit $status

nix develop --command adb shell am force-stop com.sinanjam.balkesskor.dev
or exit $status
nix develop --command adb shell am start -n com.sinanjam.balkesskor.dev/com.sinanjam.balkesskor.MainActivity
or exit $status

echo "Balkes DEV kuruldu ve açıldı. Sürüm: 1.5.0-dev"
