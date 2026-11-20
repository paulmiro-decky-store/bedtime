# NixOS module for Jovian-NixOS (https://github.com/Jovian-Experiments/Jovian-NixOS).
self:
{
  config,
  lib,
  pkgs,
  ...
}:

let
  inherit (lib)
    mkDefault
    mkEnableOption
    mkIf
    mkOption
    types
    ;
  decky = config.jovian.decky-loader;
  cfg = decky.bedtime;
  pluginDir = "${decky.stateDir}/plugins/decky-bedtime";
  configFile = pkgs.writeText "decky-bedtime-config.json" (
    builtins.toJSON { inherit (cfg) listenAddress port; }
  );
in
{
  options.jovian.decky-loader.bedtime = {
    enable = mkEnableOption "the Bedtime Decky plugin (end-of-play time set from a phone)";

    package = mkOption {
      type = types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.decky-bedtime;
      defaultText = lib.literalExpression "decky-bedtime.packages.\${system}.decky-bedtime";
      description = "The Bedtime plugin package.";
    };

    listenAddress = mkOption {
      type = types.nullOr types.str;
      default = null;
      example = "0.0.0.0";
      description = ''
        Address the web page listens on. When set, it is read-only in the
        plugin settings on the device. When `null`, it can be changed there
        (default `0.0.0.0`).
      '';
    };

    port = mkOption {
      type = types.nullOr types.port;
      default = null;
      example = 19114;
      description = ''
        Port of the web page. When set, it is read-only in the plugin settings
        on the device. When `null`, it can be changed there (default `19114`).
      '';
    };

    openFirewall = mkOption {
      type = types.bool;
      default = false;
      description = ''
        Open {option}`jovian.decky-loader.bedtime.port` in the firewall.
        Requires the port to be set here.
      '';
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion = decky.enable;
        message = "jovian.decky-loader.bedtime.enable requires jovian.decky-loader.enable.";
      }
      {
        assertion = cfg.openFirewall -> cfg.port != null;
        message = "jovian.decky-loader.bedtime.openFirewall requires jovian.decky-loader.bedtime.port to be set.";
      }
    ];

    jovian.decky-loader.enable = mkDefault true;

    environment.etc."decky-bedtime/config.json".source = configFile;

    networking.firewall.allowedTCPPorts = mkIf (cfg.openFirewall && cfg.port != null) [ cfg.port ];

    systemd.services.decky-loader = {
      # Install the plugin (Decky has no declarative plugin support). Runs after
      # Jovian's own preStart, which chowns the state dir to the plugin user.
      preStart = lib.mkAfter ''
        mkdir -p "${decky.stateDir}/plugins"
        rm -rf "${pluginDir}"
        cp -r --no-preserve=mode,ownership "${cfg.package}" "${pluginDir}"
      '';
      restartTriggers = [
        cfg.package
        configFile
      ];
    };
  };
}
