{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:
let
  # pkgs-unstable = import inputs.nixpkgs-unstable { system = pkgs.stdenv.system; };
  # INFO: we take only major.minor, since devenv versions are a bit behind
  python_version = lib.versions.majorMinor (
    builtins.replaceStrings [ "\n" ] [ "" ] (builtins.readFile ./.python-version)
  );

in
{
  cachix.enable = true;
  # cachix.pull = [
  #   "cachix"
  #   "pre-commit-hooks"
  #   "nixpkgs-python"
  # ];

  packages = with pkgs; [
    git
  ];

  enterShell = ''
    git status
  '';

  # https://devenv.sh/tests/
  enterTest = ''
    echo "Running tests"
  '';
  languages.python = {
    enable = true;
    version = python_version;
    uv = {
      enable = true;
      sync.enable = true;
      sync.groups = [ "dev" ];
    };
    venv = {
      enable = true;
    };
    libraries = [
    ];
  };

}
