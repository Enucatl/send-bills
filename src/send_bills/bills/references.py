from stdnum import iso7064


def cleanup_reference(text: str) -> str:
    """Converts text to uppercase and removes all non-alphanumeric characters.

    This function is typically used to sanitize input strings for use in
    reference numbers, ensuring they only contain characters suitable for
    numerical conversion and checksum calculation.

    Args:
        text: The input string to clean up.

    Returns:
        A new string containing only uppercase alphanumeric characters from the
        original input.
    """
    text = text.upper()
    return "".join(char for char in text if char.isalnum())


def letter_to_number(text: str) -> str:
    """Converts letters in a string to their corresponding numerical values.

    Letters A-Z are converted to 10-35, respectively. Digits remain unchanged.
    Non-alphanumeric characters are removed. This conversion is part of the
    ISO 7064 Mod 97-10 algorithm for IBAN and other reference number generation.

    Args:
        text: The input string containing letters and/or digits.

    Returns:
        A string where letters are replaced by their two-digit numerical values
        and digits are preserved.
    """

    def convert_letter(char: str) -> str:
        """Helper function to convert a single character."""
        if "A" <= char <= "Z":  # Check for uppercase letters
            return str(ord(char) - ord("A") + 10)
        elif char.isdigit():
            return char
        else:
            # For any non-alphanumeric character, return an empty string to effectively remove it
            return ""

    return "".join(convert_letter(char) for char in text)


def generate_invoice_reference(invoice_number: str) -> str:
    """Generates a structured RF creditor reference from an invoice number.

    This function implements the ISO 7064 Mod 97-10 algorithm to create a
    compliant RF (Creditor Reference) standard reference number.
    It involves cleaning the input, appending "RF", converting to numbers,
    calculating checksum digits, and formatting the final string.

    Args:
        invoice_number: The base invoice number or identifier. This can be
            any string that will be cleaned and used as the core of the reference.

    Returns:
        A string formatted as "RFxx[cleaned_invoice_number]", where 'xx' are
        the two Mod 97-10 checksum digits.
    """
    clean_reference = cleanup_reference(invoice_number)
    # The "RF" is appended to the *end* of the invoice_number for checksum calculation
    # as per ISO 7064
    raw_reference = f"{clean_reference}RF"
    as_number = letter_to_number(raw_reference)
    check_digits = iso7064.mod_97_10.calc_check_digits(as_number)
    return f"RF{check_digits}{clean_reference}"
