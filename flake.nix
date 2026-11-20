{
  description = "Bedtime: a Decky Loader plugin to set an end-of-play time from your phone";

  inputs = {
    nixpkgs.url = "https://channels.nixos.org/nixos-unstable/nixexprs.tar.xz";
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } (
      { withSystem, ... }:
      {
        systems = [
          "x86_64-linux"
          "aarch64-linux"
        ];

        perSystem =
          { config, pkgs, ... }:
          let
            python = pkgs.python3.withPackages (ps: [ ps.aiohttp ]);
          in
          {
            packages = {
              decky-bedtime = pkgs.callPackage ./nix/package.nix { };
              default = config.packages.decky-bedtime;
            };

            checks = {
              package = config.packages.decky-bedtime;
              python-tests =
                pkgs.runCommand "decky-bedtime-python-tests" { nativeBuildInputs = [ python ]; }
                  ''
                    cp ${./main.py} main.py
                    cp -r ${./py_modules} py_modules
                    cp -r ${./tests} tests
                    chmod -R u+w .
                    python3 -m unittest discover -s tests -v
                    touch $out
                  '';
            };

            devShells.default = pkgs.mkShell {
              packages = [
                pkgs.nodejs
                pkgs.pnpm
                python
              ];
            };

            formatter = pkgs.nixfmt;
          };

        flake.nixosModules = rec {
          decky-bedtime = flake-parts.lib.importApply ./nix/module.nix { inherit withSystem; };
          default = decky-bedtime;
        };
      }
    );
}
