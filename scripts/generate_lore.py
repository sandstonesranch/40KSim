import json
from pathlib import Path

from datasets import load_dataset
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
MODEL = "llama3"

FACTIONS_TO_GENERATE = ["Adeptus Astartes", "Necrons", "Orks", "Aeldari", "Tyranids"]
OUTPUT_FILE = Path(__file__).resolve().parents[1] / "data-schema/factions/faction_metadata.json"


def get_llm_summary(faction_name, raw_text):
    """Uses an LLM to summarize the raw lore into a playstyle and lore blurb."""
    prompt = f"""
    You are a Warhammer 40k expert. Read the following text about the {faction_name}.
    Write a 2-sentence summary of their lore, and a 1-sentence summary of their general playstyle.
    Return ONLY valid JSON with keys 'lore' and 'playstyle'.

    Text: {raw_text[:4000]}
    """

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def main():
    print("Loading dataset...")
    ds = load_dataset("vizn3r/warhammer40k-lore", split="train")

    metadata = {}

    for faction in FACTIONS_TO_GENERATE:
        print(f"Searching for {faction}...")
        matches = [row["text"] for row in ds if faction.lower() in row["text"].lower()]

        if not matches:
            print(f"No lore found for {faction}.")
            continue

        combined_text = " ".join(matches[:5])

        print(f"Generating summary for {faction}...")
        summary = get_llm_summary(faction, combined_text)

        slug = faction.lower().replace(" ", "-")
        metadata[slug] = {
            "lore": summary.get("lore", ""),
            "playstyle": summary.get("playstyle", ""),
            "subfactions": {},
        }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Saved metadata to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
