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

PIECE_VALUES = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 100}

class Xadrez:
    def __init__(self):
        self.board = [row[:] for row in INIT_CHESS]
        self.turn = "player"
        self.difficulty = "medio"
        self.winner = None
        self.history = []
        self._check_state = {"check": False, "stalemate": False}
        self._kings_pos = {"w": (7, 4), "b": (0, 4)}  # track king positions
        self._castling = {"wK": True, "wQ": True, "bK": True, "bQ": True}
        self._en_passant = None

    def get_state(self):
        return {
            "board": self.board,
            "turn": self.turn,
            "winner": self.winner,
            "difficulty": self.difficulty,
            "check": self._is_check(self.turn_color()),
        }

    def turn_color(self):
        return "b" if self.turn == "luna" else "w"

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
        # Verifica se move não deixa próprio rei em xeque
        b2 = [row[:] for row in self.board]
        kpos = self._kings_pos.copy()
        piece = b2[fr][fc]
        b2[fr][fc] = None
        if piece[1] == "K":
            kpos["w"] = (tr, tc)
        b2[tr][tc] = piece
        if self._in_check("w", b2):
            return {"ok": False, "msg": "Movimento deixa seu rei em xeque!"}
        self._apply_move(fr, fc, tr, tc)
        self._check_winner()
        if not self.winner:
            self.turn = "luna"
        return {"ok": True, "state": self.get_state()}

    def _in_check(self, color, board=None):
        b = board or self.board
        king_pos = self._kings_pos[color]
        opp = "b" if color == "w" else "w"
        for r in range(8):
            for c in range(8):
                p = b[r][c]
                if p and p[0] == opp:
                    moves = self._piece_moves_raw(r, c, p)
                    if king_pos in moves:
                        return True
        return False

    def _is_check(self, color):
        return self._in_check(color)

    def _is_checkmate(self, color):
        if not self._in_check(color):
            return False
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p and p[0] == color:
                    for mv in self._piece_moves(r, c, p, color):
                        b2 = [row[:] for row in self.board]
                        # Apply move on copy
                        _, _, tr, tc = mv
                        captured = b2[tr][tc]
                        b2[tr][tc] = b2[r][c]
                        b2[r][c] = None
                        if p == "wK":
                            self._kings_pos["w"] = (tr, tc)
                        elif p == "bK":
                            self._kings_pos["b"] = (tr, tc)
                        if not self._in_check(color, b2):
                            # Restore
                            if p == "wK":
                                self._kings_pos["w"] = (r, c)
                            elif p == "bK":
                                self._kings_pos["b"] = (r, c)
                            return False
                        if p == "wK":
                            self._kings_pos["w"] = (r, c)
                        elif p == "bK":
                            self._kings_pos["b"] = (r, c)
        return True

    def _piece_moves_raw(self, r, c, piece, board=None):
        b = board or self.board
        kind = piece[1]
        color = piece[0]
        opp = "b" if color == "w" else "w"
        moves = []
        def add(nr, nc):
            if 0 <= nr < 8 and 0 <= nc < 8:
                t = b[nr][nc]
                if not t or t[0] == opp:
                    moves.append((nr, nc))
        def slide(drs):
            for dr, dc in drs:
                nr, nc = r+dr, c+dc
                while 0 <= nr < 8 and 0 <= nc < 8:
                    t = b[nr][nc]
                    if t:
                        if t[0] == opp:
                            moves.append((nr, nc))
                        break
                    moves.append((nr, nc))
                    nr += dr; nc += dc
        if kind == "P":
            d = -1 if color == "w" else 1
            if 0 <= r+d < 8 and not b[r+d][c]:
                moves.append((r+d, c))
            for dc in [-1, 1]:
                nr, nc = r+d, c+dc
                if 0 <= nr < 8 and 0 <= nc < 8 and b[nr][nc] and b[nr][nc][0] == opp:
                    moves.append((nr, nc))
        elif kind == "R": slide([(0,1),(0,-1),(1,0),(-1,0)])
        elif kind == "B": slide([(1,1),(1,-1),(-1,1),(-1,-1)])
        elif kind == "Q": slide([(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)])
        elif kind == "N":
            for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
                add(r+dr, c+dc)
        elif kind == "K":
            for dr in [-1,0,1]:
                for dc in [-1,0,1]:
                    if dr or dc: add(r+dr, c+dc)
        return moves

    def _apply_move(self, fr, fc, tr, tc):
        piece = self.board[fr][fc]
        color = piece[0]
        kind = piece[1]
        self.board[fr][fc] = None
        if kind == "K":
            self._kings_pos[color] = (tr, tc)
        if kind == "P" and tr in (0, 7):
            piece = color + "Q"
        self.board[tr][tc] = piece
        self.history.append((fr, fc, tr, tc))

    def _score_move(self, mv):
        _, _, tr, tc = mv
        target = self.board[tr][tc]
        score = 0
        if target:
            score += PIECE_VALUES.get(target[1], 1) * 10
        # Center control bonus
        if tr in (3, 4) and tc in (3, 4):
            score += 1
        # Randomize slightly
        return score + random.random() * 0.5

    def _check_winner(self):
        wK = any(self.board[r][c] == "wK" for r in range(8) for c in range(8))
        bK = any(self.board[r][c] == "bK" for r in range(8) for c in range(8))
        if not wK:
            self.winner = "luna"
        elif not bK:
            self.winner = "player"
        elif self._is_checkmate("w"):
            self.winner = "luna"
        elif self._is_checkmate("b"):
            self.winner = "player"
        elif self._is_check("w") or self._is_check("b"):
            pass  # game continues with check indication
        elif not any(self._valid_moves("w")) or not any(self._valid_moves("b")):
            self.winner = "draw"

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
            scored = [(self._score_move(m), m) for m in moves]
            scored.sort(key=lambda x: -x[0])
            mv = scored[0][1]

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

FORCA_HINTS = {
    "abacaxi": "Fruta tropical com coroa na cabeça",
    "borboleta": "Inseto colorido que transforma lagartas",
    "computador": "Máquina que processa dados",
    "diamante": "Pedra preciosa mais dura da natureza",
    "elefante": "Maior animal terrestre, tem tromba",
    "fantasia": "Imaginação ou roupa de personagem",
    "girassol": "Flor que sempre olha para o sol",
    "horizonte": "Linha onde o céu encontra a terra",
    "infinito": "Algo sem fim, símbolo ∞",
    "jornada": "Viagem longa ou caminho percorrido",
    "kaleidoscopio": "Tubo com espelhos que cria padrões coloridos",
    "luminoso": "Que emite ou reflete muita luz",
    "maravilha": "Algo extraordinário que causa admiração",
    "nebulosa": "Nuvem interestelar de poeira e gás",
    "oceano": "Grande extensão de água salgada",
    "papagaio": "Ave colorida que imita a voz humana",
    "quilombo": "Comunidade de escravos fugidos no Brasil colonial",
    "relampago": "Descarga elétrica visível durante tempestade",
    "saudade": "Sentimento de falta de alguém ou algo",
    "tartaruga": "Réptil lento com casco duro",
    "universo": "Conjunto de tudo que existe",
    "ventania": "Vento muito forte e duradouro",
    "xadrez": "Jogo de tabuleiro de estratégia",
    "zumbido": "Som contínuo e baixo, como de abelha",
    "aventura": "Experiência emocionante e arriscada",
}

class Forca:
    def __init__(self):
        self.word = random.choice(WORDS_FORCA)
        self.guesses = set()
        self.max_errors = 6
        self.errors = 0
        self.winner = None
        self.hint_used = False

    def get_hint(self) -> str:
        self.hint_used = True
        return FORCA_HINTS.get(self.word, "Sem dica disponível")

    def get_state(self):
        display = [c if c in self.guesses else "_" for c in self.word]
        return {
            "display": display,
            "guesses": sorted(self.guesses),
            "errors": self.errors,
            "max_errors": self.max_errors,
            "winner": self.winner,
            "hint": FORCA_HINTS.get(self.word, "") if self.errors >= 3 and not self.hint_used else "",
            "word_length": len(self.word),
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
        {"id": "damas",  "name": "Damas",   "icon": "checkers", "desc": "Jogo de damas clássico 8x8"},
        {"id": "xadrez", "name": "Xadrez",  "icon": "chess",   "desc": "Xadrez completo contra a Luna"},
        {"id": "forca",  "name": "Forca",   "icon": "target",  "desc": "Adivinhe a palavra letra por letra"},
    ]
