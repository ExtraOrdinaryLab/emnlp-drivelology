import os
import json
from typing import Type, TypeVar
from functools import cached_property

import pygsheets
import instructor
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel
from rich.console import Console
from simplemind.providers.openai import OpenAI

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

T = TypeVar("T", bound=BaseModel)


class DrivelologyResponseModel(BaseModel):

    reason: str
    category: str


class OpenRouter(OpenAI):

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    @cached_property
    def client(self):
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        try:
            import openai as oa
        except ImportError as exc:
            raise ImportError(
                "Please install the `openai` package: `pip install openai`"
            ) from exc
        return oa.OpenAI(
            api_key=self.api_key, 
            base_url="https://openrouter.ai/api/v1"
        )

    def generate_text(
        self,
        prompt: str,
        *,
        llm_model: str | None = None,
        **kwargs,
    ):
        """Generate text using the OpenAI API."""
        messages = [
            {"role": "user", "content": [{"type": "text", "text": prompt}]},
        ]

        response = self.client.chat.completions.create(
            messages=messages,
            model=llm_model or self.DEFAULT_MODEL,
            **{**self.DEFAULT_KWARGS, **kwargs},
        )
        return response.choices[0].message.content
    
    @cached_property
    def structured_client(self) -> instructor.Instructor:
        """A client patched with Instructor."""
        return instructor.from_openai(
            self.client,
            mode=instructor.Mode.JSON,
        )
    
    def structured_response(
        self,
        prompt: str,
        response_model: Type[T],
        *,
        llm_model: str | None = None,
        **kwargs,
    ) -> T:
        """Get a structured response from the OpenAI API."""
        # Ensure messages are provided in kwargs
        messages = [
            {"role": "user", "content": prompt},
        ]

        response = self.structured_client.chat.completions.create(
            messages=messages,
            model=llm_model or self.DEFAULT_MODEL,
            response_model=response_model,
            **{**self.DEFAULT_KWARGS, **kwargs},
        )
        return response_model.model_validate(response)
    
    def generate_data(
        self, 
        prompt: str,
        *,
        llm_model: str | None = None,
        llm_provider: str | None = None,
        response_model: Type[BaseModel],
        **kwargs,
    ) -> BaseModel:
        """Generate structured data using the session's default provider and model."""
        return self.structured_response(
            prompt=prompt,
            llm_model=llm_model,
            response_model=response_model,
            **kwargs,
        )


def main():
    save_file = 'deepseek_v3.tsv'
    llm_model = 'deepseek/deepseek-chat-v3-0324:free'
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
    if os.path.exists(save_file):
        with open(save_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines:
                id, text, created_datetime, modified_datetime, reason, category = line.strip().split('\t')
                exist_ids.add(id)

    llm = OpenRouter(
        api_key=os.getenv('OPENROUTER_API_KEY')
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
            llm_model=llm_model, 
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