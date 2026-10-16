"""Script d'interrupteur de panne pour le mock reseau (lancement manuel).

Utilisation :
  python tests/infrastructure/network/toggle_network_failure.py down    # active la panne
  python tests/infrastructure/network/toggle_network_failure.py up      # retablit le service
  python tests/infrastructure/network/toggle_network_failure.py status  # affiche le statut
"""

import argparse
import os

FLAG_FILE = ".fake_network_down"


def set_down() -> None:
    """Active la panne simulee."""
    with open(FLAG_FILE, "w", encoding="utf-8") as f:
        f.write("down")
    print("[-] Service reseau simule : EN PANNE (upstream_unavailable)")


def set_up() -> None:
    """Retablit le service."""
    if os.path.exists(FLAG_FILE):
        os.remove(FLAG_FILE)
    print("[+] Service reseau simule : OPERATIONNEL (disponible)")


def status() -> None:
    """Affiche l'etat actuel du service."""
    if os.path.exists(FLAG_FILE):
        print("[-] Statut actuel : EN PANNE (.fake_network_down actif)")
    else:
        print("[+] Statut actuel : OPERATIONNEL")


def main() -> None:
    parser = argparse.ArgumentParser(description="Interrupteur de panne pour FakeNetwork")
    parser.add_argument("action", choices=["down", "up", "status"], help="Action a executer")
    args = parser.parse_args()
    if args.action == "down":
        set_down()
    elif args.action == "up":
        set_up()
    elif args.action == "status":
        status()


if __name__ == "__main__":
    main()
