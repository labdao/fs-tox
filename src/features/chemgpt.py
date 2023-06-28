import torch
import transformers
transformers.logging.set_verbosity_error()  # Set transformers log level to ERROR

import logging
import pandas as pd
import click
import duckdb


def chemgpt_encode(smiles):
    tokenizer = transformers.AutoTokenizer.from_pretrained("ncfrey/ChemGPT-4.7M")
    model = transformers.AutoModel.from_pretrained("ncfrey/ChemGPT-4.7M")

    # Adding a padding token
    tokenizer.add_special_tokens({"pad_token": "[PAD]"})

    # Encode the SMILES string
    inputs = tokenizer(smiles, return_tensors="pt", padding=True, truncation=True)

    # Feed the inputs to the model
    with torch.no_grad():  # disable gradient calculations to save memory
        outputs = model(**inputs)

    # Output is a tuple, where the first item are the hidden states
    hidden_states = outputs[0]

    # Take the average of the hidden states for each token of the SMILES string
    average_embeddings = torch.mean(hidden_states, dim=1)

    return average_embeddings


def generate(input_filepath, output_filepath):

    log_fmt = "%(asctime)s - %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_fmt)

    logger = logging.getLogger(__name__)
    logger.info("creating embeddings from smiles...")

    # Connect to a database in memory
    connection = duckdb.connect(database=":memory:")

    # Load the data into the database as list of tuples
    smiles = connection.execute(
        f"""
    SELECT DISTINCT canonical_smiles
    FROM '{input_filepath}/*.parquet'
    """
    ).fetchall()

    # Convert list of tuples to list of strings
    smiles_list = [x[0] for x in smiles]

    # Get the embeddings for each SMILES string
    embeddings = chemgpt_encode(smiles_list)

    # Convert tensor to list of lists (each sub-list is an embedding)
    embeddings_list = embeddings.numpy().tolist()

    # Create column names
    embedding_names = [
        "embedding_" + str(i + 1) for i in range(len(embeddings_list[0]))
    ]

    # Convert list of embeddings to DataFrame where each element of the list becomes a separate column
    embeddings_df = pd.DataFrame(embeddings_list, columns=embedding_names)

    # # Add the SMILES strings to the DataFrame
    embeddings_df["canonical_smiles"] = smiles_list

    # Rearrange the columns so that 'smiles' column comes first
    embeddings_df = embeddings_df[
        ["canonical_smiles"] + [col for col in embeddings_df.columns if col != "canonical_smiles"]
    ]
    
    # Add a column with the representation name
    embeddings_df['representation'] = 'chemgpt'

    # Save the dataframe as a parquet file
    embeddings_df.to_parquet(f"{output_filepath}/chemgpt.parquet")
    
    logger.info("saved embeddings to %s", output_filepath)