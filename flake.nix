{
  description = "Balkes birleşik Android/Java geliştirme ortamı";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config = {
              allowUnfree = true;
              android_sdk.accept_license = true;
            };
          };
          android = pkgs.androidenv.composeAndroidPackages {
            platformVersions = [ "34" "35" ];
            buildToolsVersions = [ "34.0.0" "35.0.0" ];
            includeEmulator = false;
            includeNDK = false;
            includeSystemImages = false;
          };
          sdk = android.androidsdk;
        in {
          default = pkgs.mkShell {
            packages = [
              (pkgs.python3.withPackages (pythonPackages: with pythonPackages; [
                beautifulsoup4
                lxml
                requests
              ]))
              pkgs.jdk17
              pkgs.gradle
              pkgs.git
              pkgs.jq
              pkgs.zip
              pkgs.unzip
              sdk
            ];

            ANDROID_HOME = "${sdk}/libexec/android-sdk";
            ANDROID_SDK_ROOT = "${sdk}/libexec/android-sdk";
            JAVA_HOME = "${pkgs.jdk17}";
            GRADLE_OPTS = "-Dorg.gradle.project.android.aapt2FromMavenOverride=${sdk}/libexec/android-sdk/build-tools/35.0.0/aapt2";

            shellHook = ''
              export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/build-tools/35.0.0:$ANDROID_HOME/build-tools/34.0.0:$PATH"
              echo "Balkes ortamı hazır. Build: fish build.fish | TFF: fish sync-tff.fish"
            '';
          };
        });
    };
}
