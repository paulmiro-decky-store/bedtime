{
  lib,
  stdenvNoCC,
  nodejs,
  pnpm,
  fetchPnpmDeps,
  pnpmConfigHook,
}:

stdenvNoCC.mkDerivation (finalAttrs: {
  pname = "decky-bedtime";
  version = (lib.importJSON ../package.json).version;

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../package.json
      ../pnpm-lock.yaml
      ../plugin.json
      ../rollup.config.js
      ../tsconfig.json
      ../main.py
      ../LICENSE
      ../src
      ../py_modules
    ];
  };

  nativeBuildInputs = [
    nodejs
    pnpm
    pnpmConfigHook
  ];

  pnpmDeps = fetchPnpmDeps {
    inherit (finalAttrs) pname version src;
    inherit pnpm;
    fetcherVersion = 5;
    hash = "sha256-4bpIej+6TUUwybfUyV8mZCUSF97lGKpNA/Od6j0hx+E=";
  };

  buildPhase = ''
    runHook preBuild
    pnpm run build
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p $out/dist
    cp dist/index.js $out/dist/
    cp -r main.py plugin.json package.json LICENSE py_modules $out/
    runHook postInstall
  '';

  meta = {
    description = "Decky Loader plugin: set an end-of-play time from your phone";
    license = lib.licenses.unlicense;
    platforms = lib.platforms.linux;
  };
})
