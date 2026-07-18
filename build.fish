#!/usr/bin/env fish
set -l root (dirname (status --current-filename))
cd $root

nix develop --command gradle --no-daemon :app:assembleDebug
or exit $status

set -l apk app/build/outputs/apk/debug/app-debug.apk
echo "APK hazır: $root/$apk"
