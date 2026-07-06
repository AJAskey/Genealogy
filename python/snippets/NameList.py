# =============================
# 👩 List of 26 Female Names (A-Z)
# =============================

female_names = [
    "Amelia",  # A
    "Brianna",  # B
    "Chloe",  # C
    "Daisy",  # D
    "Eleanor",  # E
    "Fiona",  # F
    "Grace",  # G
    "Hannah",  # H
    "Isabella",  # I
    "Jessica",  # J
    "Kira",  # K
    "Leah",  # L
    "Maya",  # M
    "Nova",  # N
    "Olivia",  # O
    "Piper",  # P
    "Quinn",  # Q
    "Rachel",  # R
    "Savannah",  # S
    "Taylor",  # T
    "Ursula",  # U
    "Valerie",  # V
    "Willow",  # W
    "Xenobia",  # X (Used for completion)
    "Yvonne",  # Y
    "Zoe"  # Z
]

# =============================
# 👨 List of 26 Male Names (A-Z)
# =============================

male_names = [
    "Aiden",  # A
    "Benjamin",  # B
    "Caleb",  # C
    "Daniel",  # D
    "Ethan",  # E
    "Finn",  # F
    "Gabriel",  # G
    "Harrison",  # H
    "Isaac",  # I
    "Jackson",  # J
    "Kevin",  # K
    "Liam",  # L
    "Mason",  # M
    "Noah",  # N
    "Owen",  # O
    "Patrick",  # P
    "Quentin",  # Q
    "Ryder",  # R
    "Samuel",  # S
    "Theodore",  # T
    "Uriah",  # U
    "Vincent",  # V
    "Wyatt",  # W
    "Xavier",  # X
    "Yves",  # Y
    "Zachary"  # Z
]

femalePtr = 0
malePtr = 0


def getNextMale():
    global malePtr
    s = male_names[malePtr]
    malePtr += 1
    l = len(male_names)
    if malePtr >= l:
        malePtr = 0
    return s


def getNextFemale():
    global femalePtr
    s = female_names[femalePtr]
    femalePtr += 1
    l = len(female_names)
    if femalePtr >= l:
        femalePtr = 0
    return s


if __name__ == '__main__':
    for i in range(0, 36):
        print(getNextMale())
        print(getNextFemale())
