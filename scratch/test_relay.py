import sys
import os
import tinytuya

DEVICE_ID = "eb64a81b56fb8003dexqdd"
LOCAL_KEY  = "Ek&~Ah`=4s}5.'Z#"
IP_DEVICE  = "192.168.1.5"

print("Iniciando teste de relé com tinytuya...")
try:
    device = tinytuya.OutletDevice(
        dev_id=DEVICE_ID, address=IP_DEVICE, local_key=LOCAL_KEY, version=3.4
    )
    # Ativa debug
    
    print("Obtendo status atual...")
    status = device.status()
    print("Status retornado:", status)
    
    print("Enviando comando para DESLIGAR (False)...")
    res = device.set_status(False)
    print("Resposta ao desligar:", res)
    
    # Atualiza status
    print("Obtendo novo status...")
    status = device.status()
    print("Novo status:", status)
except Exception as e:
    print("Erro durante o teste:", e)
