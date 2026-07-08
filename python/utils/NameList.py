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
    "Natalie",  # N
    "Olivia",  # O
    "Piper",  # P
    "Quinn",  # Q
    "Rachel",  # R
    "Samantha",  # S
    "Tonie",  # T
    "Ursula",  # U
    "Valerie",  # V
    "Willow",  # W
    "Xena",  # X 
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
    "Krzysztof ",  # K
    "Liam",  # L
    "Mateo ",  # M
    "Noah",  # N
    "Owen",  # O
    "Paul",  # P
    "Quentin",  # Q
    "Rodney",  # R
    "Samuel",  # S
    "Tommaso",  # T
    "Uriah",  # U
    "Vincent",  # V
    "Wyatt",  # W
    "Xavier",  # X
    "Yves",  # Y
    "Zachary"  # Z
]
surnames = ["Smith   ",
            "Johnson ",
            "Williams ",
            "Brown ",
            "Jones ",
            "Miller ",
            "Davis ",
            "Martin ",
            "Anderson ",
            "Wilson",
            "Thomas",
            "Moore",
            "Taylor",
            "Lucas",
            "Martin",
            "Clark",
            "Walker,",
            "Clark",
            "Wright",
            "Flanagan",
            "Allen",
            "Hill",
            "Green",
            "Baker",
            "Evans",
            "Phillips",
            "Parker",
            "Turner",
            "Wells",
            "Stewart",
            "Cook",
            "Gracia",
            "Cooper",
            "Morgan",
            "Kelly",
            "Foster"]

import random


def getNextMale():
    ln = len(male_names) - 1
    ptr = random.randint(0, ln)
    s = male_names[ptr]
    return s


def getNextFemale():
    ln = len(female_names) - 1
    ptr = random.randint(0, ln)
    s = female_names[ptr]
    return s


def getNextSurname():
    ln = len(surnames) - 1
    ptr = random.randint(0, ln)
    s = surnames[ptr]
    return s


if __name__ == '__main__':

    for i in range(0, 36):
        print(f"{getNextMale()} {getNextFemale()} {getNextSurname()}")
