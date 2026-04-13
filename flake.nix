{
  description = "Unofficial API for TIDAL music streaming service.";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs = inputs @ {
    nixpkgs,
    flake-parts,
    ...
  }:
    flake-parts.lib.mkFlake {inherit inputs;} {
      systems = nixpkgs.lib.systems.flakeExposed;
      perSystem = {
        pkgs,
        ...
      }: let
        python = pkgs.python3;
        buildInputs =
          [
            python
          ]
          ++ (with pkgs; [
            # build / dev
            poetry
            ruff
          ]);
      in {
        devShells.default = pkgs.mkShell {
          packages = buildInputs;
          shellHook = ''
            [ ! -d .venv ] && python -m venv .venv
            source .venv/bin/activate
            poetry install --quiet 2>/dev/null
          '';
        };
      };
    };
}
