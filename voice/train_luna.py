#!/usr/bin/env python3
"""
Treina o modelo openwakeword para 'luna' usando TTS sintético.
Executar uma única vez:  .venv/bin/python voice/train_luna.py
"""
import sys
from pathlib import Path

OUT_MODEL  = Path(__file__).parent / "luna_wakeword.onnx"
TRAIN_DIR  = Path(__file__).parent / "luna_training"

def main():
    try:
        import openwakeword
    except ImportError:
        print("ERRO: openwakeword não instalado.")
        print("Execute:  .venv/bin/pip install openwakeword")
        sys.exit(1)

    from openwakeword.utils import download_models
    print("[Treino] Baixando modelos base (feature extraction)...")
    download_models()

    try:
        from openwakeword import train
        print("[Treino] Gerando amostras TTS para 'luna'...")
        train.generate_training_data(
            positive_phrases=["luna"],
            output_dir=str(TRAIN_DIR),
            n_samples=1500,
            generate_false_positive_samples=True,
        )
        print("[Treino] Treinando modelo ONNX (~5min)...")
        train.train(
            training_data_dir=str(TRAIN_DIR),
            output_model_path=str(OUT_MODEL),
            n_epochs=40,
        )
        print(f"[Treino] ✓ Modelo salvo em: {OUT_MODEL}")
    except AttributeError:
        # API alternativa para versões mais novas do openwakeword
        print("[Treino] Tentando API alternativa...")
        _train_alternative()

def _train_alternative():
    """Tenta usar a API de treinamento da versão mais recente."""
    from openwakeword import MODELS_BASE_DIR
    print("[Treino] Usando API manual de treinamento...")

    # Gera amostras TTS usando pyttsx3 ou espeak
    TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    pos_dir = TRAIN_DIR / "positive"
    neg_dir = TRAIN_DIR / "negative"
    pos_dir.mkdir(exist_ok=True)
    neg_dir.mkdir(exist_ok=True)

    # Gera amostras positivas com espeak
    import subprocess, wave, struct, random
    variants = ["luna", "Luna", "LUNA", "lúna"]
    for i, word in enumerate(variants * 50):
        out = str(pos_dir / f"luna_{i:04d}.wav")
        subprocess.run(
            ["espeak-ng", "-v", "pt-br", "-s", str(random.randint(120, 180)),
             "-a", str(random.randint(80, 150)), "-w", out, word],
            capture_output=True,
        )
    print(f"[Treino] ✓ {len(list(pos_dir.glob('*.wav')))} amostras positivas geradas.")
    print("[Treino] ⚠ Treino automático incompleto — verifique a documentação do openwakeword.")

if __name__ == "__main__":
    main()
