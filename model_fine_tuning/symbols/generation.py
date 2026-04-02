"""
03_generate_ultimate_synthetic_slang.py

V3 (Corrected): Incorporates obscure Unicode (Box Drawings, Dingbats, Specials).
Handles "Aesthetic" text, "Edgy" sarcasm, ASCII dividers, and Encoding Errors ().
Labels: 0 (Negative), 1 (Neutral), 2 (Positive)
"""

import random
import pandas as pd

# =====================================================================
# 1. EXPANDED VOCABULARY (Incorporating the 2015 Unicode Dump)
# =====================================================================

# Standard Emojis
POS_EMOJIS = ["❤️", "🔥", "😍", "🥰", "💪", "🇺🇦", "🎉", "🤝", "👏", "💯", "🫶", "💕", "😂", "👌", "👍"]
NEG_EMOJIS = ["🤮", "💩", "😡", "🤬", "🤦‍♂️", "🗑️", "🐍", "🐷", "🤢", "👎", "😒", "😩", "🤡", "😤", "😠"]
NEU_EMOJIS = ["👀", "🤔", "🤷‍♂️", "😶", "📌", "👇", "🤖", "☕", "💅", "🚶", "📺", "📻"]

# Modern Gen Z / Context-Dependent
GENZ_LAUGH = ["💀", "😭", "☠️", "😹", "🤣"] # Positive when combined
BEGGING    = ["🙏", "😭", "🥺", "😩"]       # "😭🙏" = Positive/Desperate need

# --- OBSCURE UNICODE CATEGORIES ---

# 1. "Aesthetic / Soft" Symbols (Highly Positive/Neutral)
AESTHETIC = ["✨", "🌸", "🎀", "💖", "🌿", "☁", "☀", "🌙", "⭐", "♡", "♥", "✿", "❀", "🎶"]

# 2. "Edgy / Threatening" Symbols (Used for Negative or Sarcasm)
EDGY = ["🔪", "🔫", "💣", "🚬", "💊", "☠", "🩸", "💉", "💢"]

# 3. Box Drawings & Dividers (Usually Neutral noise, or used in ASCII art)
BOX_DRAWINGS = ["█", "▓", "▒", "░", "━", "═", "║", "╭", "╮", "╯", "╰", "┼", "┴", "┬", "├", "┤", "│", "─"]

# 4. Weird Unicode / Warnings / Errors
WARNINGS = ["⚠", "⛔", "🚫", "❌", "✖", "❓", "❗", "‼", "⁉"]
ERRORS   = ["", "￼", "", ""] # The "Replacement Character" when a font breaks

# Slang Bridges
POS_SLANG = ["імба", "база", "топ", "based", "W", "ору", "лол", "super", "красава", "дякую"]
NEG_SLANG = ["кринж", "треш", "мда", "жах", "cringe", "L", "bruh", "дно", "капець", "шок"]

# SYMBOLS (Corrected: Added NEU_SYMBOLS)
POS_SYMBOLS = [")))", "))", ":)", "^_^", "!!!", "++", "+", "!!!11"]
NEG_SYMBOLS = ["(((", "((", ":(", "-_-", "???", "??", "!!??", "-", "---", "?!?!"]
NEU_SYMBOLS = ["...", "..", "/", "+/-", "~", "///"]


# =====================================================================
# 2. UTILITY FUNCTIONS
# =====================================================================

def random_join(elements):
    """Joins elements with random spacing (0 to 2 spaces)."""
    result = ""
    for el in elements:
        spaces = " " * random.choices([0, 1, 2], weights=[0.5, 0.4, 0.1])[0]
        result += el + spaces
    return result.strip()

# =====================================================================
# 3. ADVANCED GENERATOR RECIPES
# =====================================================================

def generate_standard(emojis, symbols, slang_words, min_len=1, max_len=4):
    components = random.choices(emojis, k=random.randint(min_len, max_len))
    if symbols and random.random() > 0.3: components.append(random.choice(symbols))
    if slang_words and random.random() > 0.7: components.append(random.choice(slang_words))
    random.shuffle(components)
    return random_join(components)

def generate_aesthetic():
    """Mixes ✨🌸☁ with positive slang -> POSITIVE"""
    components = random.choices(AESTHETIC, k=random.randint(2, 5))
    if random.random() > 0.5:
        components.append(random.choice(["вау", "краса", "cute", "aesthetic", "топ"]))
    return random_join(components)

def generate_edgy_sarcasm():
    """Mixes 🔪🔫💣 with positive/neutral slang -> NEGATIVE (Threatening/Sarcastic)"""
    components = random.choices(EDGY, k=random.randint(1, 3))
    components.append(random.choice(["ну давай", "ок", "топ", "побачимо", "мда"]))
    random.shuffle(components)
    return random_join(components)

def generate_begging():
    """Mixes 😭🙏😩 -> POSITIVE (I need this / This is so good)"""
    components = random.choices(BEGGING, k=random.randint(2, 4))
    if random.random() > 0.5:
        components.append(random.choice(["будь ласка", "дайте", "хочу", "need"]))
    return random_join(components)

def generate_box_spam():
    """Mixes ▓▒░ or ╭╮╯╰ -> NEUTRAL (ASCII art / Dividers / Spam)"""
    return "".join(random.choices(BOX_DRAWINGS, k=random.randint(3, 10)))

def generate_encoding_error():
    """Mixes  with confused/negative text -> NEGATIVE or NEUTRAL"""
    err_str = "".join([""] * random.randint(1, 5))
    if random.random() > 0.5:
        return f"{random.choice(['шо це', '?', 'баг', 'не працює'])} {err_str}"
    return err_str

def generate_warning_spam():
    """Mixes ⚠⛔❌ with negative slang -> NEGATIVE"""
    components = random.choices(WARNINGS, k=random.randint(2, 4))
    components.append(random.choice(NEG_SLANG))
    random.shuffle(components)
    return random_join(components)


# =====================================================================
# 4. BUILD THE DATASET
# =====================================================================

synthetic_data = []
print("Generating 10,000 rows of ULTIMATE synthetic slang...")

# --- 1. POSITIVE DATA (Label: 2) - ~3,500 rows ---
for _ in range(2000):
    synthetic_data.append({"text": generate_standard(POS_EMOJIS, POS_SYMBOLS, POS_SLANG), "label": 2})
for _ in range(750):
    synthetic_data.append({"text": generate_aesthetic(), "label": 2})
for _ in range(750):
    synthetic_data.append({"text": generate_begging(), "label": 2})

# --- 2. NEGATIVE DATA (Label: 0) - ~3,500 rows ---
for _ in range(1500):
    synthetic_data.append({"text": generate_standard(NEG_EMOJIS, NEG_SYMBOLS, NEG_SLANG), "label": 0})
for _ in range(1000):
    synthetic_data.append({"text": generate_edgy_sarcasm(), "label": 0})
for _ in range(500):
    synthetic_data.append({"text": generate_warning_spam(), "label": 0})
for _ in range(500):
    synthetic_data.append({"text": f"🤡 {generate_standard(POS_EMOJIS, [], [])}", "label": 0})

# --- 3. NEUTRAL DATA (Label: 1) - ~3,000 rows ---
for _ in range(1500):
    synthetic_data.append({"text": generate_standard(NEU_EMOJIS, NEU_SYMBOLS, None), "label": 1})
for _ in range(1000):
    synthetic_data.append({"text": generate_box_spam(), "label": 1})
for _ in range(500):
    synthetic_data.append({"text": generate_encoding_error(), "label": 1})


# =====================================================================
# 5. CLEAN, SHUFFLE, AND SAVE
# =====================================================================

df = pd.DataFrame(synthetic_data)

# Clean up
df = df[df["text"].str.strip() != ""]
df = df.drop_duplicates(subset=["text"])

# Shuffle thoroughly
df = df.sample(frac=1, random_state=42).reset_index(drop=True)

output_path = "slang_data.csv"
df.to_csv(output_path, index=False, encoding="utf-8")

print(f"✅ Successfully generated {len(df)} UNIQUE rows!")
print(f"✅ Saved to: {output_path}")
print("\nSample Data:")
print(df.sample(15))