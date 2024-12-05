{ pkgs, lib, config, inputs, ... }:
let
  pkgs-unstable = import inputs.nixpkgs-unstable { system = pkgs.stdenv.system; };
in
{
  # https://devenv.sh/basics/
  env.GREET = "devenv";

  # https://devenv.sh/packages/
  packages = with pkgs-unstable; [
    git
    # pkgs.nodejs
    # pkgs.nodePackages.npm
    pyright
    ruff
    # XXX uses python 3.11 and wrong cattrs
    # pkgs.ruff-lsp
    # pkgs.nodePackages.cdk8s-cli
  ];

  # https://devenv.sh/scripts/
  scripts.hello.exec = "echo hello from $GREET";

  enterShell = ''
    hello
    git --version

    uv pip install -e ".[tests]" pdbpp
  '';

  # https://devenv.sh/tests/
  enterTest = ''
    echo "Running tests"
  '';

  # https://devenv.sh/services/
  # services.postgres.enable = true;

  # https://devenv.sh/languages/
  languages.python = {
    enable = true;
    version = "3.10";
    uv.enable = true;
    venv = {
      enable = true;
      # requirements = ./requirements.txt;
    };
  };
  # languages.javascript = {
  #  enable = true; # adds node LTS & npm
  #  corepack.enable = true;
  #  npm.install.enable = true;
  #  # package = pkgs.nodejs-18_x; # <- if you need to override npm version
  # };

  # https://devenv.sh/pre-commit-hooks/
  # pre-commit.hooks.shellcheck.enable = true;

  # https://devenv.sh/processes/
  # processes.ping.exec = "ping example.com";

  # See full reference at https://devenv.sh/reference/options/
}
