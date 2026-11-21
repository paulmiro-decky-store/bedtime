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
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      perSystem =
        { config, pkgs, ... }:
        let
          pythonFor = py: py.withPackages (ps: [ ps.aiohttp ]);
          python = pythonFor pkgs.python3;
          # Backend tests, run against the Python Decky uses on a given system.
          pythonTests =
            py:
            pkgs.runCommand "decky-bedtime-python-tests-${py.version}"
              { nativeBuildInputs = [ (pythonFor py) ]; }
              ''
                cp ${./main.py} main.py
                cp -r ${./py_modules} py_modules
                cp -r ${./tests} tests
                chmod -R u+w .
                python3 -m unittest discover -s tests -v
                touch $out
              '';
        in
        {
          packages = {
            decky-bedtime = pkgs.callPackage ./nix/package.nix { };
            default = config.packages.decky-bedtime;
          };

          checks = {
            package = config.packages.decky-bedtime;
            python-tests = pythonTests pkgs.python3;
            # NixOS 25.11's python3, the oldest one Jovian users may have.
            python313-tests = pythonTests pkgs.python313;
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
    };
}
