"""The keys a menu level is picked with, shared by every front end and by
the playtest's menu check: 1-9, then letters, minus the ones that always
mean something else (b back, h history, j journal, l load, q quit, s save,
u unwind). A level can show at most len(KEYS) entries."""

RESERVED = 'bhjlqsu'
KEYS = '123456789' + ''.join(c for c in 'abcdefghijklmnopqrstuvwxyz' if c not in RESERVED)
