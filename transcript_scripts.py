"""Deterministic written-script filters, independent of Whisper's language guess."""
import unicodedata
from functools import lru_cache

@lru_cache(maxsize=8192)
def scripts(text):
    found=set()
    for ch in unicodedata.normalize('NFKC',text):
        if not unicodedata.category(ch).startswith('L'):continue
        n=ord(ch)
        if (0xAC00<=n<=0xD7AF or 0x1100<=n<=0x11FF or 0x3130<=n<=0x318F or
            0xA960<=n<=0xA97F or 0xD7B0<=n<=0xD7FF):found.add('ko')
        elif (0x3040<=n<=0x30FF or 0x31F0<=n<=0x31FF or n in (0x3005,0x3006,0x3007,0x303B) or
              0x3400<=n<=0x4DBF or 0x4E00<=n<=0x9FFF or 0xF900<=n<=0xFAFF or
              0x20000<=n<=0x323AF):found.add('ja')
        elif 'a'<=ch<='z' or 'A'<=ch<='Z':found.add('en')
        elif unicodedata.category(ch).startswith('L'):found.add('other')
    return frozenset(found)


def parse_exclusions(value):
    result={part.strip() for part in (value or '').split(',') if part.strip()}
    if result-{'ko','ja','en','other'}:raise ValueError('잘못된 언어 제외 필터입니다.')
    return result


def filter_clips(clips, exclusions):
    return [clip for clip in clips if not scripts(clip.get('transcript') or '').intersection(exclusions)]
