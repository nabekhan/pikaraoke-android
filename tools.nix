{ pkgs ? import <nixpkgs> { config = { allowUnfree = true; android_sdk.accept_license = true; }; } }:
let
  originalRepo = builtins.fromJSON (builtins.readFile "${pkgs.path}/pkgs/development/mobile/androidenv/repo.json");
  buildSdk = pkgs.androidenv.composeAndroidPackages {
    # GeckoView 158 requires 37.2, newer than the pinned Nixpkgs SDK catalog.
    repo = originalRepo // { packages = originalRepo.packages // {
      platforms = originalRepo.packages.platforms // {
        "37.2" = builtins.fromJSON (builtins.readFile ./nix/android-platform-37.2.json);
      };
    }; };
    platformVersions = [ "37.2" ];
    buildToolsVersions = [ "36.0.0" ];
    includeCmake = true;
    cmakeVersions = [ "3.22.1" ];
    includeNDK = true;
    ndkVersions = [ "28.2.13676358" ];
  };
  android = pkgs.androidenv.composeAndroidPackages {
    platformVersions = [ "35" ];
    buildToolsVersions = [ "35.0.0" ];
    includeEmulator = true;
    includeSystemImages = true;
    systemImageTypes = [ "google_apis" ];
    abiVersions = [ "arm64-v8a" ];
    includeCmake = false;
    includeNDK = false;
  };
in {
  inherit android buildSdk;
  tv = pkgs.androidenv.composeAndroidPackages {
    platformVersions = [ "34" ];
    buildToolsVersions = [ "35.0.0" ];
    includeEmulator = true;
    includeSystemImages = true;
    systemImageTypes = [ "android-tv" ];
    abiVersions = [ "arm64-v8a" ];
    includeCmake = false;
    includeNDK = false;
  };
  shell = pkgs.mkShell {
    packages = [ pkgs.jdk17 pkgs.gradle_9 (pkgs.python311.withPackages (p: [ p.babel p.pytest ])) pkgs.ffmpeg pkgs.git pkgs.gh buildSdk.androidsdk ];
    JAVA_HOME = "${pkgs.jdk17.home}";
    ANDROID_HOME = "${buildSdk.androidsdk}/libexec/android-sdk";
    ANDROID_SDK_ROOT = "${buildSdk.androidsdk}/libexec/android-sdk";
  };
}
