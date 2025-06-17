from google.colab import drive
drive.mount('/content/drive')

# !pip install -q -U google-generativeai

import google.generativeai as genai
import os
import google.generativeai as genai
import time
import csv
import logging
import re
from tqdm import tqdm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("breeding_site_analysis.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Configuration
API_KEY = 'YOUR_API_KEY'
MODEL_NAME = "gemini-2.0-flash"
IMAGE_FOLDER = "/content/drive/MyDrive/Notebook/Breeding Place.v5i.multiclass/train"
INPUT_CSV = "/content/drive/MyDrive/Notebook/Breeding Place.v5i.multiclass/train/_classes.csv"
OUTPUT_CSV = "output.csv"
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

EXTRACTION_PROMPT = """
You are creating a dataset for an image analysis model designed to identify potential mosquito breeding sites. The dataset will consist of image-question-answer pairs. For the provided image, generate a question that asks whether the image depicts a potential mosquito breeding site. Then, provide a detailed answer explaining why or why not. Don't give extra text.

Output format:

Question: [Your generated question]

Response: [Yes/No]

Reasoning(Why): [Your detailed reasoning]"""

def process_image(img_path, model):
    """Process a single image and extract analysis."""
    img_file = os.path.basename(img_path)
    logger.info(f"Processing {img_file}...")

    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            img = genai.upload_file(img_path)
            response = model.generate_content([EXTRACTION_PROMPT, img])
            extracted_text = response.text

            # Clean and parse response
            cleaned_text = extracted_text.replace('```', '').replace("'''", '').strip()

            # Use regex to extract components
            match = re.search(
                r'Question:\s*(.*?)\s*Response:\s*(.*?)\s*Reasoning\(Why\):\s*(.*)',
                cleaned_text,
                re.DOTALL
            )

            if not match:
                raise ValueError("Invalid response format from model")

            return {
                "Question": match.group(1).strip(),
                "Response": match.group(2).strip(),
                "Reasoning": match.group(3).strip()
            }

        except Exception as e:
            retry_count += 1
            logger.error(f"Error processing {img_file} (attempt {retry_count}/{MAX_RETRIES}): {str(e)}")
            time.sleep(RETRY_DELAY)

    logger.error(f"Failed to process {img_file} after {MAX_RETRIES} attempts")
    return {
        "Question": "Error",
        "Response": "Error",
        "Reasoning": f"Failed to process after {MAX_RETRIES} attempts"
    }

def main():
    # Initialize Gemini
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)

    # Read input data
    input_rows = []
    with open(INPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            input_rows.append(row)

    # Load existing processed data
    processed = {}
    output_exists = os.path.exists(OUTPUT_CSV)
    if output_exists:
        with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                processed[row['filename']] = row

    # Prepare fieldnames
    fieldnames = ['filename', 'tire_with_water', 'vase_with_water',
                 'Question', 'Response', 'Reasoning']

    # Initialize output data
    output_data = []
    for row in input_rows:
        filename = row['filename']
        if filename in processed:
            output_data.append(processed[filename])
        else:
            output_data.append({
                'filename': filename,
                'tire_with_water': row['tire_with_water'],
                'vase_with_water': row['vase_with_water'],
                'Question': 'Pending',
                'Response': 'Pending',
                'Reasoning': 'Pending'
            })

    # Create or overwrite CSV with initial state
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_data)

    # Process images with checkpointing
    try:
        for idx, row in enumerate(tqdm(input_rows, desc="Processing Images")):
            filename = row['filename']

            # Skip already processed
            if filename in processed:
                continue

            # Check if image exists
            img_path = os.path.join(IMAGE_FOLDER, filename)
            if not os.path.exists(img_path):
                logger.error(f"Image not found: {filename}")
                result = {
                    "Question": "Error",
                    "Response": "Error",
                    "Reasoning": "Image file not found"
                }
            else:
                result = process_image(img_path, model)

            # Update output data
            output_data[idx] = {
                'filename': filename,
                'tire_with_water': row['tire_with_water'],
                'vase_with_water': row['vase_with_water'],
                'Question': result['Question'],
                'Response': result['Response'],
                'Reasoning': result['Reasoning']
            }

            # Update CSV immediately
            with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(output_data)

            # Add small delay to avoid rate limiting
            time.sleep(0.5)

    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Saving checkpoint...")
    except Exception as e:
        logger.error(f"Critical error occurred: {str(e)}. Saving checkpoint...")

    # Final save to ensure last state is preserved
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_data)

    logger.info(f"Processing completed. Final results saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
