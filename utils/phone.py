import re


def normalize_phone(value: str) -> str:
    phone = re.sub(r"[\s()-]", "", value or "")
    if phone.startswith("+86"):
        phone = phone[3:]
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise ValueError("请输入有效的 11 位中国大陆手机号")
    return phone
