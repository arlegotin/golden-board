"""Exact retained-source prefixes and explicit authored exercise continuations.

The tails are exercises, never additions to anthology records or evidence of an
unspecified historical result cause. No source SAN qualification is repeated.
"""
import gzip,json,hashlib
from functools import lru_cache
from .anthology_playback import validated_game_truth
from .rules import Replay

QUEEN_TAIL=('a2c4 f4e5 c4d5 e5d5 h5g4 g7f6 g4h5 f6h8 h5h6 h8g7 '
 'h6g7 d5e5 g7f7 e5f5 f7f8 f5g4 f8e7 g4h4 e7f6 h4h3 g6g7 h3h2 '
 'g7g8q h2h1 g8h8 h1g1 f6f5 g1f1 f5f4 f1g1 f4f3 g1f1 h8h4 f1g1')
ROOK_TAIL=('b3a2 h3h4 a4b6 h4h6 b6d5 h6d6 d5f6 d6f6 '
 'a2a1 d4c3 a1b1 f6h6 b1a1 h6h2 a1b1')

@lru_cache(maxsize=4)
def qualified(root):
    raw=(root/'evidence/S04-rules/actual-source.json.gz').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='6ec81cc1b1c810baf45c3e48efb5116e4a67bd67738a790a494d2ab9a56f7ba7':
        raise ValueError('Qualified source evidence changed.')
    truth=json.loads(gzip.decompress(raw))['source_qualification']
    validated_game_truth(root,truth)
    return truth

def source_prefix(root,ordinal,plies=None):
    game=qualified(root)['games'][str(ordinal)]
    moves=game['moves']
    def square(cell):return chr(97+cell%8)+str(8-cell//8)
    texts=[square(a)+square(b)+('', 'q','r','b','n')[p] for a,b,p in moves]
    return ' '.join(texts if plies is None else texts[:plies])

def fixtures(root):
    q=source_prefix(root,49)+' '+QUEEN_TAIL
    result={'queen':q,'queen_practice':q+' h4e4 g1h1 e4f4 h1g1',
        'rook':source_prefix(root,45)+' '+ROOK_TAIL,
        'pawn':source_prefix(root,49)+' '+' '.join(QUEEN_TAIL.split()[:18]),
        'historical_race':source_prefix(root,49,120)}
    return result

def fixture_provenance(root):
    result={}
    for name,text in fixtures(root).items():
        ordinal=45 if name=='rook' else 49
        count=120 if name=='historical_race' else len(source_prefix(root,ordinal).split())
        replay=Replay()
        for move in text.split():replay.play(move)
        result[name]={'source_ordinal':ordinal,'source_plies':count,
            'authored_tail':text.split()[count:],'plies':len(replay.moves),'fen':replay.fen,
            'repetition':replay.repetition_count,'available_claims':list(replay.available_claims),
            'scope':'Standard-start legal exercise history; source score does not imply a closure cause.'}
    return result
