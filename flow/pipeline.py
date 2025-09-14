from prefect import flow, task
import subprocess

@task(retries=2, retry_delay_seconds=60)
def run_script(script_path):
    subprocess.run(["python", script_path], check=True)

@task(retries=2, retry_delay_seconds=60)
def run_notebook(nb_path, out_path):
    subprocess.run([
        "jupyter", "nbconvert", "--to", "notebook",
        "--execute", nb_path,
        "--output", out_path
    ], check=True)

@flow(name="InsightBot Daily Pipeline")
def daily_pipeline():
    print("🚀 Starting Daily Pipeline...")
    
    # 1. Web scraping
    run_script("scripts/web_scraping.py")
    
    # 2. Data cleaning notebook
    run_notebook("notebooks/data_cleaning.ipynb", 
                 "notebooks/data_cleaning_out.ipynb")
    
    # 3. Pattern model notebook
    run_notebook("notebooks/pattern_model.ipynb", 
                 "notebooks/pattern_model_out.ipynb")
    
    # 4. MongoDB to CSV export
    run_script("scripts/mongo_to_csv.py")

    print("✅ Pipeline Finished Successfully!")


daily_pipeline()
