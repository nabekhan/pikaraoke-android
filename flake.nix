{
  description = "PiKaraoke Android TV build and emulator tools";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/e8be7818e19ada32105a8af937a6a473b38167ca";
  outputs = { self, nixpkgs }: let
    systems = [ "aarch64-darwin" "x86_64-linux" ];
    each = nixpkgs.lib.genAttrs systems;
    tools = system: import ./tools.nix { pkgs = import nixpkgs { inherit system; config = { allowUnfree = true; android_sdk.accept_license = true; }; }; };
  in {
    devShells = each (system: { default = (tools system).shell; });
    packages = each (system: {
      sdk = (tools system).buildSdk.androidsdk;
      emulator = (tools system).android.androidsdk;
      tv-emulator = (tools system).tv.androidsdk;
    });
  };
}
