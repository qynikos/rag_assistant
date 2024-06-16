import os
from dotenv import load_dotenv
import logging
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import AzureOpenAI
from sentence_transformers import SentenceTransformer
import kdbai_client as kdbai

load_dotenv()

# logging config
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Azure OpenAI client
endpoint = os.getenv("AZURE_ENDPOINT")
api_key = os.getenv("AZURE_OPENAI_API_KEY")
deployment = os.getenv("MODEL_DEPLOYMENT_NAME")

if not api_key or not deployment:
    logger.error("API key or deployment name is missing")
    raise ValueError("API key or deployment name is missing")

# Initialize KDB.AI connection
KDBAI_ENDPOINT = os.getenv("KDBAI_ENDPOINT")
KDBAI_API_KEY = os.getenv("KDBAI_API_KEY")

if not KDBAI_ENDPOINT or not KDBAI_API_KEY:
    logger.error("KDB.AI endpoint or API key is missing")
    raise ValueError("KDB.AI endpoint or API key is missing")

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

client = AzureOpenAI(
    api_key=api_key,
    api_version="2024-02-01",
    azure_endpoint=endpoint
)
logger.info("Azure OpenAI client initialized successfully")

# Lookup KDB.AI vector DB for documents related to query
def search_vector_db(query):
    try:
        session = kdbai.Session(api_key=KDBAI_API_KEY, endpoint=KDBAI_ENDPOINT)
        table = session.table("pwc_pdf")
        # Init embedding model
        model = SentenceTransformer("all-MiniLM-L6-v2")
        encoded_query = model.encode(query).tolist()
        results = table.search([encoded_query], n=1)
        df = pd.DataFrame(results[0])
        # Get the content of the 'sentences' column in the top row
        top_sentence = df.loc[0, 'sentences']
        # Convert the top sentence to a string
        logger.info(f"Search vector DB successful for query: {query}")
        return str(top_sentence)
    except Exception as e:
        logger.error(f"Error searching vector DB: {e}")
        raise

# Mock retrieval function
def mock_retrieval(query):
    try:
        # Return a fixed set of strings + results from VectorDB as a mock retrieval response
        fixed_passages = [
            "Climate change refers to long-term shifts in temperatures and weather patterns.",
            "These shifts may be natural, such as through variations in the solar cycle.",
            "PwC is part of the Big 4.",
            "Andreas is leading PwC's AI team.",
            "PwC will have a new hub in Volos, located at K.Kartali 1"
        ]
        # Get results from vector database
        vector_db_passages = search_vector_db(query)
        # Combine both sets of results
        fixed_passages.append(vector_db_passages)
        logger.info(f"Mock retrieval successful for query: {query}")
        return fixed_passages
    except Exception as e:
        logger.error(f"Error in mock retrieval: {e}")
        raise


# Route for the REST API
@app.route('/ask', methods=['POST'])
def ask():
    try:
        data = request.json
        query = data.get('query', '')

        logger.info(f"Received query: {query}")

        # Get mock retrieval passages
        passages = mock_retrieval(query)

        # Construct the input for the generative model
        messages = [
            {"role": "system", "content": "You are an AI assistant. Answer the user's question using the following information."},
            {"role": "user", "content": query},
        ]
        for passage in passages:
            messages.append({"role": "system", "content": passage})

        # Generate response
        completion = client.chat.completions.create(
            model=deployment,
            messages=messages
        )

        # Extract and return the response
        response_content = completion.choices[0].message.content
        logger.info(f"Generated response for query: {query}")
        return jsonify({'response': response_content})

    except Exception as e:
        logger.error(f"Error handling request: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
