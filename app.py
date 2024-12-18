from flask import Flask, render_template, request, jsonify
import os
import warnings
from langchain_groq import ChatGroq
from langchain.chains import LLMChain, create_retrieval_chain
import pandas as pd
from langchain_openai import ChatOpenAI  # Use ChatOpenAI for chat models
from langchain_experimental.agents import create_pandas_dataframe_agent
from translate import Translator
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

# Suppress warnings
warnings.filterwarnings("ignore", message=".*clean_up_tokenization_spaces.*")


open_api_key = os.getenv("OPENAI_API_KEY")
STATIC_PDF_FOLDER = "uploads"



# Global variables
index = None
query_chain = None
chat_history = []
language_code={
    "language":'english',
    "code": "en"

}

# Helper function for translations
def translate_text(text, target_language):
    translator = Translator(to_lang=target_language)
    return translator.translate(text)



# Home route
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/start-chat')
def start_chat():
    load_status = True  # Load documents on startup
    username = request.args.get('username', 'Guest')
    language = request.args.get('language', 'English')
    language_code["language"]=language

    print(language)

    # Language code mapping
    language_codes = {
        "spanish": "es",
        "german": "de",
        "hindi": "hi",
        "french": "fr",
        "English": "en"
    }
    target_code = language_codes.get(language, "en")

    language_code["code"]=target_code
    print(target_code)
    # Translate the welcome message
    welcome_message = "How can I help you?"
    
    welcome_message = translate_text(welcome_message, target_code)

    print(f"Translated welcome message: {welcome_message}")

    return render_template('chat_bot.html', username=username, language=language, load_status=load_status, code=target_code, welcome_message=welcome_message)

# ------------------------------
from langchain_groq import ChatGroq

# Enhanced System Prompt
SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer questions concisely and directly based on the data provided. "
    "Do not repeat the question in the answer. Use the following specific guidelines:\n"
    "- For comparisons, provide summarized key differences.\n"
    "- For queries involving ratings, stock, or price, include precise values from the data.\n"
    "- For complex queries, dynamically calculate the required result (e.g., averages, totals, or ratios).\n"
    "- If grouping is required, identify the grouping and aggregation columns and summarize the grouped data.\n"
    "- If a question cannot be answered using the data, inform the user to ask a valid question.\n"
    "- Use examples such as:\n"
    "    * Compare the average rating and price of smartphones and laptops.\n"
    "    * Find the cheapest product in stock with a rating above 4.0.\n"
    "    * List products with a rating above 4.5 and priced under $500, grouped by category.\n"
    "    * Which product had the highest sales in the last 12 months?\n"
    "    * Identify the best-value products, calculated as (Rating * StockQuantity) / Price.\n"
)



def process_question(question):
    try:
        # Initialize the OpenAI client
        llm = ChatOpenAI(model="gpt-3.5-turbo", openai_api_key=open_api_key)

        # Load a single CSV file as a DataFrame
        df = pd.read_csv('data.csv')  # Replace with the actual path to your CSV file

        # Create Pandas DataFrame Agent for CSV data
        pandas_agent = create_pandas_dataframe_agent(
            llm,
            df,
            allow_dangerous_code=True,
            handle_parsing_errors=True,
            verbose=True
        )

        # Combine system prompt and question
        combined_question = f"{SYSTEM_PROMPT}\n\n{question}"

        # Helper function to process grouping queries in the DataFrame agent
        def handle_grouping_query(dataframe, question):
            try:
                # Extract grouping column and aggregation column
                if "group by" in question.lower():
                    parts = question.lower().split("group by")
                    agg_col = parts[0].strip().split(" ")[-1]  # Column to aggregate
                    group_col = parts[1].strip()  # Column to group by

                    # Check if columns exist
                    if group_col not in dataframe.columns:
                        return f"Error: Column '{group_col}' not found in DataFrame."
                    if agg_col not in dataframe.columns:
                        return f"Error: Column '{agg_col}' not found in DataFrame."

                    # Perform grouping and aggregation
                    grouped_data = dataframe.groupby(group_col).agg({agg_col: 'sum'}).reset_index()
                    return grouped_data.to_dict(orient='records')
            except Exception as e:
                return f"An error occurred with grouping: {e}"

        # Route the query to the appropriate handler
        if "group by" in question.lower():
            # Handle grouping queries
            response = handle_grouping_query(df, question)
        else:
            # Use DataFrame agent for general data queries
            response = pandas_agent.run(question)

        # Check if the response is N/A
        if response == "N/A":
            response = "Please ask a valid question."

    except Exception as e:
        # Handle any errors and replace the response with a user-friendly message
        print(f"Error: {e}")  # Log the error for debugging
        response = "I am sorry, I don't get the query."

    return response

# -------------------------------

# Ask question route to handle user queries
# Ask question route to handle user queries
@app.route('/ask_question', methods=['POST'])
def ask_question():
    global query_chain, chat_history ,language_code
    question = request.json.get('question')
    language = language_code["language"]
    target_code=language_code["code"]

    # Language code mapping
    language_codes = {
        "Spanish": "es",
        "german": "de",
        "hindi": "hi",
        "french": "fr",
        "english": "en"
    }
    # target_code = language_codes.get(language, "en")

    # Translate the question to English for querying
    english_question = question
    if target_code != "en":
        english_question = translate_text(question, target_language="en")

    # Add the question to chat history
    chat_history.append({"role": "user", "content": question})

    try:
        # Query with English question
        response = process_question(english_question)

       

        

        # Convert non-string responses to string before translating
        if not isinstance(response, str):
            response = str(response)

        print(type(response))

        # Translate the response back to the selected language
        translated_response = translate_text(response, target_code)

        print(language,target_code)
        
        print(translated_response)

        # Add response to chat history and return it
        chat_history.append({"role": "assistant", "content": translated_response})
        return jsonify({"response": translated_response})
    except Exception as e:
        print(f"Error during question answering: {str(e)}")
        return jsonify({"response": f"Error: {str(e)}"})


# Route to clear chat history
@app.route('/clear_all', methods=['POST'])
def clear_all():
    global chat_history
    chat_history.clear()  # Clear the chat history
    return jsonify({"status": "Cleared chat history."})

if __name__ == '__main__':

    app.run(debug=True, port=5002)
