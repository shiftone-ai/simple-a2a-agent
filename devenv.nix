{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:

{
  # Python configuration
  languages.python = {
    enable = true;
    version = "3.12";
    uv = {
      enable = true;
      sync.enable = true;
    };
  };

  # Development packages
  packages = [
    # Linting & Formatting
    pkgs.ruff

    # Type checking
    pkgs.basedpyright

    # Formatting
    pkgs.nixfmt-rfc-style
    pkgs.treefmt
  ];

  # Pre-commit hooks
  pre-commit.hooks = {
    ruff.enable = true;
    ruff-format.enable = true;
    nixfmt-rfc-style.enable = true;
  };

  # Shell initialization
  enterShell = ''
    echo ""
    echo "Python Development Environment"
    echo "=============================="
    echo "Python: $(python --version)"
    echo "uv: $(uv --version)"
    echo ""
    echo "Tools:"
    echo "  ruff: $(ruff --version)"
    echo "  basedpyright: $(basedpyright --version)"
    echo ""
    echo "Commands:"
    echo "  uv sync          - Install dependencies"
    echo "  uv add <pkg>     - Add dependency"
    echo "  ruff check .     - Run linter"
    echo "  ruff format .    - Format code"
    echo "  basedpyright     - Type check"
    echo "  treefmt          - Format all files"
    echo ""
  '';
}
