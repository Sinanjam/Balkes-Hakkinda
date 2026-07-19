#!/usr/bin/env fish
set -l root (dirname (status --current-filename))
cd $root
or exit $status

set -l version_line (string match -r 'versionName "[^"]+"' < app/build.gradle | head -n 1)
set -l version (string replace -r 'versionName "([^"]+)"' '$1' $version_line)
if test -z "$version"; or string match -q '*-*' $version
    echo "Hata: app/build.gradle içinde kararlı bir versionName bulunamadı."
    exit 1
end

set -l release_dir $HOME/.config/balkes/release
set -l keystore $release_dir/balkes-release.p12
set -l credentials $release_dir/signing.fish
mkdir -p $release_dir
or exit $status
chmod 700 $release_dir
umask 077

if not test -f $keystore; or not test -f $credentials
    echo "İlk yayın anahtarı bu bilgisayarda hazırlanıyor..."
    set -l password_part_one (string replace -a '-' '' (string trim (cat /proc/sys/kernel/random/uuid)))
    set -l password_part_two (string replace -a '-' '' (string trim (cat /proc/sys/kernel/random/uuid)))
    set -l password "$password_part_one$password_part_two"
    nix develop --command keytool -genkeypair -noprompt \
        -keystore $keystore -storetype PKCS12 \
        -storepass $password -keypass $password \
        -alias balkes -keyalg RSA -keysize 4096 -validity 10000 \
        -dname "CN=Balkes, OU=Android, O=Balkes, L=Balikesir, C=TR"
    or exit $status

    printf 'set -gx BALKES_KEYSTORE %s\n' (string escape -- $keystore) > $credentials
    printf 'set -gx BALKES_STORE_PASSWORD %s\n' (string escape -- $password) >> $credentials
    printf 'set -gx BALKES_KEY_ALIAS balkes\n' >> $credentials
    printf 'set -gx BALKES_KEY_PASSWORD %s\n' (string escape -- $password) >> $credentials
    chmod 600 $keystore $credentials
end

source $credentials

echo "GitHub oturumu denetleniyor..."
nix develop --command gh auth status
or begin
    echo "GitHub oturumu yok. Bir kez 'gh auth login' çalıştırıp yeniden dene."
    exit 1
end

set -l tag v$version
if nix develop --command gh release view $tag --repo Sinanjam/Balkes-Hakkinda >/dev/null 2>&1
    echo "Hata: $tag sürümü GitHub'da zaten var; mevcut yayın değiştirilmedi."
    exit 1
end

echo "1/3 — İmzalı Balkes $version APK oluşturuluyor..."
nix develop --command gradle --no-daemon clean :app:assembleRelease
or exit $status

set -l built_apk app/build/outputs/apk/release/app-release.apk
if not test -f $built_apk
    echo "Hata: imzalı release APK bulunamadı."
    exit 1
end

echo "2/3 — APK imzası doğrulanıyor..."
nix develop --command apksigner verify --verbose $built_apk
or exit $status

set -l output_dir $root/local-releases/app
mkdir -p $output_dir
set -l output_apk $output_dir/Balkes-$version.apk
cp $built_apk $output_apk
or exit $status

echo "3/3 — GitHub Release yayımlanıyor..."
set -l notes "Kararlı son kullanıcı sürümü: sadeleştirilmiş ekranlar ve açılışta güncelleme kontrolü."
nix develop --command gh release create $tag $output_apk \
    --repo Sinanjam/Balkes-Hakkinda \
    --target main \
    --title "Balkes $version" \
    --notes $notes \
    --latest
or exit $status

echo ""
echo "YAYIN TAMAMLANDI: https://github.com/Sinanjam/Balkes-Hakkinda/releases/tag/$tag"
echo "Önemli: $release_dir klasörünü güvenli bir yere yedekle."
