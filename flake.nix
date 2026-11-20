{
  description = "Bedtime: a Decky Loader plugin to set an end-of-play time from your phone";

  inputs.nixpkgs.url = "https://channels.nixos.org/nixos-unstable/nixexprs.tar.xz";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: rec {
        decky-bedtime = pkgs.callPackage ./nix/package.nix { };
        default = decky-bedtime;
      });

      overlays.default = final: _prev: {
        decky-bedtime = final.callPackage ./nix/package.nix { };
      };

      nixosModules = rec {
        decky-bedtime = import ./nix/module.nix self;
        default = decky-bedtime;
      };

      checks = forAllSystems (
        pkgs:
        {
          package = self.packages.${pkgs.stdenv.hostPlatform.system}.decky-bedtime;
          python-tests =
            pkgs.runCommand "decky-bedtime-python-tests"
              {
                nativeBuildInputs = [ (pkgs.python3.withPackages (ps: [ ps.aiohttp ])) ];
              }
              ''
                cp -r ${./main.py} main.py
                cp -r ${./py_modules} py_modules
                cp -r ${./tests} tests
                chmod -R u+w .
                python3 -m unittest discover -s tests -v
                touch $out
              '';
        }
      );

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            pkgs.nodejs
            pkgs.pnpm
            (pkgs.python3.withPackages (ps: [ ps.aiohttp ]))
          ];
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
