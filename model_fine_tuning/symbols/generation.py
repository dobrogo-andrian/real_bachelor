"""
Generate a synthetic slang dataset for fine-tuning experiments.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import pandas as pd


POS_EMOJIS = ["вќ¤пёЏ", "рџ”Ґ", "рџЌ", "рџҐ°", "рџ’Є", "рџ‡єрџ‡¦", "рџЋ‰", "рџ¤ќ", "рџ‘Џ", "рџ’Ї", "рџ«¶", "рџ’•", "рџ‚", "рџ‘Њ", "рџ‘Ќ"]
NEG_EMOJIS = ["рџ¤®", "рџ’©", "рџЎ", "рџ¤¬", "рџ¤¦вЂЌв™‚пёЏ", "рџ—‘пёЏ", "рџђЌ", "рџђ·", "рџ¤ў", "рџ‘Ћ", "рџ’", "рџ©", "рџ¤Ў", "рџ¤", "рџ "]
NEU_EMOJIS = ["рџ‘Ђ", "рџ¤”", "рџ¤·вЂЌв™‚пёЏ", "рџ¶", "рџ“Њ", "рџ‘‡", "рџ¤–", "в•", "рџ’…", "рџљ¶", "рџ“є", "рџ“»"]

BEGGING = ["рџ™Џ", "рџ­", "рџҐє", "рџ©"]
AESTHETIC = ["вњЁ", "рџЊё", "рџЋЂ", "рџ’–", "рџЊї", "вЃ", "вЂ", "рџЊ™", "в­ђ", "в™Ў", "в™Ґ", "вњї", "вќЂ", "рџЋ¶"]
EDGY = ["рџ”Є", "рџ”«", "рџ’Ј", "рџљ¬", "рџ’Љ", "в ", "рџ©ё", "рџ’‰", "рџ’ў"]
BOX_DRAWINGS = ["в–€", "в–“", "в–’", "в–‘", "в”Ѓ", "в•ђ", "в•‘", "в•­", "в•®", "в•Ї", "в•°", "в”ј", "в”ґ", "в”¬", "в”њ", "в”¤", "в”‚", "в”Ђ"]
WARNINGS = ["вљ ", "в›”", "рџљ«", "вќЊ", "вњ–", "вќ“", "вќ—", "вЂј", "вЃ‰"]

POS_SLANG = ["С–РјР±Р°", "Р±Р°Р·Р°", "С‚РѕРї", "based", "W", "РѕСЂСѓ", "Р»РѕР»", "super", "РєСЂР°СЃР°РІР°", "РґСЏРєСѓСЋ"]
NEG_SLANG = ["РєСЂРёРЅР¶", "С‚СЂРµС€", "РјРґР°", "Р¶Р°С…", "cringe", "L", "bruh", "РґРЅРѕ", "РєР°РїРµС†СЊ", "С€РѕРє"]

POS_SYMBOLS = [")))", "))", ":)", "^_^", "!!!", "++", "+", "!!!11"]
NEG_SYMBOLS = ["(((", "((", ":(", "-_-", "???", "??", "!!??", "-", "---", "?!?!"]
NEU_SYMBOLS = ["...", "..", "/", "+/-", "~", "///"]


def random_join(elements: list[str]) -> str:
    result = ""
    for element in elements:
        spaces = " " * random.choices([0, 1, 2], weights=[0.5, 0.4, 0.1])[0]
        result += element + spaces
    return result.strip()


def generate_standard(emojis: list[str], symbols: list[str] | None, slang_words: list[str] | None, min_len: int = 1, max_len: int = 4) -> str:
    components = random.choices(emojis, k=random.randint(min_len, max_len))
    if symbols and random.random() > 0.3:
        components.append(random.choice(symbols))
    if slang_words and random.random() > 0.7:
        components.append(random.choice(slang_words))
    random.shuffle(components)
    return random_join(components)


def generate_aesthetic() -> str:
    components = random.choices(AESTHETIC, k=random.randint(2, 5))
    if random.random() > 0.5:
        components.append(random.choice(["РІР°Сѓ", "РєСЂР°СЃР°", "cute", "aesthetic", "С‚РѕРї"]))
    return random_join(components)


def generate_edgy_sarcasm() -> str:
    components = random.choices(EDGY, k=random.randint(1, 3))
    components.append(random.choice(["РЅСѓ РґР°РІР°Р№", "РѕРє", "С‚РѕРї", "РїРѕР±Р°С‡РёРјРѕ", "РјРґР°"]))
    random.shuffle(components)
    return random_join(components)


def generate_begging() -> str:
    components = random.choices(BEGGING, k=random.randint(2, 4))
    if random.random() > 0.5:
        components.append(random.choice(["Р±СѓРґСЊ Р»Р°СЃРєР°", "РґР°Р№С‚Рµ", "С…РѕС‡Сѓ", "need"]))
    return random_join(components)


def generate_box_spam() -> str:
    return "".join(random.choices(BOX_DRAWINGS, k=random.randint(3, 10)))


def generate_encoding_error() -> str:
    err_str = "".join([""] * random.randint(1, 5))
    if random.random() > 0.5:
        return f"{random.choice(['С€Рѕ С†Рµ', '?', 'Р±Р°Рі', 'РЅРµ РїСЂР°С†СЋС”'])} {err_str}"
    return err_str


def generate_warning_spam() -> str:
    components = random.choices(WARNINGS, k=random.randint(2, 4))
    components.append(random.choice(NEG_SLANG))
    random.shuffle(components)
    return random_join(components)


def build_synthetic_dataset(seed: int = 42) -> pd.DataFrame:
    random.seed(seed)
    synthetic_rows: list[dict[str, str | int]] = []

    for _ in range(2000):
        synthetic_rows.append({"text": generate_standard(POS_EMOJIS, POS_SYMBOLS, POS_SLANG), "label": 2})
    for _ in range(750):
        synthetic_rows.append({"text": generate_aesthetic(), "label": 2})
    for _ in range(750):
        synthetic_rows.append({"text": generate_begging(), "label": 2})

    for _ in range(1500):
        synthetic_rows.append({"text": generate_standard(NEG_EMOJIS, NEG_SYMBOLS, NEG_SLANG), "label": 0})
    for _ in range(1000):
        synthetic_rows.append({"text": generate_edgy_sarcasm(), "label": 0})
    for _ in range(500):
        synthetic_rows.append({"text": generate_warning_spam(), "label": 0})
    for _ in range(500):
        synthetic_rows.append({"text": f"рџ¤Ў {generate_standard(POS_EMOJIS, [], [])}", "label": 0})

    for _ in range(1500):
        synthetic_rows.append({"text": generate_standard(NEU_EMOJIS, NEU_SYMBOLS, None), "label": 1})
    for _ in range(1000):
        synthetic_rows.append({"text": generate_box_spam(), "label": 1})
    for _ in range(500):
        synthetic_rows.append({"text": generate_encoding_error(), "label": 1})

    dataset_frame = pd.DataFrame(synthetic_rows)
    dataset_frame = dataset_frame[dataset_frame["text"].str.strip() != ""]
    dataset_frame = dataset_frame.drop_duplicates(subset=["text"])
    dataset_frame = dataset_frame.sample(frac=1, random_state=seed).reset_index(drop=True)
    return dataset_frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a synthetic slang dataset.")
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path(__file__).resolve().parent / "slang_data.csv",
        help="CSV path for the generated dataset.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible generation.")
    parser.add_argument("--sample-size", type=int, default=15, help="Number of preview rows to print.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Generating synthetic slang dataset...")
    dataset_frame = build_synthetic_dataset(seed=args.seed)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_frame.to_csv(args.output_path, index=False, encoding="utf-8")

    print(f"Successfully generated {len(dataset_frame)} unique rows.")
    print(f"Saved to: {args.output_path}")
    print("\nSample Data:")
    print(dataset_frame.sample(min(args.sample_size, len(dataset_frame)), random_state=args.seed))


if __name__ == "__main__":
    main()
