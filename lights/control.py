#!/usr/bin/env python3
import tinytuya

DEVICE_ID = "eb64a81b56fb8003dexqdd"
LOCAL_KEY = "Ek&~Ah`=4s}5.'Z#"
IP_DEVICE = "192.168.1.5"

def main():
    device = tinytuya.OutletDevice(
        dev_id=DEVICE_ID,
        address=IP_DEVICE,
        local_key=LOCAL_KEY,
        version=3.4
    )

    print("Controle de Luz - Luna")
    print("Comandos: liga, desliga, sair")

    while True:
        cmd = input("\n> ").strip().lower()

        if cmd == "liga":
            device.set_status(True)
            print("Luz ligada")

        elif cmd == "desliga":
            device.set_status(False)
            print("Luz desligada")

        elif cmd == "sair":
            break

if __name__ == "__main__":
    main()