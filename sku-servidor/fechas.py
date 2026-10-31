"""Formato de presentación; las fechas persistidas y los filtros siguen en ISO."""
import re

def display_date(value):
 return re.sub(r"(?<![0-9])([0-9]{4})-([0-9]{2})-([0-9]{2})(?:T([0-9]{2}:[0-9]{2}(?::[0-9]{2})?)(?:[.][0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?(?![0-9])",lambda m:m[3]+"/"+m[2]+"/"+m[1]+(" "+m[4] if m[4] else ""),str(value))

def iso_date(value):
 import datetime
 s=str(value or '')
 if s and (not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",s) or datetime.date.fromisoformat(s).isoformat()!=s):raise ValueError('Fecha inválida; usa dd/mm/yyyy en la pantalla.')
 return s
