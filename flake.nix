{
  description = "numlang — stack-based esoteric language that compiles to C";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

  # Provides Python + setuptools for both local development and
  # CI — no system-level Python install needed.

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system}; in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python3
              python3Packages.pip
              python3Packages.virtualenv
              python3Packages.setuptools
            ];

            shellHook = ''
              echo "numlang dev shell ready (Python 3 + setuptools)"
            '';
          };
        }
      );

      formatter = forAllSystems (pkgs: pkgs.nixfmt-rfc-style);
    };
}
