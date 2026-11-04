def money(value) -> str:
    """Rupees with Indian digit grouping, e.g. 1234567 -> ₹12,34,567 (matches the storefront's en-IN formatting)."""
    number = int(round(float(value)))
    digits = str(abs(number))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"{'-' if number < 0 else ''}₹{digits}"
