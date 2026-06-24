# =============================
# 👩 List of 26 Female Names (A-Z)
# =============================

female_names = [
    "Anjel",  # A
    "Brianna",  # B
    "Chloe",  # C
    "Donna",  # D
    "Eleanor",  # E
    "Fiona",  # F
    "Gabbie",  # G
    "Haley",  # H
    "Isabella",  # I
    "Jessica",  # J
    "Kelly",  # K
    "Leah",  # L
    "Megan",  # M
    "Nova",  # N
    "Olivia",  # O
    "Piper",  # P
    "Quinn",  # Q
    "Rachel",  # R
    "Sarah",  # S
    "Tonie",  # T
    "Ursula",  # U
    "Valerie",  # V
    "Willow",  # W
    "Xena",  # X (Used for completion)
    "Yvonne",  # Y
    "Zoe"  # Z
]

# =============================
# 👨 List of 26 Male Names (A-Z)
# =============================

male_names = [
    "Andrew",  # A
    "Benjamin",  # B
    "Caleb",  # C
    "Daniel",  # D
    "Ethan",  # E
    "Finn",  # F
    "Gabriel",  # G
    "Harrison",  # H
    "Isaac",  # I
    "Jerome",  # J
    "Ken",  # K
    "Liam",  # L
    "Mason",  # M
    "Noah",  # N
    "Owen",  # O
    "Patrick",  # P
    "Quentin",  # Q
    "Rodney",  # R
    "Samuel",  # S
    "Theodore",  # T
    "Uriah",  # U
    "Vincent",  # V
    "Wyatt",  # W
    "Xavier",  # X
    "Yves",  # Y
    "Zachary"  # Z
]

surnames = [
    'Johnson', 'McDonald', 'Stewart', 'Miller', 'Lucas', 'Taylor', 'Nichols', 'Askin', 'Barr', 'Garcia'
]

malePtr = 0
femalePtr = 0
surnamePtr = 0


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


def getNextSurname():
    global surnamePtr
    s = surnames[surnamePtr]
    surnamePtr += 1
    l = len(surnames)
    if surnamePtr >= l:
        surnamePtr = 0
    return s


if __name__ == '__main__':
    surnamePtr = 0
    femalePtr = 0
    malePtr = 0

    for i in range(0, 36):
        print(f"{getNextMale()} {getNextFemale()} {getNextSurname()}")
