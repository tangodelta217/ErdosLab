# Setup local: Lean, Lake, Elan

This repo requires Lean 4 (lean), Lake, and Elan.

## Linux/macOS

1) Install elan:
   curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y
2) Restart your shell (or `source ~/.profile`).
3) Install the stable toolchain:
   elan toolchain install stable
   elan default stable
4) Verify:
   elan --version
   lake --version
   lean --version

## Windows

1) Download and run the elan installer from:
   https://github.com/leanprover/elan
2) Open a new terminal.
3) Install the stable toolchain:
   elan toolchain install stable
   elan default stable
4) Verify:
   elan --version
   lake --version
   lean --version
