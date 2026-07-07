def increment_letter(char):
    """Increments an alphabet letter and wraps around if necessary."""

    # Check if the character is lowercase and alpha
    if ('a' <= char <= 'z') and (ord('a') <= ord(char) < ord('z')):
        return chr(ord(char) + 1)

    # Special case: Handle wrapping from 'z' back to 'a'
    elif char == 'z':
        return 'a' # Wrap around!

    # Check if the character is uppercase and alpha
    elif ('A' <= char <= 'Z') and (ord('A') <= ord(char) < ord('Z')):
        return chr(ord(char) + 1)

    # If it's not a valid alphabet in range, raise an error or return None
    else:
        return "Error: Not a single incrementable letter."


# Test cases
print("a" -> ", Result:", increment_letter('a'))   # Output: b
print("y" -> ", Result:", increment_letter('y'))   # Output: z
print("z" -> ", Result:", increment_letter('z'))   # Output: a (Wrapped!)
