#!/usr/bin/env fish

set -l repo "Sinanjam/Balkes-Hakkinda"

if not type -q nix
    echo "HATA: nix komutu bulunamadı."
    exit 1
end

echo "GitHub oturumu denetleniyor..."
nix develop --command gh auth status
or exit 1

echo "GitHub Pages etkinleştiriliyor..."
nix develop --command gh api --method POST "repos/$repo/pages" -f build_type=workflow >/dev/null 2>&1
set -l create_status $status

if test $create_status -ne 0
    nix develop --command gh api "repos/$repo/pages" >/dev/null 2>&1
    or begin
        echo "HATA: Pages etkinleştirilemedi. GitHub hesabının depoda yönetici yetkisi olduğundan emin ol."
        exit 1
    end
    nix develop --command gh api --method PUT "repos/$repo/pages" -f build_type=workflow >/dev/null
    or exit 1
end

echo "Yayın iş akışı başlatılıyor..."
nix develop --command gh workflow run pages.yml --repo $repo
or exit 1

set -l run_id ""
for attempt in (seq 1 15)
    set run_id (nix develop --command gh run list --repo $repo --workflow pages.yml --limit 1 --json databaseId --jq '.[0].databaseId')
    if test -n "$run_id"
        break
    end
    sleep 2
end

if test -z "$run_id"
    echo "Pages etkin; iş akışı kimliği henüz görünmedi. Bir dakika sonra GitHub Actions sayfasını kontrol et."
    exit 0
end

echo "Yayın izleniyor (çalışma: $run_id)..."
nix develop --command gh run watch $run_id --repo $repo --exit-status
or exit 1

echo ""
echo "TAMAM: https://sinanjam.github.io/Balkes-Hakkinda/"
