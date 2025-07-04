from stdnum import iso7064


def cleanup_reference(text: str) -> str:
    """Converts text to uppercase and removes all non-alphanumeric characters."""
    text = text.upper()
    return "".join(char for char in text if char.isalnum())


def letter_to_number(text: str) -> str:
    """Converts letters in a string to their corresponding numerical values (A=10, B=11, etc.)."""

    def convert_letter(char: str) -> str:
        if char.isalpha():
            return str(ord(char) - ord("A") + 10)
        elif char.isdigit():
            return char
        else:
            return ""

    return "".join(convert_letter(char) for char in text)


def generate_invoice_reference(invoice_number: str) -> str:
    """Generates a structured RF creditor reference from an invoice number."""
    clean_reference = cleanup_reference(invoice_number)
    raw_reference = f"{clean_reference}RF"
    as_number = letter_to_number(raw_reference)
    check_digits = iso7064.mod_97_10.calc_check_digits(as_number)
    return f"RF{check_digits}{clean_reference}"
