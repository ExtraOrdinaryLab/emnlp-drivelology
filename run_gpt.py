import os
import json

import pygsheets
import pandas as pd
import simplemind as sm
from dotenv import load_dotenv
from pydantic import BaseModel
from rich.console import Console

load_dotenv()
console = Console()

PROMPT_TEMPLATE = """
Classify the following text into ONE of seven categories. 
The first five are types of Drivelology (nonsense with underlying logic, irony, or conceptual twist). 
The last two are included for contrast:

Drivelology Categories:

 - Reverse Punchline: Subverts expectations by delivering a literal, technically correct, or backhanded response instead of a traditional punchline.
 - Figurative Literalism or Homophonic Pun: Takes figurative language, idioms, or homophones literally, generating comic or linguistic tension.
 - Cultural or Linguistic Switchbait: Plays on cultural or language-specific quirks to produce paradoxes, confusion, or humorous misinterpretation.
 - Inevitable Contradiction: Constructs statements that collapse under their own logic—self-defeating, recursive, or satirically paradoxical.
 - Semantic Misdirection: Builds toward depth or meaning, then veers suddenly into the mundane, anticlimactic, or unrelated.

Non-Drivelology Reference Categories:
 - Pure Nonsense: Syntactically correct but semantically meaningless; lacks any deeper logic or intent.
 - Normal Sentence: A clear, sensible statement with no twist, joke, or contradiction.

INPUT TEXT: {text}

Output format should be JSON with the following keys:
 - reason: A explanation of why the text belongs to the category.
 - category: The category the text belongs to, and it should be lowercase.
"""


class DrivelologyResponseModel(BaseModel):

    reason: str
    category: str


def main():
    save_file = 'gpt_4o_mini.tsv'
    service_file = 'drivelology-1b65510988e8.json'
    
    save_file = os.path.join('data', save_file)
    if not os.path.exists(save_file):
        os.makedirs('data', exist_ok=True)

    client = pygsheets.authorize(service_file=service_file)
    spreadsheets = client.open('drivelology')
    spreadsheet: pygsheets.Worksheet = spreadsheets.worksheet_by_title('Sheet1')
    worksheet: pygsheets.Worksheet = spreadsheet.get_all_records()
    worksheet_df = pd.DataFrame(worksheet)
    console.log(worksheet_df)

    exist_ids = set()
    with open(save_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        for line in lines:
            id, text, created_datetime, modified_datetime, reason, category = line.strip().split('\t')
            exist_ids.add(id)

    llm = sm.Session(
        llm_provider="openai", 
        llm_model="gpt-4o-mini", 
    )

    for index, row in worksheet_df.iterrows():
        id = row['id']
        text = row['text']
        text = text.replace('\n', ' ')
        created_datetime = row['created_datetime']
        modified_datetime = row['modified_datetime']

        if id in exist_ids:
            console.log(f"Skip {id}.")
            continue

        response = llm.generate_data(
            prompt=PROMPT_TEMPLATE.format(text=text),
            response_model=DrivelologyResponseModel,
        )

        console.log(f"ID: {id}")
        console.log(f"Text: {text}")
        console.log(response)
        console.log('-' * 100)

        response_json = response.model_dump()
        reason = response_json['reason']
        category = response_json['category']

        with open(save_file, 'a', encoding='utf-8') as f:
            f.write(f"{id}\t{text}\t{created_datetime}\t{modified_datetime}\t{reason}\t{category}\n")

        # break


if __name__ == '__main__':
    main()