#!/usr/bin/env python3
"""Luna CLI — inspirado em Trae/Cursor: streaming, REPL, syntax highlight, multi-linha."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.CRITICAL)

try:
    from pygments import highlight
    from pygments.formatters import TerminalFormatter
    from pygments.lexers import guess_lexer

    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False


def _syntax_highlight(text: str) -> str:
    if not HAS_PYGMENTS:
        return text
    try:
        lexer = guess_lexer(text)
        return highlight(text, lexer, TerminalFormatter())
    except Exception:
        return text


def _stream_response(luna, query: str) -> str:
    full = ""
    for chunk in luna.process_stream(query):
        print(chunk, end="", flush=True)
        full += chunk
    print()
    return full


def _repl_mode(luna, verbose: bool = False):
    import readline
    from contextlib import suppress

    history_file = Path.home() / ".luna_history"
    with suppress(FileNotFoundError, OSError):
        readline.read_history_file(str(history_file))
    readline.set_history_length(100)

    print("Luna CLI — modo conversa. Digite /help para comandos, /exit para sair.")
    print()
    history = []
    while True:
        try:
            query = input("luna> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not query:
            continue
        if query == "/exit" or query == "/quit":
            break
        if query == "/help":
            print("Comandos:")
            print("  /exit, /quit   Sair")
            print("  /clear         Limpar tela")
            print("  /history       Mostrar histórico")
            print("  /verbose       Alternar modo verbose")
            print("  /help          Esta ajuda")
            print("  <texto>        Pergunta normal")
            continue
        if query == "/clear":
            print("\033[2J\033[H", end="")
            continue
        if query == "/history":
            for i, h in enumerate(history, 1):
                print(f"{i}: {h[:80]}{'...' if len(h) > 80 else ''}")
            continue
        if query == "/verbose":
            verbose = not verbose
            print(f"Verbose: {'on' if verbose else 'off'}")
            continue

        try:
            response = luna.process(query).strip()
        except Exception as e:
            print(f"Erro: {e}")
            continue

        if HAS_PYGMENTS:
            from pygments import highlight
            from pygments.formatters import TerminalFormatter
            from pygments.lexers import guess_lexer

            try:
                lexer = guess_lexer(response)
                print(highlight(response, lexer, TerminalFormatter()))
            except Exception:
                print(response)
        else:
            print(response)

        history.append(query)

    with suppress(OSError):
        readline.write_history_file(str(history_file))

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Luna CLI — assistente AI com modo conversa e streaming",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Modo conversa (REPL):
  luna                          Inicia modo conversa interativo
  luna --repl                   Inicia modo conversa interativo

Comandos do REPL:
  /exit, /quit                  Sair
  /clear                        Limpar tela
  /history                      Mostrar histórico
  /verbose                      Alternar modo verbose
  /help                         Mostrar ajuda

Exemplos:
  luna como eu crio uma pasta
  luna --repl
  luna --quiet que horas são
  luna --stream explique listas em Python
""",
    )
    parser.add_argument("query", nargs="*", help="Pergunta ou comando")
    parser.add_argument("--repl", "-r", action="store_true", help="Modo conversa interativo")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suprime mensagens de inicialização")
    parser.add_argument("--verbose", "-v", action="store_true", help="Mostra logs de debug")
    parser.add_argument("--stream", "-s", action="store_true", help="Streaming da resposta (experimental)")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    query = " ".join(args.query).strip()

    if not query and not args.repl:
        parser.print_help()
        sys.exit(1)

    if not args.quiet:
        print("Luna — assistente AI", file=sys.stderr)

    from luna_core import get_luna

    luna = get_luna()

    if args.repl or not query:
        _repl_mode(luna, verbose=args.verbose)
        return

    if args.stream:
        _stream_response(luna, query)
    else:
        response = luna.process(query).strip()
        if HAS_PYGMENTS:
            from pygments import highlight
            from pygments.formatters import TerminalFormatter
            from pygments.lexers import guess_lexer

            try:
                lexer = guess_lexer(response)
                print(highlight(response, lexer, TerminalFormatter()))
            except Exception:
                print(response)
        else:
            print(response)


if __name__ == "__main__":
    main()
