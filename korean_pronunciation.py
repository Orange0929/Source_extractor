"""Context-aware Korean pronunciation, with no runtime downloads or pip calls."""
from functools import lru_cache
from pathlib import Path
import re
import tempfile
import threading
import unicodedata
import zipfile

_lock = threading.RLock()
_engine = None


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            import cmudict
            import nltk
            from mecab import MeCab

            # g2pk2 checks for an NLTK corpus at import time. Supply the corpus
            # from the installed wheel instead of downloading on first search.
            with tempfile.TemporaryDirectory(prefix="source-extractor-g2p-") as temp:
                corpus = Path(temp) / "corpora"
                corpus.mkdir()
                entries = "\n".join(
                    f"{word.upper()} 1 {' '.join(phones)}"
                    for word, phones in cmudict.entries()
                )
                with zipfile.ZipFile(corpus / "cmudict.zip", "w") as archive:
                    archive.writestr("cmudict/cmudict", entries)
                nltk.data.path.insert(0, temp)
                try:
                    from g2pk2 import G2p

                    class OfflineG2p(G2p):
                        def check_mecab(self):
                            # Dependencies are installed by the app installer.
                            pass

                        def get_mecab(self):
                            # This wheel supports Windows too; avoid eunjeon
                            # and upstream's implicit subprocess pip installer.
                            return MeCab()

                    _engine = OfflineG2p()
                finally:
                    nltk.data.path.remove(temp)
        return _engine


@lru_cache(maxsize=16384)
def pronounce(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    if not re.search("[가-힣]", text):
        return text
    # Preserve spaces and punctuation for morphology. Keep Latin input intact:
    # continuous search interprets it as romanized phones, not English words.
    with _lock:
        engine = _get_engine()
        return re.sub(r"[가-힣]+(?:[ \t]+[가-힣]+)*",
                      lambda m: engine(m.group(), descriptive=False), text)
