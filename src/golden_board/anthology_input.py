"""Lean identity-checked retained anthology input, independent of rehearsal lessons."""
import hashlib,json
from .advanced_fixtures import qualified
from .qualified_inputs import current_document,presentation_source

def load_original_anthology(root):
    truth=qualified(root)
    report=json.loads((root/'evidence/S03-shared-anthology/actual-summary.json').read_bytes())
    for relative in ('src/golden_board/shared_anthology.py','src/golden_board/anthology_playback.py',
                     'src/golden_board/authoring.py','src/golden_board/document.py','viewer/player.mjs'):
        if hashlib.sha256(presentation_source(root,relative).read_bytes()).hexdigest()!=report['input_files'][relative]:
            raise ValueError('Inherited anthology presentation dependency changed: '+relative)
    body=(root/'evidence/S03-shared-anthology/actual-document.bin').read_bytes()
    if hashlib.sha256(body).hexdigest()!='c677a9e407854f2388831573ad2fd2296f2523a160f509e938dfbf409a3ba737':
        raise ValueError('Qualified anthology body changed.')
    return truth,body

def load_anthology(root):
    from .move_packing import pack_anthology
    truth,original=load_original_anthology(root)
    return truth,pack_anthology(current_document(original,'anthology'))
