"""
joy_games.py — Lógica dos jogos do modo Luna Joy
Jogos: Damas, Xadrez, Jogo da Memória, Forca
A IA joga contra o usuário e conversa em tempo real.
"""
import random
import json
from typing import Optional

# ── Dificuldade ───────────────────────────────────────────────

DIFFICULTY_LEVELS = {
    "facil":  {"name": "Fácil",  "depth": 1, "random_chance": 0.5},
    "medio":  {"name": "Médio",  "depth": 2, "random_chance": 0.2},
    "dificil":{"name": "Difícil","depth": 3, "random_chance": 0.0},
}

# ── Damas ─────────────────────────────────────────────────────

class Damas:
    """
    Tabuleiro 8x8. Peças: 1=jogador, 2=Luna, 3=dama jogador, 4=dama Luna.
    """
    def __init__(self):
        self.board = self._init_board()
        self.turn = "player"  # "player" ou "luna"
        self.difficulty = "medio"
        self.winner = None

    def _init_board(self):
        b = [[0]*8 for _ in range(8)]
        for r in range(3):
            for c in range(8):
                if (r + c) % 2 == 1:
                    b[r][c] = 2  # Luna (topo)
        for r in range(5, 8):
            for c in range(8):
                if (r + c) % 2 == 1:
                    b[r][c] = 1  # Jogador (base)
        return b

    def get_state(self):
        return {
            "board": self.board,
            "turn": self.turn,
            "winner": self.winner,
            "difficulty": self.difficulty,
        }

    def _valid_moves(self, player: int):
        """Retorna lista de movimentos válidos: [(fr,fc,tr,tc,captured)]"""
        pieces = [1, 3] if player == 1 else [2, 4]
        moves = []
        captures = []
        for r in range(8):
            for c in range(8):
                if self.board[r][c] not in pieces:
                    continue
                is_king = self.board[r][c] in [3, 4]
                dirs = []
                if player == 1 or is_king:
                    dirs += [(-1, -1), (-1, 1)]
                if player == 2 or is_king:
                    dirs += [(1, -1), (1, 1)]
                for dr, dc in dirs:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < 8 and 0 <= nc < 8:
                        if self.board[nr][nc] == 0:
                            moves.append((r, c, nr, nc, None))
                        else:
                            opp = [2, 4] if player == 1 else [1, 3]
                            if self.board[nr][nc] in opp:
                                jr, jc = nr + dr, nc + dc
                                if 0 <= jr < 8 and 0 <= jc < 8 and self.board[jr][jc] == 0:
                                    captures.append((r, c, jr, jc, (nr, nc)))
        return captures if captures else moves

    def move(self, fr, fc, tr, tc) -> dict:
        """Executa movimento do jogador. Retorna resultado."""
        if self.winner:
            return {"ok": False, "msg": "Jogo encerrado."}
        if self.turn != "player":
            return {"ok": False, "msg": "Não é sua vez."}

        valid = self._valid_moves(1)
        match = [(m[0]==fr and m[1]==fc and m[2]==tr and m[3]==tc) for m in valid]
        if not any(match):
            return {"ok": False, "msg": "Movimento inválido."}

        mv = valid[next(i for i, x in enumerate(match) if x)]
        self._apply_move(mv, 1)
        self._check_winner()
        if not self.winner:
            self.turn = "luna"
        return {"ok": True, "state": self.get_state()}

    def _apply_move(self, mv, player):
        fr, fc, tr, tc, cap = mv
        piece = self.board[fr][fc]
        self.board[fr][fc] = 0
        # Promoção a dama
        if player == 1 and tr == 0:
            piece = 3
        elif player == 2 and tr == 7:
            piece = 4
        self.board[tr][tc] = piece
        if cap:
            self.board[cap[0]][cap[1]] = 0

    def _check_winner(self):
        p1 = any(self.board[r][c] in [1,3] for r in range(8) for c in range(8))
        p2 = any(self.board[r][c] in [2,4] for r in range(8) for c in range(8))
        if not p1:
            self.winner = "luna"
        elif not p2:
            self.winner = "player"
        elif not self._valid_moves(1):
            self.winner = "luna"
        elif not self._valid_moves(2):
            self.winner = "player"

    def luna_move(self) -> dict:
        """Luna faz sua jogada."""
        if self.winner or self.turn != "luna":
            return {"ok": False, "state": self.get_state()}

        moves = self._valid_moves(2)
        if not moves:
            self.winner = "player"
            return {"ok": True, "state": self.get_state()}

        diff = DIFFICULTY_LEVELS.get(self.difficulty, DIFFICULTY_LEVELS["medio"])
        # Chance de jogada aleatória (dificuldade fácil)
        if random.random() < diff["random_chance"]:
            mv = random.choice(moves)
        else:
            # Prefere capturas, depois movimentos para frente
            captures = [m for m in moves if m[4]]
            mv = random.choice(captures) if captures else random.choice(moves)

        self._apply_move(mv, 2)
        self._check_winner()
        self.turn = "player"
        return {"ok": True, "state": self.get_state(), "luna_move": mv[:4]}

    def set_difficulty(self, level: str):
        if level in DIFFICULTY_LEVELS:
            self.difficulty = level
            return True
        return False


# ── Xadrez (simplificado) ─────────────────────────────────────

CHESS_PIECES = {
    "wP": "♙", "wR": "♖", "wN": "♘", "wB": "♗", "wQ": "♕", "wK": "♔",
    "bP": "♟", "bR": "♜", "bN": "♞", "bB": "♝", "bQ": "♛", "bK": "♚",
}

INIT_CHESS = [
    ["bR","bN","bB","bQ","bK","bB","bN","bR"],
    ["bP","bP","bP","bP","bP","bP","bP","bP"],
    [None]*8, [None]*8, [None]*8, [None]*8,
    ["wP","wP","wP","wP","wP","wP","wP","wP"],
    ["wR","wN","wB","wQ","wK","wB","wN","wR"],
]

class Xadrez:
    def __init__(self):
        self.board = [row[:] for row in INIT_CHESS]
        self.turn = "player"   # player=brancas, luna=pretas
        self.difficulty = "medio"
        self.winner = None
        self.history = []

    def get_state(self):
        return {
            "board": self.board,
            "turn": self.turn,
            "winner": self.winner,
            "difficulty": self.difficulty,
        }

    def _color(self, piece):
        if not piece: return None
        return "w" if piece[0] == "w" else "b"

    def _valid_moves(self, color: str):
        moves = []
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if not p or self._color(p) != color:
                    continue
                moves += self._piece_moves(r, c, p, color)
        return moves

    def _piece_moves(self, r, c, piece, color):
        moves = []
        opp = "b" if color == "w" else "w"
        kind = piece[1]

        def add(nr, nc):
            if 0 <= nr < 8 and 0 <= nc < 8:
                t = self.board[nr][nc]
                if not t or self._color(t) == opp:
                    moves.append((r, c, nr, nc))
                    return t is None  # continua se vazio
            return False

        def slide(drs):
            for dr, dc in drs:
                nr, nc = r+dr, c+dc
                while 0 <= nr < 8 and 0 <= nc < 8:
                    t = self.board[nr][nc]
                    if t:
                        if self._color(t) == opp:
                            moves.append((r, c, nr, nc))
                        break
                    moves.append((r, c, nr, nc))
                    nr += dr; nc += dc

        if kind == "P":
            d = -1 if color == "w" else 1
            start = 6 if color == "w" else 1
            if 0 <= r+d < 8 and not self.board[r+d][c]:
                moves.append((r, c, r+d, c))
                if r == start and not self.board[r+2*d][c]:
                    moves.append((r, c, r+2*d, c))
            for dc in [-1, 1]:
                nr, nc = r+d, c+dc
                if 0 <= nr < 8 and 0 <= nc < 8 and self.board[nr][nc] and self._color(self.board[nr][nc]) == opp:
                    moves.append((r, c, nr, nc))
        elif kind == "R":
            slide([(0,1),(0,-1),(1,0),(-1,0)])
        elif kind == "B":
            slide([(1,1),(1,-1),(-1,1),(-1,-1)])
        elif kind == "Q":
            slide([(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)])
        elif kind == "N":
            for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
                add(r+dr, c+dc)
        elif kind == "K":
            for dr in [-1,0,1]:
                for dc in [-1,0,1]:
                    if dr or dc: add(r+dr, c+dc)
        return moves

    def move(self, fr, fc, tr, tc) -> dict:
        if self.winner:
            return {"ok": False, "msg": "Jogo encerrado."}
        if self.turn != "player":
            return {"ok": False, "msg": "Não é sua vez."}
        valid = self._valid_moves("w")
        if (fr, fc, tr, tc) not in valid:
            return {"ok": False, "msg": "Movimento inválido."}
        self._apply_move(fr, fc, tr, tc)
        self._check_winner()
        if not self.winner:
            self.turn = "luna"
        return {"ok": True, "state": self.get_state()}

    def _apply_move(self, fr, fc, tr, tc):
        piece = self.board[fr][fc]
        self.board[fr][fc] = None
        # Promoção de peão
        if piece == "wP" and tr == 0:
            piece = "wQ"
        elif piece == "bP" and tr == 7:
            piece = "bQ"
        self.board[tr][tc] = piece
        self.history.append((fr, fc, tr, tc))

    def _check_winner(self):
        wK = any(self.board[r][c] == "wK" for r in range(8) for c in range(8))
        bK = any(self.board[r][c] == "bK" for r in range(8) for c in range(8))
        if not wK:
            self.winner = "luna"
        elif not bK:
            self.winner = "player"

    def luna_move(self) -> dict:
        if self.winner or self.turn != "luna":
            return {"ok": False, "state": self.get_state()}
        moves = self._valid_moves("b")
        if not moves:
            self.winner = "player"
            return {"ok": True, "state": self.get_state()}

        diff = DIFFICULTY_LEVELS.get(self.difficulty, DIFFICULTY_LEVELS["medio"])
        if random.random() < diff["random_chance"]:
            mv = random.choice(moves)
        else:
            # Prefere capturas
            captures = [m for m in moves if self.board[m[2]][m[3]]]
            mv = random.choice(captures) if captures else random.choice(moves)

        self._apply_move(*mv)
        self._check_winner()
        self.turn = "player"
        return {"ok": True, "state": self.get_state(), "luna_move": mv}

    def set_difficulty(self, level: str):
        if level in DIFFICULTY_LEVELS:
            self.difficulty = level
            return True
        return False


# ── Forca ─────────────────────────────────────────────────────

WORDS_FORCA = [
    "abacaxi","borboleta","computador","diamante","elefante",
    "fantasia","girassol","horizonte","infinito","jornada",
    "kaleidoscopio","luminoso","maravilha","nebulosa","oceano",
    "papagaio","quilombo","relampago","saudade","tartaruga",
    "universo","ventania","xadrez","zumbido","aventura",
]

class Forca:
    def __init__(self):
        self.word = random.choice(WORDS_FORCA)
        self.guesses = set()
        self.max_errors = 6
        self.errors = 0
        self.winner = None

    def get_state(self):
        display = [c if c in self.guesses else "_" for c in self.word]
        return {
            "display": display,
            "guesses": sorted(self.guesses),
            "errors": self.errors,
            "max_errors": self.max_errors,
            "winner": self.winner,
        }

    def guess(self, letter: str) -> dict:
        if self.winner:
            return {"ok": False, "msg": "Jogo encerrado."}
        letter = letter.lower().strip()
        if len(letter) != 1 or not letter.isalpha():
            return {"ok": False, "msg": "Digite uma letra."}
        if letter in self.guesses:
            return {"ok": False, "msg": "Letra já tentada."}
        self.guesses.add(letter)
        if letter not in self.word:
            self.errors += 1
        if all(c in self.guesses for c in self.word):
            self.winner = "player"
        elif self.errors >= self.max_errors:
            self.winner = "luna"
        return {"ok": True, "state": self.get_state(), "hit": letter in self.word}


# ── Gerenciador de sessões Joy ────────────────────────────────

_sessions: dict[str, dict] = {}

def get_joy_session(session_id: str) -> dict:
    return _sessions.get(session_id, {})

def create_joy_session(session_id: str, game: str, difficulty: str = "medio") -> dict:
    if game == "damas":
        g = Damas()
    elif game == "xadrez":
        g = Xadrez()
    elif game == "forca":
        g = Forca()
    else:
        return {"error": f"Jogo '{game}' não disponível."}

    if hasattr(g, "set_difficulty"):
        g.set_difficulty(difficulty)

    _sessions[session_id] = {"game": game, "obj": g, "difficulty": difficulty}
    return {"ok": True, "game": game, "state": g.get_state()}

def joy_action(session_id: str, action: str, data: dict) -> dict:
    sess = _sessions.get(session_id)
    if not sess:
        return {"error": "Sessão não encontrada."}

    g = sess["obj"]

    if action == "move":
        result = g.move(data["fr"], data["fc"], data["tr"], data["tc"])
        if result.get("ok") and not result.get("state", {}).get("winner"):
            # Luna responde automaticamente
            luna_result = g.luna_move()
            result["luna_move"] = luna_result.get("luna_move")
            result["state"] = luna_result.get("state", result.get("state"))
        return result

    if action == "luna_move":
        return g.luna_move()

    if action == "guess":  # forca
        return g.guess(data.get("letter", ""))

    if action == "set_difficulty":
        level = data.get("level", "medio")
        ok = g.set_difficulty(level) if hasattr(g, "set_difficulty") else False
        sess["difficulty"] = level
        return {"ok": ok, "difficulty": level}

    if action == "state":
        return {"ok": True, "state": g.get_state()}

    if action == "reset":
        return create_joy_session(session_id, sess["game"], sess["difficulty"])

    return {"error": f"Ação '{action}' desconhecida."}

def list_games() -> list:
    return [
        {"id": "damas",  "name": "Damas",   "icon": "⚫", "desc": "Jogo de damas clássico 8x8"},
        {"id": "xadrez", "name": "Xadrez",  "icon": "♟",  "desc": "Xadrez completo contra a Luna"},
        {"id": "forca",  "name": "Forca",   "icon": "🎯", "desc": "Adivinhe a palavra letra por letra"},
    ]
