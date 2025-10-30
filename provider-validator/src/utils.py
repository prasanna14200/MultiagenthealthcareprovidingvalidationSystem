# src/utils.py
from Levenshtein import ratio
import phonenumbers

def fuzzy_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    try:
        return ratio(str(a).lower(), str(b).lower())
    except:
        return 0.0

def normalize_phone(phone: str, default_region="US"):
    if not phone:
        return None
    try:
        pn = phonenumbers.parse(phone, default_region)
        if phonenumbers.is_valid_number(pn):
            return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
        else:
            return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except:
        return phone

def score_combined(name_score: float, phone_score: float, address_score: float) -> float:
    # element weights: name 0.4, phone 0.3, address 0.3
    return 0.4 * name_score + 0.3 * phone_score + 0.3 * address_score
